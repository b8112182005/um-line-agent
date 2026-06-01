# CHANGELOG — um-line-agent

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
