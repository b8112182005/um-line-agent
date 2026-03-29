# CHANGELOG — um-line-agent

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
