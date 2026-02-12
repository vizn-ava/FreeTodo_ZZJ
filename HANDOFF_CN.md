# FreeTodo 对接说明（语音输入 + 百炼实时语音聊天）

## 1. 版本目标
- 提供可直接联调的语音能力版本，包含两条主线：
- 语音输入：在待办、聊天、待办详情输入框中按住快捷键录音，松开转文字（faster-whisper）。
- 实时语音聊天：独立面板接入阿里云百炼，支持实时语音对话与会话文本展示。

## 2. 功能清单
- `AltRight`（默认）长按录音，松开转写。
- 语音输入语言可配（`zh` / `en` / `auto`），默认 `zh`。
- 转写后处理统一为简体中文（中文场景）。
- 设置页新增百炼配置项：
- `API Key`（保存后掩码显示）
- `Workspace ID`
- `App ID`
- 语音聊天消息在会话过程中实时呈现（用户和助手都实时更新）。

## 3. 快速启动

### 后端
```bash
cd FreeTodo
.venv\Scripts\python.exe -m lifetrace.server
```

### 前端
```bash
cd FreeTodo/free-todo-frontend
pnpm install
pnpm dev
```

## 4. 对接步骤（同事）
1. 启动前后端后，进入 `设置` 面板。
2. 在 `百炼语音聊天` 区块填写：
3. `API Key`
4. `Workspace ID`
5. `App ID`
6. 打开 `语音聊天` 面板，开始会话验证。
7. 在 `待办/聊天/待办详情` 输入框验证语音输入转写。

## 5. 关键接口
- 快速转写（不落库）：`POST /api/audio/transcriptions/quick`
- 百炼参数下发：`GET /api/voice-chat/bailian/bootstrap`
- 百炼语音会话代理：`WS /api/voice-chat/bailian/ws`

## 6. 关键文件
- 语音输入核心
- `free-todo-frontend/lib/hooks/useVoiceInput.ts`
- `free-todo-frontend/lib/hooks/useVoiceHotkey.ts`
- `lifetrace/services/audio_transcription_service.py`
- `lifetrace/routers/audio.py`
- 实时语音聊天
- `free-todo-frontend/apps/voice-chat/VoiceChatPanel.tsx`
- `lifetrace/routers/voice_chat.py`
- 百炼前端配置
- `free-todo-frontend/apps/settings/components/BailianConfigSection.tsx`
- `free-todo-frontend/apps/settings/SettingsPanel.tsx`
- `lifetrace/services/config_service.py`

## 7. 安全与配置建议
- 不要提交真实密钥到仓库。
- 首选在设置页填写密钥，由后端写入本地用户配置。
- 若需环境变量优先覆盖，使用：
- `DASHSCOPE_API_KEY`
- `BAILIAN_WORKSPACE_ID`
- `BAILIAN_APP_ID`

## 8. 已知注意事项
- 百炼连接失败通常由三类问题导致：
- 密钥/工作空间/App ID 不匹配
- 百炼应用未发布或无可用额度
- 本机网络限制导致 WebSocket 上游不可达

