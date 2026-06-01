# STATUS — um-line-agent

> 最後更新：2026-05-31

## 部署狀態

| 環境 | 狀態 | 網址 |
|------|------|------|
| Railway | ✅ 已部署 | https://um-line-agent-production.up.railway.app |
| LINE Webhook | ✅ 已設定 | /callback |

## 身份分流

| 角色 | 判斷方式 | 功能 |
|------|----------|------|
| 老闆（白名單）| BOSS_USER_IDS 環境變數 | 內部查詢（庫存/帳務） |
| 一般客戶 | 非白名單 | AI 客服「小墨」+ 圖文選單 |

## 功能狀態 — 老闆模式

| 功能 | 狀態 | 說明 |
|------|------|------|
| Claude 意圖解析 | ✅ | claude-haiku-4-5-20251001 |
| 關鍵字 fallback | ✅ | Claude 掛掉時自動降級 |
| 口語化回覆 | ✅ | Claude 將查詢結果轉口語 |
| 查庫存 | ✅ | WMS API /api/products |
| 低庫存警報 | ✅ | WMS API /api/alerts |
| 進出貨紀錄 | ✅ | WMS API /api/transactions |
| 訂單摘要 | ✅ | WMS API /api/orders |
| 月收支（PnL）| ✅ | UMmoney API /api/reports/pnl |
| 支出分類 | ✅ | UMmoney API /api/invoices/in + /api/expenses |
| 支出明細 | ✅ | UMmoney API /api/expenses |
| 帳款狀態 | ✅ | UMmoney API /api/dashboard |
| 每日庫存推播 | ✅ | 每天 08:00 |
| 每週收支推播 | ✅ | 每週一 08:30 |

## 功能狀態 — 客服模式

| 功能 | 狀態 | 說明 |
|------|------|------|
| AI 客服「小墨」| ✅ | Claude Haiku 對話，200字內回覆 |
| 圖文選單 | ✅ | 6格 Rich Menu（需執行 rich_menu.py 建立）|
| 產品介紹 | ✅ | 固定回覆 |
| 備料詢問 | ✅ | 引導收集資訊 |
| 工程服務 | ✅ | 介紹瑀墨工程 |
| 常見問題 | ✅ | Top 5 FAQ |
| 聯絡方式 | ✅ | 地址/營業時間 |
| 服務流程 | ✅ | 諮詢→報價→備料→配送→退料 |

## 安全狀態

| 機制 | 狀態 | 說明 |
|------|------|------|
| 模型身份硬攔截 | ✅ | 進 LLM 前攔下「你是什麼模型」等探詢 |
| Prompt injection 攔截 | ✅ | 關鍵字黑名單（客服模式） |
| 老闆通知冷卻＋去重 | ✅ | 10 分鐘，防「找真人」灌爆 |
| 圖片/語音額度 | ✅ | 納入每日 50 則上限 |
| 簽章 fail-closed＋防重放 | ✅ | 缺 secret 拒絕、舊事件丟棄 |
| 記憶體狀態清理 | ✅ | 閒置 24h 淘汰 |

## 已知限制

- 定時推播使用 APScheduler in-process，Railway 重啟後排程重置（不影響功能，會自動重建）
- LINE 回覆上限 5000 字，超過會截斷
- 客服模式目前無多輪記憶，每次獨立對話
- Rich Menu 需手動執行 rich_menu.py 建立（一次性）
