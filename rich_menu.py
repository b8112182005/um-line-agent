"""建立 Rich Menu（依角色分兩套）並綁定用戶。

執行方式：python rich_menu.py
"""
import logging
import httpx
from PIL import Image, ImageDraw, ImageFont
from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID
from user_db import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINE_API = "https://api.line.me/v2/bot"
HEADERS = {
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
}

# === 老闆/工程師選單 ===
BOSS_MENU = {
    "size": {"width": 2500, "height": 1686},
    "selected": True,
    "name": "瑀墨助理 — 管理選單",
    "chatBarText": "點我開啟選單",
    "areas": [
        {"bounds": {"x": 0, "y": 0, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "缺貨"}},
        {"bounds": {"x": 1250, "y": 0, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "最近支出"}},
        {"bounds": {"x": 0, "y": 562, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "應收應付"}},
        {"bounds": {"x": 1250, "y": 562, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "最近進出貨"}},
        {"bounds": {"x": 0, "y": 1124, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "名單"}},
        {"bounds": {"x": 1250, "y": 1124, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "待審"}},
    ],
}

BOSS_LABELS = [
    ("缺貨警報", "最近支出"),
    ("應收應付", "進出貨紀錄"),
    ("白名單管理", "待審核"),
]

# === 客戶選單 ===
# 官網 URL（佔位，之後替換為正式網址）
WEBSITE_URL = "https://yumo-website.vercel.app"

CUSTOMER_MENU = {
    "size": {"width": 2500, "height": 1686},
    "selected": True,
    "name": "瑀墨助理 — 客戶選單",
    "chatBarText": "點我開啟選單",
    "areas": [
        {"bounds": {"x": 0, "y": 0, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "產品介紹"}},
        {"bounds": {"x": 1250, "y": 0, "width": 1250, "height": 562},
         "action": {"type": "uri", "uri": WEBSITE_URL + "/order", "label": "線上備料"}},
        {"bounds": {"x": 0, "y": 562, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "工程服務"}},
        {"bounds": {"x": 1250, "y": 562, "width": 1250, "height": 562},
         "action": {"type": "uri", "uri": WEBSITE_URL + "/portfolio", "label": "作品集"}},
        {"bounds": {"x": 0, "y": 1124, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "常見問題"}},
        {"bounds": {"x": 1250, "y": 1124, "width": 1250, "height": 562},
         "action": {"type": "message", "text": "聯絡方式"}},
    ],
}

CUSTOMER_LABELS = [
    ("產品介紹", "線上備料"),
    ("工程服務", "作品集"),
    ("常見問題", "聯絡我們"),
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


# 深色管理風格
BOSS_STYLE = {
    "bg": "#0f0f1a",
    "card": "#1a1a2e",
    "text": "#e0e0e0",
    "accent": "#4a9eff",
}

# 品牌藍客戶風格
CUSTOMER_STYLE = {
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
    """建立兩套選單 + 綁定"""
    # 先刪除所有舊選單
    resp = httpx.get(f"{LINE_API}/richmenu/list", headers=HEADERS, timeout=15)
    if resp.status_code == 200:
        for menu in resp.json().get("richmenus", []):
            httpx.delete(f"{LINE_API}/richmenu/{menu['richMenuId']}", headers=HEADERS, timeout=15)
            logger.info(f"已刪除舊選單：{menu['richMenuId']}")

    # 客戶選單（預設）
    customer_id = _create_menu(CUSTOMER_MENU, CUSTOMER_LABELS, CUSTOMER_STYLE, "rich_menu_customer.png")
    resp = httpx.post(f"{LINE_API}/user/all/richmenu/{customer_id}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    logger.info(f"客戶選單已設為預設：{customer_id}")

    # 管理選單
    boss_id = _create_menu(BOSS_MENU, BOSS_LABELS, BOSS_STYLE, "rich_menu_boss.png")

    # 綁定老闆/工程師
    for uid in [LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID]:
        if uid:
            _link_menu_to_user(boss_id, uid)

    print(f"\n完成！")
    print(f"  客戶選單（預設）：{customer_id}")
    print(f"  管理選單（老闆）：{boss_id}")
    return boss_id, customer_id


if __name__ == "__main__":
    init_db(LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID)
    setup_rich_menus()
