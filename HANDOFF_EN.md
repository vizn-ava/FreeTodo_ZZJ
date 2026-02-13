# FreeTodo Handoff (Voice Input + Bailian Realtime Voice Chat)

## 1. Scope
- This handoff build includes two production-facing voice features:
- Hold-to-talk voice input for text fields (online ASR via Bailian).
- Dedicated realtime voice chat panel powered by Bailian via backend WebSocket proxy.

## 2. Delivered Capabilities
- Default hotkey is `AltRight` (hold to record, release to transcribe).
- Voice input language is configurable (`zh` / `en` / `auto`), default `zh`.
- Chinese transcript normalization to simplified Chinese is enabled.
- New settings section for Bailian credentials:
- `API Key` (masked after save)
- `Workspace ID`
- `App ID`
- Voice chat transcript is rendered in real time during the call.

## 3. Run Locally

### Backend
```bash
cd FreeTodo
.venv\Scripts\python.exe -m lifetrace.server
```

### Frontend
```bash
cd FreeTodo/free-todo-frontend
pnpm install
pnpm dev
```

## 4. Integration Steps
1. Start backend and frontend.
2. Open `Settings`.
3. Fill values in `Bailian Voice Chat`:
4. `API Key`
5. `Workspace ID`
6. `App ID`
7. Open `Voice Chat` panel and run a realtime session test.
8. Verify voice input in chat/todo/todo-detail inputs.

## 5. Key Endpoints
- Quick ASR (no record persistence): `POST /api/audio/transcriptions/quick`
- Bailian bootstrap: `GET /api/voice-chat/bailian/bootstrap`
- Bailian WS proxy: `WS /api/voice-chat/bailian/ws`

## 6. Key Files
- Voice input
- `free-todo-frontend/lib/hooks/useVoiceInput.ts`
- `free-todo-frontend/lib/hooks/useVoiceHotkey.ts`
- `lifetrace/services/audio_transcription_service.py`
- `lifetrace/routers/audio.py`
- Realtime voice chat
- `free-todo-frontend/apps/voice-chat/VoiceChatPanel.tsx`
- `lifetrace/routers/voice_chat.py`
- Bailian config in settings
- `free-todo-frontend/apps/settings/components/BailianConfigSection.tsx`
- `free-todo-frontend/apps/settings/SettingsPanel.tsx`
- `lifetrace/services/config_service.py`

## 7. Security Notes
- Do not commit real keys.
- Preferred flow: users configure keys from frontend settings.
- Environment variables still supported and take priority:
- `DASHSCOPE_API_KEY`
- `BAILIAN_WORKSPACE_ID`
- `BAILIAN_APP_ID`


