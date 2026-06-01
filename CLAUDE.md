# um-line-agent

## 專案概述
瑀墨助理 LINE Bot，讓老闆在 LINE 上直接查詢倉儲和會計數據。

## 架構
- FastAPI + uvicorn
- Claude API (claude-haiku-4-5-20251001)：客服小墨對話、內部同仁對話、口語化回覆、圖片分析
- OpenAI Whisper：語音轉文字（客服）
- APScheduler 定時推播（每日低庫存、每週月收支）
- WMS P2 API + UMmoney P2 API（唯讀查詢）：query_wms.py / query_money.py，⚠️ 目前僅供定時推播使用
- intent.py（parse_intent 意圖解析 + 關鍵字 fallback）：模組已備，⚠️ 尚未接入聊天流程（保留供未來「老闆即時查詢」）

## 部署
- Railway: um-line-agent-production.up.railway.app (port 8080)
- LINE Channel: 瑀墨助理
- Webhook: https://um-line-agent-production.up.railway.app/callback

## 身份分流（main.py callback）
- 內部人員（LINE_BOSS_USER_ID / LINE_ENG_BOSS_USER_ID / LINE_ENGINEER_USER_ID，或 users 表 role 為 boss/engineer）→ handle_staff：輕鬆對話 AI（小墨）＋「最近需求」客戶統計
- 其餘 → handle_customer：AI 客服「小墨」＋ 圖文選單固定回覆
- 內部人員可打「測試模式」切到客服視角，「結束測試」切回
- ⚠️ 老闆「在聊天裡即時查 WMS/UMmoney」目前未接線（parse_intent 未被呼叫）；倉儲/會計數據目前只透過下方「定時推播」送達

## 環境變數
LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN,
LINE_BOSS_USER_ID（葉老闆/塗料）, LINE_ENG_BOSS_USER_ID（工程部門）, LINE_ENGINEER_USER_ID（工程師最高權限）,
WMS_API_URL, MONEY_API_URL, API_USERNAME, API_PASSWORD,
ANTHROPIC_API_KEY, OPENAI_API_KEY（語音轉文字 Whisper）
ALLOW_UNSIGNED_WEBHOOK（僅本機開發；正式環境勿設，缺 secret 時一律拒絕）

## 安全機制（customer.py / main.py）
- 身份保護：`_is_identity_question` 在進 LLM 前硬攔模型探詢，回固定話術（不自報 Claude/Anthropic）
- prompt injection：`_is_injection` 關鍵字攔截（客服模式）
- 老闆通知冷卻：`_can_notify_staff`（10 分鐘）防「找真人」灌爆
- 額度：每人每日 50 則，圖片/語音也納入計算
- webhook：HMAC 簽章 fail-closed + 事件 timestamp 防重放
- 記憶體：`_maybe_cleanup` 定期淘汰閒置狀態

## 白名單 / 角色（user_db.py）
- SQLite users 表，啟動時寫入種子資料（boss / engineer / approved）
- 角色定義：engineer > boss > approved > pending > blocked
- main.py 以 role（boss/engineer）或 LINE_*_USER_ID 判定是否為內部人員
- ⚠️ 尚未實作：聊天管理指令（通過/不要/名單/待審）、陌生人自動 pending + 通知老闆審核。
  user_db.py 已備 approve_user / list_pending / add_pending 等函式，但 main.py 尚未接上

## 查詢能力（query_wms.py / query_money.py）
- 模組支援：查庫存、低庫存、進出貨、訂單摘要、月收支、支出分類/明細、帳款狀態
- ⚠️ 目前僅「低庫存」「月收支」被定時推播使用；其餘查詢與「聊天即時查詢」尚未接入 main.py

## 客服模式觸發文字
產品介紹、我要備料、工程服務、常見問題、聯絡方式、服務流程 → 固定回覆
其他文字 → Claude AI 自由對話

## 定時推播
- 每日 08:00 低庫存警報
- 每週一 08:30 月收支摘要

## Rich Menu
- rich_menu.py — 一次性腳本，建立客服圖文選單（需 Pillow）
- 執行：python rich_menu.py

## 分支策略
staging = 開發測試，master = 正式（Railway 自動部署）

## 開發規範
- 敏感資訊一律用環境變數，不寫死在程式碼
- 改完必須更新 CLAUDE.md、CHANGELOG.md、STATUS.md
- config.py 只放讀取 env 的程式（皆有預設值、不含機密），已納入版控
