# CHANGELOG — um-line-agent

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
