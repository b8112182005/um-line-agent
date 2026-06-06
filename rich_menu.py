"""建立兩套 Rich Menu：
- 非熟客版（5 格，無線上備料）→ 設為預設，所有新客人都看這個
- 熟客版（6 格，含線上備料）→ 內部人員審核為熟客後，由 main.py 綁定到該客人

執行方式：railway run python rich_menu.py
建立後 menu_id 會寫入 users.db 的 settings 表（regular_menu_id / vip_menu_id），
供 main.py 執行階段 per-user 綁定使用。
"""
import logging
import httpx
from PIL import Image, ImageDraw, ImageFont
from config import LINE_CHANNEL_ACCESS_TOKEN
from user_db import init_db, set_setting

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINE_API = "https://api.line.me/v2/bot"
HEADERS = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
WEBSITE_URL = "https://yumo-website.vercel.app"
# 熟客「線上備料」一鍵直接開 LIFF 下單表單（LIFF 已上線，免兩段式）
LIFF_ORDER_URL = "https://liff.line.me/2010310048-cDA0VIKv"

W, H = 2500, 1686
HALF = W // 2
THIRD = H // 3

# === 非熟客選單（5 格：上排 2×2 + 底部整列作品集，無線上備料）===
REGULAR_MENU = {
    "size": {"width": W, "height": H},
    "selected": True,
    "name": "瑀墨助理選單",
    "chatBarText": "點我開啟選單",
    "areas": [
        {"bounds": {"x": 0, "y": 0, "width": HALF, "height": THIRD}, "action": {"type": "message", "text": "塗料部門"}},
        {"bounds": {"x": HALF, "y": 0, "width": HALF, "height": THIRD}, "action": {"type": "message", "text": "工程部門"}},
        {"bounds": {"x": 0, "y": THIRD, "width": HALF, "height": THIRD}, "action": {"type": "message", "text": "產品介紹"}},
        {"bounds": {"x": HALF, "y": THIRD, "width": HALF, "height": THIRD}, "action": {"type": "message", "text": "常見問題"}},
        {"bounds": {"x": 0, "y": THIRD * 2, "width": W, "height": THIRD}, "action": {"type": "uri", "uri": WEBSITE_URL, "label": "作品集"}},
    ],
}
REGULAR_CELLS = [
    {"label": "塗料部門", "x": 0, "y": 0, "w": HALF, "h": THIRD},
    {"label": "工程部門", "x": HALF, "y": 0, "w": HALF, "h": THIRD},
    {"label": "產品介紹", "x": 0, "y": THIRD, "w": HALF, "h": THIRD},
    {"label": "常見問題", "x": HALF, "y": THIRD, "w": HALF, "h": THIRD},
    {"label": "作品集", "x": 0, "y": THIRD * 2, "w": W, "h": THIRD},
]

# === 熟客選單（6 格：含線上備料）===
# 「線上備料」用 uri 直接開 LIFF 下單表單（一鍵進表單）。
# main.py 仍保留 message 文字攔截，供使用者打字「線上備料」時回連結 + 非熟客導引。
VIP_MENU = {
    "size": {"width": W, "height": H},
    "selected": True,
    "name": "瑀墨熟客選單",
    "chatBarText": "點我開啟選單",
    "areas": [
        {"bounds": {"x": 0, "y": 0, "width": HALF, "height": THIRD}, "action": {"type": "message", "text": "塗料部門"}},
        {"bounds": {"x": HALF, "y": 0, "width": HALF, "height": THIRD}, "action": {"type": "message", "text": "工程部門"}},
        {"bounds": {"x": 0, "y": THIRD, "width": HALF, "height": THIRD}, "action": {"type": "message", "text": "產品介紹"}},
        {"bounds": {"x": HALF, "y": THIRD, "width": HALF, "height": THIRD}, "action": {"type": "message", "text": "常見問題"}},
        {"bounds": {"x": 0, "y": THIRD * 2, "width": HALF, "height": THIRD}, "action": {"type": "uri", "uri": WEBSITE_URL, "label": "作品集"}},
        {"bounds": {"x": HALF, "y": THIRD * 2, "width": HALF, "height": THIRD}, "action": {"type": "uri", "uri": LIFF_ORDER_URL, "label": "線上備料"}},
    ],
}
VIP_CELLS = [
    {"label": "塗料部門", "x": 0, "y": 0, "w": HALF, "h": THIRD},
    {"label": "工程部門", "x": HALF, "y": 0, "w": HALF, "h": THIRD},
    {"label": "產品介紹", "x": 0, "y": THIRD, "w": HALF, "h": THIRD},
    {"label": "常見問題", "x": HALF, "y": THIRD, "w": HALF, "h": THIRD},
    {"label": "作品集", "x": 0, "y": THIRD * 2, "w": HALF, "h": THIRD},
    {"label": "線上備料", "x": HALF, "y": THIRD * 2, "w": HALF, "h": THIRD},
]

STYLE = {"bg_image": "rich_menu_bg.png", "text": "#ffffff", "line_color": "#C9A84C"}


def _load_font(size: int = 96):
    for font_path in [
        "C:/Windows/Fonts/msjhbd.ttc",
        "C:/Windows/Fonts/msjh.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_menu_image(cells, style, path):
    """依 cells（每格 x/y/w/h/label）產生 2500×1686 選單圖，支援任意格佈局。"""
    if style.get("bg_image"):
        try:
            img = Image.open(style["bg_image"]).convert("RGB").resize((W, H), Image.LANCZOS)
        except (FileNotFoundError, OSError):
            img = Image.new("RGB", (W, H), style.get("bg", "#1a3a5c"))
    else:
        img = Image.new("RGB", (W, H), style.get("bg", "#1a3a5c"))

    # 半透明暗色遮罩（讓文字更清晰）
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov = ImageDraw.Draw(overlay)
    for c in cells:
        ov.rectangle((c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]), fill=(0, 0, 0, 70))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    line_color = style.get("line_color", "#C9A84C")
    text_color = style.get("text", "#ffffff")
    font = _load_font(96)

    # 每格框線
    for c in cells:
        draw.rectangle((c["x"], c["y"], c["x"] + c["w"] - 1, c["y"] + c["h"] - 1),
                       outline=line_color, width=4)
    # 標籤置中（陰影 + 主色）
    for c in cells:
        bbox = draw.textbbox((0, 0), c["label"], font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = c["x"] + (c["w"] - tw) // 2
        ty = c["y"] + (c["h"] - th) // 2
        draw.text((tx + 3, ty + 3), c["label"], fill=(0, 0, 0), font=font)
        draw.text((tx, ty), c["label"], fill=text_color, font=font)

    img.save(path, format="JPEG", quality=85, optimize=True)
    logger.info(f"選單圖片已產生：{path}")
    return path


def _create_menu(definition, cells, style, img_name):
    """建立一個 Rich Menu 並上傳圖片，回傳 menu_id。"""
    resp = httpx.post(
        f"{LINE_API}/richmenu",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=definition, timeout=15,
    )
    resp.raise_for_status()
    menu_id = resp.json()["richMenuId"]
    logger.info(f"Rich Menu 已建立：{menu_id}（{definition['name']}）")

    img_path = generate_menu_image(cells, style, img_name)
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
    """綁定 Rich Menu 到指定用戶（LINE linkRichMenuIdToUser）。"""
    resp = httpx.post(
        f"{LINE_API}/user/{user_id}/richmenu/{menu_id}",
        headers=HEADERS, timeout=15,
    )
    if resp.status_code == 200:
        logger.info(f"已綁定選單到用戶：{user_id[:8]}...")
        return True
    logger.warning(f"綁定失敗 {user_id[:8]}：{resp.status_code} {resp.text}")
    return False


def setup_rich_menus():
    """建立兩套選單：非熟客版設為預設，熟客版供綁定。menu_id 存入 settings 表。"""
    init_db()  # 確保 settings 表存在

    # 先刪除所有舊選單
    resp = httpx.get(f"{LINE_API}/richmenu/list", headers=HEADERS, timeout=15)
    if resp.status_code == 200:
        for menu in resp.json().get("richmenus", []):
            httpx.delete(f"{LINE_API}/richmenu/{menu['richMenuId']}", headers=HEADERS, timeout=15)
            logger.info(f"已刪除舊選單：{menu['richMenuId']}")

    # 非熟客版（5 格）→ 設為所有人預設
    regular_id = _create_menu(REGULAR_MENU, REGULAR_CELLS, STYLE, "rich_menu_regular.jpg")
    set_setting("regular_menu_id", regular_id)
    resp = httpx.post(f"{LINE_API}/user/all/richmenu/{regular_id}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    logger.info(f"非熟客選單已設為預設：{regular_id}")

    # 熟客版（6 格）→ 供 per-user 綁定
    vip_id = _create_menu(VIP_MENU, VIP_CELLS, STYLE, "rich_menu_vip.jpg")
    set_setting("vip_menu_id", vip_id)
    logger.info(f"熟客選單已建立：{vip_id}")

    print(f"\n完成！\n  非熟客版（預設，5格）：{regular_id}\n  熟客版（6格含備料）：{vip_id}")
    print("menu_id 已寫入 users.db settings 表")
    return regular_id, vip_id


if __name__ == "__main__":
    setup_rich_menus()
