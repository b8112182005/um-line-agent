import os
from dotenv import load_dotenv

load_dotenv()

# === LINE Bot ===
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_BOSS_USER_ID = os.getenv("LINE_BOSS_USER_ID", "")         # 葉采鑫（塗料部門）
LINE_ENG_BOSS_USER_ID = os.getenv("LINE_ENG_BOSS_USER_ID", "")  # 張紘瑀（工程部門）
LINE_ENGINEER_USER_ID = os.getenv("LINE_ENGINEER_USER_ID", "")  # 開發者

# === 白名單（逗號分隔的 LINE User ID）===
BOSS_USER_IDS = [
    uid.strip()
    for uid in os.getenv("BOSS_USER_IDS", "").split(",")
    if uid.strip()
]

# === 系統 API（Railway P2 正式環境）===
WMS_API_URL = os.getenv("WMS_API_URL", "https://um-wms-p2-production.up.railway.app")
MONEY_API_URL = os.getenv("MONEY_API_URL", "https://ummoney-p2-production.up.railway.app")

# === API 登入帳號 ===
API_USERNAME = os.getenv("API_USERNAME", "")
API_PASSWORD = os.getenv("API_PASSWORD", "")

# === Claude API ===
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# === OpenAI API（語音轉文字 Whisper）===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
