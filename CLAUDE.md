# um-line-agent

## 專案概述
瑀墨塗料 LINE Bot 助理（瑀墨助理），讓老闆在 LINE 上直接查詢倉儲和會計數據。

## 架構
- FastAPI + uvicorn
- Claude API (claude-haiku-4-5-20251001) 做意圖解析 + 口語化回覆
- 關鍵字 fallback（Claude API 掛掉時自動降級）
- 透過 HTTP 呼叫 WMS P2 API + UMmoney P2 API（唯讀查詢）
- APScheduler 定時推播

## 部署
- Railway: um-line-agent-production.up.railway.app (port 8080)
- LINE Channel: 瑀墨助理（UMIM Provider）
- Webhook: https://um-line-agent-production.up.railway.app/callback

## 環境變數
LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, LINE_BOSS_USER_ID,
WMS_API_URL, MONEY_API_URL, API_USERNAME, API_PASSWORD, ANTHROPIC_API_KEY

## 支援查詢
查庫存、低庫存警報、進出貨紀錄、訂單摘要、月收支、支出分類、支出明細、帳款狀態

## 定時推播
- 每日 08:00 低庫存警報
- 每週一 08:30 月收支摘要

## 分支策略
master = 正式（Railway 自動部署）

## 開發規範
- 敏感資訊一律用環境變數，不寫死在程式碼
- 改完必須更新 CLAUDE.md、CHANGELOG.md、STATUS.md
- config.py 不上傳 GitHub（在 .gitignore）
