# 交接变更清单（语音能力）

## 版本摘要
- 新增：独立 `语音聊天` 面板（百炼实时语音）
- 新增：前端语音输入（待办/聊天/待办详情）
- 新增：设置页百炼配置入口（API Key 掩码）
- 优化：语音聊天文本改为会话中实时显示
- 优化：中文识别统一简体输出

## 详细变更

### 1) 前端语音输入
- 新增可复用 Hook：
- `free-todo-frontend/lib/hooks/useVoiceInput.ts`
- `free-todo-frontend/lib/hooks/useVoiceHotkey.ts`
- 接入业务输入框：
- `free-todo-frontend/apps/chat/components/input/InputBox.tsx`
- `free-todo-frontend/apps/todo-list/NewTodoInlineForm.tsx`
- `free-todo-frontend/apps/todo-detail/components/DescriptionSection.tsx`
- `free-todo-frontend/apps/todo-detail/components/NotesEditor.tsx`
- 设置项扩展：
- `free-todo-frontend/apps/settings/components/VoiceInputSection.tsx`
- `free-todo-frontend/lib/query/config.ts`

### 2) 实时语音聊天（百炼）
- 新增聊天面板：
- `free-todo-frontend/apps/voice-chat/VoiceChatPanel.tsx`
- `free-todo-frontend/apps/voice-chat/index.ts`
- 布局接入：
- `free-todo-frontend/components/layout/PanelContent.tsx`
- `free-todo-frontend/components/layout/BottomDock.tsx`
- `free-todo-frontend/app/page.tsx`
- 后端路由与代理：
- `lifetrace/routers/voice_chat.py`
- `lifetrace/server.py`

### 3) 百炼配置前端化
- 新增设置组件：
- `free-todo-frontend/apps/settings/components/BailianConfigSection.tsx`
- 设置页面接入：
- `free-todo-frontend/apps/settings/SettingsPanel.tsx`
- `free-todo-frontend/apps/settings/components/index.ts`
- 文案补充：
- `free-todo-frontend/lib/i18n/messages/zh.json`
- `free-todo-frontend/lib/i18n/messages/en.json`
- 配置类型补充：
- `free-todo-frontend/lib/query/config.ts`
- 后端配置映射与掩码：
- `lifetrace/services/config_service.py`

### 4) ASR 与文本规范化
- 快速转写接口：
- `lifetrace/routers/audio.py` (`/api/audio/transcriptions/quick`)
- faster-whisper + 说话人分离服务：
- `lifetrace/services/audio_transcription_service.py`
- 新增中文繁转简处理（OpenCC）
- 默认配置扩展：
- `lifetrace/config/default_config.yaml`

## 验证记录
- 前端类型检查通过：`pnpm -C free-todo-frontend exec tsc --noEmit`
- 后端关键导入与配置映射校验通过（本地脚本）

## 对接风险提示
- 配置不完整会导致语音聊天启动失败（API Key / Workspace / App ID）
- 百炼应用需已发布且有额度
- 本地麦克风权限是必需项

