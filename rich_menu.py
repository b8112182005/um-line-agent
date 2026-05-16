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
    W, H = 2500, 1686
    cell_w = W // 2
    cell_h = H // 3

    # 底圖
    if style.get("bg_image"):
        img = Image.open(style["bg_image"]).convert("RGB").resize((W, H), Image.LANCZOS)
    else:
        img = Image.new("RGB", (W, H), style.get("bg", "#1a3a5c"))

    # 半透明暗色遮罩（讓文字更清晰）
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    for row in range(3):
        for col in range(2):
            x, y = col * cell_w, row * cell_h
            ov_draw.rectangle((x, y, x + cell_w, y + cell_h), fill=(0, 0, 0, 70))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    line_color = style.get("line_color", "#C9A84C")
    text_color = style.get("text", "#ffffff")
    font = _load_font(96)

    # 金色格線
    draw.line([(cell_w, 0), (cell_w, H)], fill=line_color, width=4)
    draw.line([(0, cell_h), (W, cell_h)], fill=line_color, width=4)
    draw.line([(0, cell_h * 2), (W, cell_h * 2)], fill=line_color, width=4)

    # 文字標籤（陰影 + 主色）
    for row_idx, (left, right) in enumerate(labels):
        for col_idx, label in enumerate([left, right]):
            x, y = col_idx * cell_w, row_idx * cell_h
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = x + (cell_w - tw) // 2
            ty = y + (cell_h - th) // 2
            draw.text((tx + 3, ty + 3), label, fill=(0, 0, 0, 160), font=font)
            draw.text((tx, ty), label, fill=text_color, font=font)

    img.save(path, format="JPEG", quality=85, optimize=True)
    logger.info(f"選單圖片已產生：{path}")
    return path


# 品牌背景圖風格
UNIFIED_STYLE = {
    "bg_image": "rich_menu_bg.png",  # 底圖
    "text": "#ffffff",
    "line_color": "#C9A84C",         # 金色格線
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
            headers={**HEADERS, "Content-Type": "image/jpeg"},
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
    menu_id = _create_menu(UNIFIED_MENU, UNIFIED_LABELS, UNIFIED_STYLE, "rich_menu_unified.jpg")
    resp = httpx.post(f"{LINE_API}/user/all/richmenu/{menu_id}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    logger.info(f"統一選單已設為預設：{menu_id}")

    print(f"\n完成！統一選單：{menu_id}")
    return menu_id


if __name__ == "__main__":
    setup_rich_menus()
