# STATUS — um-line-agent

> 最後更新：2026-03-29

## 部署狀態

| 環境 | 狀態 | 網址 |
|------|------|------|
| Railway | ✅ 已部署 | https://um-line-agent-production.up.railway.app |
| LINE Webhook | ✅ 已設定 | /callback |

## 功能狀態

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

## 已知限制

- 定時推播使用 APScheduler in-process，Railway 重啟後排程重置（不影響功能，會自動重建）
- LINE 回覆上限 5000 字，超過會截斷
