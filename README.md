# 瑀墨 LINE Agent

LINE Bot 查詢助理，連接 WMS 倉儲系統與 UMmoney 會計系統，讓老闆直接用 LINE 查庫存、收支、帳款。

## 架構

```
LINE 訊息 → FastAPI Webhook → Ollama 意圖解析 → SQLite 查詢 → LINE 回覆
                                    ↓ (失敗時)
                              關鍵字 Fallback
```

## 功能

| 指令範例 | 功能 |
|----------|------|
| 虹牌庫存 | 查單項庫存 |
| 缺貨 / 低庫存 | 低庫存警報 |
| 最近進出貨 | 近 7 天進出貨 |
| 3月收支 | 月收支摘要 |
| 最近支出 | 近 7 天支出明細 |
| 3月支出分類 | 各類別支出 |
| 應收應付 | 帳款狀態 |

### 定時推播
- 每天 08:00 — 低庫存警報（有品項低於安全量才推）
- 每週一 08:30 — 上月收支摘要

## 環境需求

- Python 3.11+
- Ollama（本地 AI 意圖解析）

## 安裝

### 1. 安裝 Ollama 與模型

```bash
# 安裝 Ollama：https://ollama.com/download
ollama pull qwen2.5:7b
```

### 2. 安裝 Python 套件

```bash
cd um-line-agent
pip install -r requirements.txt
```

### 3. LINE Developers Console 設定

1. 到 [LINE Developers](https://developers.line.biz/) 建立 Provider
2. 建立 Messaging API Channel
3. 取得：
   - **Channel Secret**（Basic settings）
   - **Channel Access Token**（Messaging API → Issue）
4. Webhook URL 設為：`https://你的網域/callback`

### 4. 取得老闆 LINE User ID

啟動 bot 後，老闆傳任意訊息，查看 server log 中的 `userId`。
或到 LINE Developers Console → Messaging API → Your user ID。

### 5. 設定 config.py

編輯 `config.py` 或設定環境變數：

```bash
export LINE_CHANNEL_SECRET="你的 secret"
export LINE_CHANNEL_ACCESS_TOKEN="你的 token"
export LINE_BOSS_USER_ID="老闆的 user id"
export WMS_DB_PATH="/path/to/paint.db"
export MONEY_DB_PATH="/path/to/accounting.db"
```

### 6. Cloudflare Tunnel（免費，不需固定 IP）

```bash
# 安裝：https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:8000
```

會產生一個 `https://xxx.trycloudflare.com` 網址，貼到 LINE Webhook URL。

## 啟動

```bash
# 第一次先確認 schema
python db_inspect.py

# 啟動服務
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 測試

```bash
# 健康檢查
curl http://localhost:8000/health
```
