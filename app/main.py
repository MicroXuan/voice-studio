import asyncio
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.azure_tts_service import AzureTTSService
from app.config import AzureSpeechConfig
from app.job_store import ActiveJobError, JobRecord, JobStore
from app.models import JobResponse, JobState, SynthesisRequest, VoiceOption
from app.tts_router import TTSRouter
from app.tts_service import (
    AudioWriteError,
    EdgeTTSService,
    EmptyAudioError,
    SpeechSynthesizer,
    TTSAuthenticationError,
    TTSQuotaError,
    TTSServiceError,
    TTSUnavailableError,
)
from app.voices import build_voice_catalog, get_voice


logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(
    store: JobStore | None = None,
    tts_service: SpeechSynthesizer | None = None,
    azure_config: AzureSpeechConfig | None = None,
    catalog: tuple[VoiceOption, ...] | None = None,
) -> FastAPI:
    config = azure_config or AzureSpeechConfig.from_env()
    voice_catalog = catalog or build_voice_catalog(config.configured)
    job_store = store or JobStore(
        Path(tempfile.gettempdir()) / "voice-studio-audio"
    )
    synthesizer = tts_service or TTSRouter(
        voice_catalog,
        EdgeTTSService(),
        AzureTTSService(config) if config.configured else None,
    )
    background_tasks: set[asyncio.Task[None]] = set()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await job_store.cleanup_expired()
        yield
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)

    application = FastAPI(title="声屿 Voice Studio", lifespan=lifespan)
    application.state.store = job_store
    application.state.tts_service = synthesizer
    application.state.voice_catalog = voice_catalog
    application.state.background_tasks = background_tasks
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @application.get("/api/voices", response_model=list[VoiceOption])
    async def list_voices() -> tuple[VoiceOption, ...]:
        return voice_catalog

    @application.post(
        "/api/jobs",
        response_model=JobResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_job(request: SynthesisRequest, response: Response) -> JobResponse:
        await job_store.cleanup_expired()
        voice = get_voice(request.voice, voice_catalog)
        if voice is None:
            raise HTTPException(status_code=422, detail="请选择有效的声音")
        if not voice.available:
            raise HTTPException(
                status_code=422,
                detail=voice.unavailable_reason or "声音当前不可用",
            )
        try:
            record = await job_store.create()
        except ActiveJobError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        task = asyncio.create_task(
            _run_job(job_store, synthesizer, record.id, request)
        )
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        response.headers["Location"] = f"/api/jobs/{record.id}"
        return _to_response(record)

    @application.get("/api/jobs/{job_id}", response_model=JobResponse)
    async def get_job(job_id: UUID) -> JobResponse:
        await job_store.cleanup_expired()
        record = await job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        return _to_response(record)

    @application.get("/api/jobs/{job_id}/audio")
    async def get_audio(
        job_id: UUID, download: bool = Query(default=False)
    ) -> FileResponse:
        await job_store.cleanup_expired()
        record = await job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        if (
            record.state is not JobState.COMPLETED
            or record.output_path is None
            or not record.output_path.is_file()
            or record.output_path.stat().st_size == 0
        ):
            raise HTTPException(status_code=409, detail="音频尚未生成完成")
        return FileResponse(
            record.output_path,
            media_type="audio/mpeg",
            filename=f"voice-studio-{job_id}.mp3",
            content_disposition_type="attachment" if download else "inline",
        )

    return application


async def _run_job(
    store: JobStore,
    synthesizer: SpeechSynthesizer,
    job_id: UUID,
    request: SynthesisRequest,
) -> None:
    try:
        await store.start(job_id)

        async def report_progress(progress: int, message: str) -> None:
            await store.update_progress(job_id, progress, message)

        output_path = store.output_dir / f"{job_id}.mp3"
        await synthesizer.synthesize(
            request.text,
            request.voice,
            request.rate,
            request.pitch,
            request.volume,
            output_path,
            report_progress,
        )
        await store.complete(job_id, output_path)
    except asyncio.CancelledError:
        await store.fail(job_id, "生成任务已取消，请重新生成")
        raise
    except TTSAuthenticationError:
        logger.warning("Azure Speech authentication failed")
        await store.fail(job_id, "Azure Speech 配置无效，请检查 Key 和 Region")
    except TTSQuotaError:
        logger.warning("Azure Speech quota or request limit reached")
        await store.fail(
            job_id,
            "Azure 免费额度可能已用完或请求过于频繁，请稍后重试",
        )
    except TTSServiceError:
        logger.warning("Azure Speech rejected the synthesis request")
        await store.fail(job_id, "Azure 语音服务暂时不可用，请稍后重试")
    except TTSUnavailableError:
        logger.warning("Speech service is unavailable")
        await store.fail(job_id, "无法连接微软语音服务，请检查网络后重试")
    except EmptyAudioError:
        logger.warning("Speech service returned no audio")
        await store.fail(job_id, "语音服务没有返回有效音频，请稍后重试")
    except AudioWriteError:
        logger.warning("Could not write generated audio")
        await store.fail(job_id, "无法保存音频，请检查磁盘空间或临时目录权限")
    except ValueError:
        logger.exception("Generated audio file was empty")
        await store.fail(job_id, "语音服务没有返回有效音频，请稍后重试")
    except Exception:
        logger.exception("Unexpected synthesis failure")
        await store.fail(job_id, "生成语音时发生错误，请重试")


def _to_response(record: JobRecord) -> JobResponse:
    audio_url = (
        f"/api/jobs/{record.id}/audio"
        if record.state is JobState.COMPLETED
        else None
    )
    return JobResponse(
        id=record.id,
        state=record.state,
        progress=record.progress,
        message=record.message,
        error=record.error,
        audio_url=audio_url,
    )


app = create_app()
