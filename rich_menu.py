"""建立客服用 Rich Menu 並設為預設。

執行方式：python rich_menu.py
只需執行一次，建立後 LINE 會記住。
"""
import logging
import httpx
from PIL import Image, ImageDraw, ImageFont
from config import LINE_CHANNEL_ACCESS_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINE_API = "https://api.line.me/v2/bot"
HEADERS = {
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
}

MENU_DEFINITION = {
    "size": {"width": 2500, "height": 1686},
    "selected": True,
    "name": "瑀墨助理選單",
    "chatBarText": "點我開啟選單",
    "areas": [
        {
            "bounds": {"x": 0, "y": 0, "width": 1250, "height": 562},
            "action": {"type": "message", "text": "產品介紹"},
        },
        {
            "bounds": {"x": 1250, "y": 0, "width": 1250, "height": 562},
            "action": {"type": "message", "text": "我要備料"},
        },
        {
            "bounds": {"x": 0, "y": 562, "width": 1250, "height": 562},
            "action": {"type": "message", "text": "工程服務"},
        },
        {
            "bounds": {"x": 1250, "y": 562, "width": 1250, "height": 562},
            "action": {"type": "message", "text": "常見問題"},
        },
        {
            "bounds": {"x": 0, "y": 1124, "width": 1250, "height": 562},
            "action": {"type": "message", "text": "聯絡方式"},
        },
        {
            "bounds": {"x": 1250, "y": 1124, "width": 1250, "height": 562},
            "action": {"type": "message", "text": "服務流程"},
        },
    ],
}

GRID_LABELS = [
    ("🎨 產品介紹", "📦 備料詢問"),
    ("🔧 工程服務", "❓ 常見問題"),
    ("📍 聯絡我們", "📋 服務流程"),
]

BG_COLOR = "#2B5C8A"
TEXT_COLOR = "#FFFFFF"
BORDER_COLOR = "#1E4060"


def generate_menu_image(path: str = "rich_menu.png"):
    """產生 2500x1686 的選單圖片"""
    img = Image.new("RGB", (2500, 1686), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 嘗試載入字型，fallback 到預設
    font = None
    for font_path in [
        "C:/Windows/Fonts/msjh.ttc",      # 微軟正黑體
        "C:/Windows/Fonts/mingliu.ttc",    # 新細明體
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]:
        try:
            font = ImageFont.truetype(font_path, 64)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    # 畫格線
    draw.line([(1250, 0), (1250, 1686)], fill=BORDER_COLOR, width=4)
    draw.line([(0, 562), (2500, 562)], fill=BORDER_COLOR, width=4)
    draw.line([(0, 1124), (2500, 1124)], fill=BORDER_COLOR, width=4)

    # 畫文字
    for row_idx, (left, right) in enumerate(GRID_LABELS):
        y_center = row_idx * 562 + 281
        for col_idx, label in enumerate([left, right]):
            x_center = col_idx * 1250 + 625
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (x_center - tw // 2, y_center - th // 2),
                label,
                fill=TEXT_COLOR,
                font=font,
            )

    img.save(path)
    logger.info(f"選單圖片已產生：{path}")
    return path


def create_rich_menu():
    """建立 Rich Menu 並設為預設"""
    # 1. 建立 Rich Menu
    resp = httpx.post(
        f"{LINE_API}/richmenu",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=MENU_DEFINITION,
        timeout=15,
    )
    resp.raise_for_status()
    menu_id = resp.json()["richMenuId"]
    logger.info(f"Rich Menu 已建立：{menu_id}")

    # 2. 上傳圖片
    img_path = generate_menu_image()
    with open(img_path, "rb") as f:
        resp = httpx.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers={**HEADERS, "Content-Type": "image/png"},
            content=f.read(),
            timeout=30,
        )
    resp.raise_for_status()
    logger.info("選單圖片已上傳")

    # 3. 設為預設
    resp = httpx.post(
        f"{LINE_API}/user/all/richmenu/{menu_id}",
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    logger.info(f"已設為預設 Rich Menu：{menu_id}")

    return menu_id


if __name__ == "__main__":
    menu_id = create_rich_menu()
    print(f"完成！Rich Menu ID: {menu_id}")
