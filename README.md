# 声屿 Voice Studio

一个本地运行的中文文本转语音工作台。粘贴最长 20,000 字的文本，选择云健、云希、云夏、云扬、云泽或晓晓，调整语速、音调和音量，即可试听并下载 MP3。

## 运行要求

- Python 3.11 或更高版本
- 可访问 Microsoft Edge 在线语音服务的网络连接
- Chrome、Edge、Safari 或 Firefox 的近期版本

云泽使用 Azure Speech，需要额外配置 Azure Speech 资源的 Key 和 Region；其他五个声音仍使用 Edge TTS，不需要 Azure Key。

`edge-tts` 是第三方开源客户端，调用的是 Microsoft Edge 在线语音服务，并不是可离线部署的微软开源语音模型。接口可用性与使用政策可能变化；本项目当前定位为个人本地工具。

## 本地启动

在项目目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Windows PowerShell 激活虚拟环境：

```powershell
.venv\Scripts\Activate.ps1
```

浏览器打开：

```text
http://127.0.0.1:8000
```

停止服务时，在终端按 `Ctrl+C`。

## 配置 Azure 云泽

只有使用云泽时才需要配置 Azure。先复制本地配置模板：

```bash
cp .env.example .env
```

打开 `.env`，只在自己的电脑上填写 Azure Speech 的 Key：

```dotenv
AZURE_SPEECH_KEY=在这里填写你的Key
AZURE_SPEECH_REGION=eastasia
```

保存后重启 Uvicorn，再刷新网页。云泽卡片从“需配置 Azure Speech”变为可选择，即表示配置已读取。

`.env` 已被 Git 忽略。不要提交、分享、截图或把 Key 放进网页代码；如果 Key 曾经暴露，请立即在 Azure 门户的“密钥和终结点”页面重新生成该密钥。

创建 Speech 资源时可选择 `Free F0` 免费层。免费额度和服务限制以 Azure 门户当前显示为准；本项目不会绕过额度，也不会替你控制 Azure 订阅中的其他付费资源。

## 使用方法

1. 粘贴需要配音的中文文本。
2. 选择云健、云希、云夏、云扬、云泽或晓晓。未配置 Azure 时，云泽会显示为不可用。
3. 按需调整语速、音调和音量。
4. 点击“生成语音”，等待进度到达 100%。
5. 在页面中试听，或点击“下载 MP3”。

第一版同一时间只处理一个任务。生成期间请保持页面和本地服务开启。

## 运行测试

```bash
python -m pytest -v
python -m compileall -q app
```

## 临时文件

音频写入系统临时目录下的 `voice-studio-audio` 子目录。任务记录保存在进程内存中，默认一小时后过期；服务启动、创建任务、查询任务或请求音频时会清理过期文件。重启服务后，旧任务不会继续显示在网页中。

## 常见问题

### 页面显示“无法连接微软语音服务”

确认电脑可以正常联网，然后重新生成。公司网络、防火墙、代理或微软服务暂时不可用都可能导致连接失败。

### 页面可以打开，但声音清单没有出现

确认终端中的 Uvicorn 服务仍在运行，并刷新页面。如果端口被占用，可以改用其他端口：

```bash
uvicorn app.main:app --reload --port 8001
```

随后访问 `http://127.0.0.1:8001`。

### 提示无法保存音频

检查磁盘剩余空间，以及系统临时目录是否可写。清理磁盘空间后重新生成。

### 云泽显示“需配置 Azure Speech”

确认项目根目录存在 `.env`，其中同时填写了 `AZURE_SPEECH_KEY` 和 `AZURE_SPEECH_REGION=eastasia`，然后完整停止并重新启动 Uvicorn。只配置其中一项时，云泽仍会保持禁用。

### 云泽提示 Azure 配置无效

确认 Key 来自当前 Speech 资源，Region 与资源页面的“位置/区域”一致。当前资源位于 East Asia，因此 Region 应为 `eastasia`。不要把 Key 粘贴到聊天或问题截图中。

### 能否公开部署

当前版本以单机个人使用为目标。公开部署前需要增加按 IP 限流、每日字符额度、持久任务队列、并发限制、对象存储和监控，不能直接把开发服务器暴露到公网。
