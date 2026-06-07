# CHANGELOG — um-line-agent

## 2026-06-07 — 線上備料上線除錯 + 表單版面重整

### 修復
- 切模式選單沒換：`_bind_rich_menu` 對失效 menu_id 綁定 404 靜默失敗。改 bind 回 bool + `_switch_menu` 自我修復（清快取重抓），審核熟客/follow/切模式三處統一走它。
- LIFF 點開變官網：LINE Login channel(2010310048) 未發佈（HT 已發佈）；endpoint 經查正確為 /order。
- 表單空無商品：bot 連 WMS 帳密錯。改用 engineer `HTfoder`（UM-KENYA 密碼已失效），設入 Railway + .env，實測查得 525 筆。

### 變更
- 熟客選單「線上備料」由 message 改 uri，一鍵直開 LIFF 下單表單（避免兩段式/按錯鄰格作品集）。
- 下單表單(`assets/order.html`)版面重整：品牌標籤化、品名 word-break 不爆版、吸頂搜尋列 + 品牌快篩 chips（前端即時篩選）、加大數量鈕、已選高亮、底部選購摘要。

## 2026-06-07 — 模式切換新增「熟客模式」（三態）

### 變更
- 內部人員（boss / engineer）模式切換由二態擴為**三態**：內部同仁 / 客服（非熟客客人）/ 熟客。
  - `_staff_test_mode`（set）改為 `_staff_mode`（dict：`service` / `vip`，不在 dict = 內部同仁，重啟回預設）。
  - 切換時**同步換 rich menu**：客服模式→非熟客版選單、熟客模式→熟客版選單、內部模式→還原熟客版（內部人員本可線上備料）。
  - 「線上備料」依模擬視角判定：熟客模式→可開 LIFF 下單、客服模式→當非熟客擋下，可真正體驗兩種客人視角。
- 指令：客服模式 / 熟客模式 / 內部模式 / 目前模式（各含多個同義詞）。
- 新增 `_switch_menu(kind, user_id)` 輔助函式。

## 2026-06-06 — 熟客線上叫貨（LIFF）+ 雙人下單通知

### 新增
- `liff_api.py`：LIFF 線上叫貨 BFF。熟客在 LINE 內開表單下單，後端驗證 idToken（限 approved/boss/engineer），代理 WMS 查品項目錄、查上次訂單、建「待確認訂單」（不扣庫存）。
- `main.py`：掛上 `/liff` 路由 + `/order` 表單頁（`assets/order.html`）。「線上備料」改為：熟客回 LIFF 連結、非熟客提示洽專員、未設定 LIFF_ID 則回設定中。
- `api_client.py`：新增 `wms_post`。
- `config.py`：新增 `LIFF_ID`、`LINE_LOGIN_CHANNEL_ID`。

### 變更
- 新訂單通知對象由「只通知葉老闆」擴為「葉老闆（塗料）+ 工程師（HT）」。

### 部署前必設環境變數（Railway）
- `LIFF_ID`、`LINE_LOGIN_CHANNEL_ID`（= 驗 idToken 的 LINE Login channel ID）。未設則線上叫貨停用、其餘功能不受影響。

## 2026-06-01 — 內部人員模式切換指令

### 新增
- 內部人員（boss / engineer）可用清楚的指令在「內部同仁模式 ⇄ 客服模式」之間切換：
  - 切到客服視角：「客服模式」（亦相容舊詞 測試模式 / 切換客服 / 客服測試）
  - 切回內部：「內部模式」（亦相容 結束測試 / 切回來 / 退出測試）
  - 查目前模式：「目前模式」
- 沿用既有 `_staff_test_mode`（記憶體，重啟回內部模式），僅整理指令命名與新增狀態查詢

## 2026-06-01 — 修復：客服傳照片後「忘記」照片

### 修復
- `handle_image` 分析完照片後沒有寫入對話歷史，導致客人下一句文字提問（如「這上面顏色你們都有嗎」）時，小墨完全不記得剛剛看過照片。
  現在分析成功會以「（客人傳了一張照片…）＋小墨的描述」記入 `_conversations`，後續提問即有照片上下文。
- 同步在 `handle_image` 補 `_touch(user_id)`，避免該用戶狀態被閒置清理誤刪。

## 2026-06-01 — CLAUDE.md 準確性校對

### 文件
- 校正 CLAUDE.md 與實際程式碼的落差（只改文件、不動程式）：
  - 標記「老闆聊天即時查 WMS/UMmoney」尚未接線（`parse_intent` 未被呼叫）
  - 標記定時推播未啟動（`setup_scheduler()` 從未被呼叫，lifespan 只做 init_db）→ 整套 WMS/UMmoney 功能目前休眠（兩條送達管道都沒接）
  - 標記白名單聊天管理（通過/不要/名單/待審）與陌生人自動 pending 通知尚未實作
  - 身份分流改為對齊 main.py（內部人員走 handle_staff、其餘走 handle_customer）
  - 補上 LINE_ENG_BOSS_USER_ID、OPENAI_API_KEY 環境變數
  - 修正「config.py 在 .gitignore」的錯誤敘述（實際已納入版控、不含機密）

## 2026-06-01 — CI 自動化 + 修復過期測試

### 新增
- `.github/workflows/ci.yml`：每次 PR 與 push 到 master/staging 時，自動跑 `compileall` 語法檢查 + `test_bot.py`

### 修復
- `test_bot.py` 已與程式碼脫節，修正後可通過（29 項全綠）：
  - `init_db()` 已改為無參數＋寫死種子資料，測試改為對齊現況（角色、note、群組以實際種子驗證，不再用過期的測試 ID）
  - 移除 `test_admin_commands`：它測的 `main.handle_boss_admin` 在現行 codebase 不存在（白名單聊天管理指令尚未實作）

## 2026-05-31 — 小墨身份保護 + 安全加固

### 身份保護
- customer.py — 客服與內部同仁兩組 system prompt 都加入身份原則：被問「你是什麼模型」、「是不是 Claude/GPT」、「誰開發的」等問題時，只回答「我是瑀墨的 AI 助理小墨」，不再透露底層模型、AI 公司或技術供應商
- 新增 `_is_identity_question` 硬攔截：在送進 LLM 之前就攔下模型探詢，回固定話術，不依賴 AI 自律（客服＋內部模式皆套用）

### 修正（PR #1 code review 回饋）
- 備料需求持久化（`save_demand`）不再受通知冷卻影響：先前若用戶剛說過「找真人」，10 分鐘內完成的備料訂單會被連同推播一起跳過而掉單；現在一律存檔，僅推播去重
- 「找真人」與「備料」改用各自獨立的冷卻 key，彼此不互相壓制
- 語音額度：改在呼叫 Whisper 當下扣額度（無論轉錄成功/空白/失敗），避免空白語音狂打 Whisper 卻不耗額度；成功時下游 `handle_customer(count_quota=False)` 不重複扣

### 安全加固（防騷擾／防大量破壞）
- 修正 `_INJECTION_PATTERNS` 過寬的「你是一個」「你現在是」誤判正常客戶，收斂為精準越獄話術並補上編碼／開發者模式繞過詞
- 老闆通知冷卻＋去重（`_can_notify_staff`，10 分鐘）：防止「找真人」與備料推播被連續灌爆
- 圖片（Vision）與語音（Whisper）納入每日額度，避免高成本 API 被無上限濫用
- 簽章驗證改為 fail-closed：缺 `LINE_CHANNEL_SECRET` 時拒絕請求（本機可用 `ALLOW_UNSIGNED_WEBHOOK=1` 放行），並新增事件 timestamp 防重放（10 分鐘窗口）
- 記憶體狀態定期清理（`_maybe_cleanup`）：淘汰閒置 24h 的對話/計數與過期日期記錄，避免 in-memory dict 緩慢洩漏

## 2026-04-04 — v1.1.0 身份分流 + AI 客服

### 新增
- 白名單機制：BOSS_USER_IDS 環境變數，逗號分隔 LINE User ID
- 身份分流：白名單用戶走內部查詢，其他用戶走客服模式
- AI 客服「小墨」：Claude Haiku 驅動，專業親切的塗料客服對話
- 客服固定回覆：產品介紹、備料詢問、工程服務、常見問題、聯絡方式、服務流程
- 客服 Rich Menu（圖文選單）：6 格設計，自動產圖 + 設為預設
- rich_menu.py 腳本：一鍵建立選單（python rich_menu.py）

### 新增檔案
- customer.py — 客服模式處理（AI 對話 + 觸發文字回覆）
- rich_menu.py — Rich Menu 建立腳本（Pillow 產圖）

### 修改
- config.py — 新增 BOSS_USER_IDS
- main.py — webhook 加入身份分流邏輯
- requirements.txt — 新增 Pillow

---

## 2026-03-29 — v1.0.0 初版上線

### 新增
- LINE Webhook server（FastAPI + uvicorn）
- Claude Haiku 意圖解析（claude-haiku-4-5-20251001）
- 關鍵字 fallback（Claude API 失敗時自動降級）
- Claude 口語化回覆（raw data → 親切中文）
- WMS 查詢：庫存搜尋、低庫存警報、進出貨紀錄、訂單摘要
- UMmoney 查詢：月收支（PnL）、支出分類、支出明細、帳款狀態
- 定時推播：每日 08:00 低庫存、每週一 08:30 月收支
- API client 自動登入 + token 過期重試
- Railway 部署配置（Procfile + railway.json）
- 環境變數化，敏感資訊不入 repo

### 修復
- 修正 SYSTEM_PROMPT 中 JSON 大括號與 .format() 衝突
- 修正 intent.py regex 中未轉義的 `?` 導致 PatternError
- 修正 Railway PORT 環境變數支援（${PORT:-8000}）
