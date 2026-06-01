# um-line-agent

## 專案概述
瑀墨助理 LINE Bot，讓老闆在 LINE 上直接查詢倉儲和會計數據。

## 架構
- FastAPI + uvicorn
- Claude API (claude-haiku-4-5-20251001) 做意圖解析 + 口語化回覆
- 關鍵字 fallback（Claude API 掛掉時自動降級）
- 透過 HTTP 呼叫 WMS P2 API + UMmoney P2 API（唯讀查詢）
- APScheduler 定時推播

## 部署
- Railway: um-line-agent-production.up.railway.app (port 8080)
- LINE Channel: 瑀墨助理
- Webhook: https://um-line-agent-production.up.railway.app/callback

## 身份分流
- 白名單（BOSS_USER_IDS）→ 老闆模式：意圖解析 → 查 WMS/UMmoney → 口語化回覆
- 非白名單 → 客服模式：AI 客服「小墨」+ 圖文選單固定回覆
- 內部人員（boss/engineer）模式切換指令：「客服模式」切到客人視角體驗小墨、「內部模式」切回內部同仁、「目前模式」查目前狀態（記憶體記錄，重啟自動回內部模式）

## 環境變數
LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, LINE_BOSS_USER_ID,
LINE_ENGINEER_USER_ID（工程師最高權限）,
WMS_API_URL, MONEY_API_URL, API_USERNAME, API_PASSWORD, ANTHROPIC_API_KEY
ALLOW_UNSIGNED_WEBHOOK（僅本機開發；正式環境勿設，缺 secret 時一律拒絕）

## 安全機制（customer.py / main.py）
- 身份保護：`_is_identity_question` 在進 LLM 前硬攔模型探詢，回固定話術（不自報 Claude/Anthropic）
- prompt injection：`_is_injection` 關鍵字攔截（客服模式）
- 老闆通知冷卻：`_can_notify_staff`（10 分鐘）防「找真人」灌爆
- 額度：每人每日 50 則，圖片/語音也納入計算
- webhook：HMAC 簽章 fail-closed + 事件 timestamp 防重放
- 記憶體：`_maybe_cleanup` 定期淘汰閒置狀態

## 白名單管理
- SQLite users 表（user_db.py）取代環境變數 BOSS_USER_IDS
- 角色：engineer > boss > approved > pending > blocked
- 老闆/工程師可透過聊天管理：通過/不要/名單/待審
- 陌生人自動 pending → push 通知老闆審核

## 支援查詢（老闆模式）
查庫存、低庫存警報、進出貨紀錄、訂單摘要、月收支、支出分類、支出明細、帳款狀態

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
- config.py 不上傳 GitHub（在 .gitignore）
