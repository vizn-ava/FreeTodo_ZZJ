# 浜ゆ帴鍙樻洿娓呭崟锛堣闊宠兘鍔涳級

## 鐗堟湰鎽樿
- 鏂板锛氱嫭绔?`璇煶鑱婂ぉ` 闈㈡澘锛堢櫨鐐煎疄鏃惰闊筹級
- 鏂板锛氬墠绔闊宠緭鍏ワ紙寰呭姙/鑱婂ぉ/寰呭姙璇︽儏锛?- 鏂板锛氳缃〉鐧剧偧閰嶇疆鍏ュ彛锛圓PI Key 鎺╃爜锛?- 浼樺寲锛氳闊宠亰澶╂枃鏈敼涓轰細璇濅腑瀹炴椂鏄剧ず
- 浼樺寲锛氫腑鏂囪瘑鍒粺涓€绠€浣撹緭鍑?
## 璇︾粏鍙樻洿

### 1) 鍓嶇璇煶杈撳叆
- 鏂板鍙鐢?Hook锛?- `free-todo-frontend/lib/hooks/useVoiceInput.ts`
- `free-todo-frontend/lib/hooks/useVoiceHotkey.ts`
- 鎺ュ叆涓氬姟杈撳叆妗嗭細
- `free-todo-frontend/apps/chat/components/input/InputBox.tsx`
- `free-todo-frontend/apps/todo-list/NewTodoInlineForm.tsx`
- `free-todo-frontend/apps/todo-detail/components/DescriptionSection.tsx`
- `free-todo-frontend/apps/todo-detail/components/NotesEditor.tsx`
- 璁剧疆椤规墿灞曪細
- `free-todo-frontend/apps/settings/components/VoiceInputSection.tsx`
- `free-todo-frontend/lib/query/config.ts`

### 2) 瀹炴椂璇煶鑱婂ぉ锛堢櫨鐐硷級
- 鏂板鑱婂ぉ闈㈡澘锛?- `free-todo-frontend/apps/voice-chat/VoiceChatPanel.tsx`
- `free-todo-frontend/apps/voice-chat/index.ts`
- 甯冨眬鎺ュ叆锛?- `free-todo-frontend/components/layout/PanelContent.tsx`
- `free-todo-frontend/components/layout/BottomDock.tsx`
- `free-todo-frontend/app/page.tsx`
- 鍚庣璺敱涓庝唬鐞嗭細
- `lifetrace/routers/voice_chat.py`
- `lifetrace/server.py`

### 3) 鐧剧偧閰嶇疆鍓嶇鍖?- 鏂板璁剧疆缁勪欢锛?- `free-todo-frontend/apps/settings/components/BailianConfigSection.tsx`
- 璁剧疆椤甸潰鎺ュ叆锛?- `free-todo-frontend/apps/settings/SettingsPanel.tsx`
- `free-todo-frontend/apps/settings/components/index.ts`
- 鏂囨琛ュ厖锛?- `free-todo-frontend/lib/i18n/messages/zh.json`
- `free-todo-frontend/lib/i18n/messages/en.json`
- 閰嶇疆绫诲瀷琛ュ厖锛?- `free-todo-frontend/lib/query/config.ts`
- 鍚庣閰嶇疆鏄犲皠涓庢帺鐮侊細
- `lifetrace/services/config_service.py`

### 4) ASR 涓庢枃鏈鑼冨寲
- 蹇€熻浆鍐欐帴鍙ｏ細
- `lifetrace/routers/audio.py` (`/api/audio/transcriptions/quick`)
- 阿里云百炼在线ASR + 璇磋瘽浜哄垎绂绘湇鍔★細
- `lifetrace/services/audio_transcription_service.py`
- 鏂板涓枃绻佽浆绠€澶勭悊锛圤penCC锛?- 榛樿閰嶇疆鎵╁睍锛?- `lifetrace/config/default_config.yaml`

## 楠岃瘉璁板綍
- 鍓嶇绫诲瀷妫€鏌ラ€氳繃锛歚pnpm -C free-todo-frontend exec tsc --noEmit`
- 鍚庣鍏抽敭瀵煎叆涓庨厤缃槧灏勬牎楠岄€氳繃锛堟湰鍦拌剼鏈級

## 瀵规帴椋庨櫓鎻愮ず
- 閰嶇疆涓嶅畬鏁翠細瀵艰嚧璇煶鑱婂ぉ鍚姩澶辫触锛圓PI Key / Workspace / App ID锛?- 鐧剧偧搴旂敤闇€宸插彂甯冧笖鏈夐搴?- 鏈湴楹﹀厠椋庢潈闄愭槸蹇呴渶椤?


