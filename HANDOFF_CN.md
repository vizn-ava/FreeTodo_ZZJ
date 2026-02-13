# FreeTodo 瀵规帴璇存槑锛堣闊宠緭鍏?+ 鐧剧偧瀹炴椂璇煶鑱婂ぉ锛?
## 1. 鐗堟湰鐩爣
- 鎻愪緵鍙洿鎺ヨ仈璋冪殑璇煶鑳藉姏鐗堟湰锛屽寘鍚袱鏉′富绾匡細
- 璇煶杈撳叆锛氬湪寰呭姙銆佽亰澶┿€佸緟鍔炶鎯呰緭鍏ユ涓寜浣忓揩鎹烽敭褰曢煶锛屾澗寮€杞枃瀛楋紙阿里云百炼在线ASR锛夈€?- 瀹炴椂璇煶鑱婂ぉ锛氱嫭绔嬮潰鏉挎帴鍏ラ樋閲屼簯鐧剧偧锛屾敮鎸佸疄鏃惰闊冲璇濅笌浼氳瘽鏂囨湰灞曠ず銆?
## 2. 鍔熻兘娓呭崟
- `AltRight`锛堥粯璁わ級闀挎寜褰曢煶锛屾澗寮€杞啓銆?- 璇煶杈撳叆璇█鍙厤锛坄zh` / `en` / `auto`锛夛紝榛樿 `zh`銆?- 杞啓鍚庡鐞嗙粺涓€涓虹畝浣撲腑鏂囷紙涓枃鍦烘櫙锛夈€?- 璁剧疆椤垫柊澧炵櫨鐐奸厤缃」锛?- `API Key`锛堜繚瀛樺悗鎺╃爜鏄剧ず锛?- `Workspace ID`
- `App ID`
- 璇煶鑱婂ぉ娑堟伅鍦ㄤ細璇濊繃绋嬩腑瀹炴椂鍛堢幇锛堢敤鎴峰拰鍔╂墜閮藉疄鏃舵洿鏂帮級銆?
## 3. 蹇€熷惎鍔?
### 鍚庣
```bash
cd FreeTodo
.venv\Scripts\python.exe -m lifetrace.server
```

### 鍓嶇
```bash
cd FreeTodo/free-todo-frontend
pnpm install
pnpm dev
```

## 4. 瀵规帴姝ラ锛堝悓浜嬶級
1. 鍚姩鍓嶅悗绔悗锛岃繘鍏?`璁剧疆` 闈㈡澘銆?2. 鍦?`鐧剧偧璇煶鑱婂ぉ` 鍖哄潡濉啓锛?3. `API Key`
4. `Workspace ID`
5. `App ID`
6. 鎵撳紑 `璇煶鑱婂ぉ` 闈㈡澘锛屽紑濮嬩細璇濋獙璇併€?7. 鍦?`寰呭姙/鑱婂ぉ/寰呭姙璇︽儏` 杈撳叆妗嗛獙璇佽闊宠緭鍏ヨ浆鍐欍€?
## 5. 鍏抽敭鎺ュ彛
- 蹇€熻浆鍐欙紙涓嶈惤搴擄級锛歚POST /api/audio/transcriptions/quick`
- 鐧剧偧鍙傛暟涓嬪彂锛歚GET /api/voice-chat/bailian/bootstrap`
- 鐧剧偧璇煶浼氳瘽浠ｇ悊锛歚WS /api/voice-chat/bailian/ws`

## 6. 鍏抽敭鏂囦欢
- 璇煶杈撳叆鏍稿績
- `free-todo-frontend/lib/hooks/useVoiceInput.ts`
- `free-todo-frontend/lib/hooks/useVoiceHotkey.ts`
- `lifetrace/services/audio_transcription_service.py`
- `lifetrace/routers/audio.py`
- 瀹炴椂璇煶鑱婂ぉ
- `free-todo-frontend/apps/voice-chat/VoiceChatPanel.tsx`
- `lifetrace/routers/voice_chat.py`
- 鐧剧偧鍓嶇閰嶇疆
- `free-todo-frontend/apps/settings/components/BailianConfigSection.tsx`
- `free-todo-frontend/apps/settings/SettingsPanel.tsx`
- `lifetrace/services/config_service.py`

## 7. 瀹夊叏涓庨厤缃缓璁?- 涓嶈鎻愪氦鐪熷疄瀵嗛挜鍒颁粨搴撱€?- 棣栭€夊湪璁剧疆椤靛～鍐欏瘑閽ワ紝鐢卞悗绔啓鍏ユ湰鍦扮敤鎴烽厤缃€?- 鑻ラ渶鐜鍙橀噺浼樺厛瑕嗙洊锛屼娇鐢細
- `DASHSCOPE_API_KEY`
- `BAILIAN_WORKSPACE_ID`
- `BAILIAN_APP_ID`

## 8. 宸茬煡娉ㄦ剰浜嬮」
- 鐧剧偧杩炴帴澶辫触閫氬父鐢变笁绫婚棶棰樺鑷达細
- 瀵嗛挜/宸ヤ綔绌洪棿/App ID 涓嶅尮閰?- 鐧剧偧搴旂敤鏈彂甯冩垨鏃犲彲鐢ㄩ搴?- 鏈満缃戠粶闄愬埗瀵艰嚧 WebSocket 涓婃父涓嶅彲杈?


