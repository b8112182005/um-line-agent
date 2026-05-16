"""建立統一 Rich Menu（所有用戶同一套）。

執行方式：railway run python rich_menu.py
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

WEBSITE_URL = "https://yumo-website.vercel.app"

# === 統一選單（所有用戶）===
UNIFIED_MENU = {
    "size": {"width": 2500, "height": 1686},
    "selected": True,
    "name": "瑀墨助理選單",
    "chatBarText": "點我開啟選單",
    "areas": [
        {"bounds": {"x": 0, "y": 0, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "塗料部門"}},
        {"bounds": {"x": 1250, "y": 0, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "工程部門"}},
        {"bounds": {"x": 0, "y": 562, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "產品介紹"}},
        {"bounds": {"x": 1250, "y": 562, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "常見問題"}},
        {"bounds": {"x": 0, "y": 1124, "width": 1250, "height": 562},
         "action": {"type": "uri", "uri": WEBSITE_URL + "/portfolio", "label": "作品集"}},
        {"bounds": {"x": 1250, "y": 1124, "width": 1250, "height": 562},
         "action": {"type": "uri", "uri": WEBSITE_URL + "/order", "label": "線上備料"}},
    ],
}

UNIFIED_LABELS = [
    ("塗料部門", "工程部門"),
    ("產品介紹", "常見問題"),
    ("作品集", "線上備料"),
]


def _load_font(size: int = 56):
    for font_path in [
        "C:/Windows/Fonts/msjhbd.ttc",    # 微軟正黑體 Bold
        "C:/Windows/Fonts/msjh.ttc",      # 微軟正黑體
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _draw_rounded_rect(draw, xy, radius, fill):
    """畫圓角矩形"""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def generate_menu_image(labels, style, path):
    """產生 2500x1686 的選單圖片"""
    bg = style["bg"]
    card = style["card"]
    text_color = style["text"]
    accent = style["accent"]

    img = Image.new("RGB", (2500, 1686), bg)
    draw = ImageDraw.Draw(img)
    font = _load_font(56)
    small_font = _load_font(32)

    pad = 40        # 外邊距
    gap = 24        # 格子間距
    cell_w = (2500 - pad * 2 - gap) // 2
    cell_h = (1686 - pad * 2 - gap * 2) // 3

    for row_idx, (left, right) in enumerate(labels):
        for col_idx, label in enumerate([left, right]):
            x = pad + col_idx * (cell_w + gap)
            y = pad + row_idx * (cell_h + gap)

            # 卡片背景（圓角）
            _draw_rounded_rect(draw, (x, y, x + cell_w, y + cell_h), radius=28, fill=card)

            # 頂部裝飾線
            draw.rounded_rectangle(
                (x + cell_w // 2 - 40, y + 60, x + cell_w // 2 + 40, y + 66),
                radius=3, fill=accent,
            )

            # 文字
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = x + (cell_w - tw) // 2
            ty = y + (cell_h - th) // 2 + 20
            draw.text((tx, ty), label, fill=text_color, font=font)

    img.save(path, quality=95)
    logger.info(f"選單圖片已產生：{path}")
    return path


# 品牌藍風格
UNIFIED_STYLE = {
    "bg": "#1a3a5c",
    "card": "#2B5C8A",
    "text": "#ffffff",
    "accent": "#5cb8ff",
}


def _create_menu(definition, labels, style, img_name):
    """建立一個 Rich Menu 並上傳圖片"""
    resp = httpx.post(
        f"{LINE_API}/richmenu",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=definition, timeout=15,
    )
    resp.raise_for_status()
    menu_id = resp.json()["richMenuId"]
    logger.info(f"Rich Menu 已建立：{menu_id}（{definition['name']}）")

    img_path = generate_menu_image(labels, style, img_name)
    with open(img_path, "rb") as f:
        resp = httpx.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers={**HEADERS, "Content-Type": "image/png"},
            content=f.read(), timeout=30,
        )
    resp.raise_for_status()
    logger.info(f"圖片已上傳：{img_name}")
    return menu_id


def _link_menu_to_user(menu_id, user_id):
    """綁定 Rich Menu 到指定用戶"""
    resp = httpx.post(
        f"{LINE_API}/user/{user_id}/richmenu/{menu_id}",
        headers=HEADERS, timeout=15,
    )
    if resp.status_code == 200:
        logger.info(f"已綁定選單到用戶：{user_id[:8]}...")
    else:
        logger.warning(f"綁定失敗 {user_id[:8]}：{resp.status_code}")


def setup_rich_menus():
    """建立統一選單並設為所有人預設"""
    # 先刪除所有舊選單
    resp = httpx.get(f"{LINE_API}/richmenu/list", headers=HEADERS, timeout=15)
    if resp.status_code == 200:
        for menu in resp.json().get("richmenus", []):
            httpx.delete(f"{LINE_API}/richmenu/{menu['richMenuId']}", headers=HEADERS, timeout=15)
            logger.info(f"已刪除舊選單：{menu['richMenuId']}")

    # 建立統一選單並設為預設
    menu_id = _create_menu(UNIFIED_MENU, UNIFIED_LABELS, UNIFIED_STYLE, "rich_menu_unified.png")
    resp = httpx.post(f"{LINE_API}/user/all/richmenu/{menu_id}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    logger.info(f"統一選單已設為預設：{menu_id}")

    print(f"\n完成！統一選單：{menu_id}")
    return menu_id


if __name__ == "__main__":
    setup_rich_menus()
