"""產生「瑀墨報價單」圖片（銷貨明細表樣式，無金額），線上備料完成後推給熟客。

設計：白底、黑金品牌；上方標題列，中段雙欄客戶資訊，下方品項表（序/品項/數量/單位），
底部註「金額另計」。畫在足夠高的畫布上，最後裁切到實際內容高度，避免高度估算誤差。
"""
import os
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_BASE = os.path.dirname(os.path.abspath(__file__))
_FONT_PATH = os.path.join(_BASE, "assets", "fonts", "NotoSansTC-Regular.ttf")
_LOGO_PATH = os.path.join(_BASE, "assets", "logo_gold.png")
_OUT_DIR = os.path.join(_BASE, "assets", "quotes")

INK = (27, 27, 31)
GOLD = (200, 164, 92)
GOLD_SOFT = (205, 182, 130)
GRAY = (120, 120, 128)
LINE = (210, 214, 220)
DARK = (40, 44, 52)
NOTE = (176, 99, 58)
STRIPE = (247, 248, 250)

_font_cache = {}


def _font(size: int):
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(_FONT_PATH, size)
        except Exception:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def _fit(d, text, font, max_w):
    """過長文字截斷加…以符合寬度。"""
    text = "" if text is None else str(text)
    if d.textlength(text, font=font) <= max_w:
        return text
    while text and d.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def build_quote_image(order: dict):
    """order: {order_number, date, customer_name, contact_person, phone, tax_id,
              company_address, delivery_method, site_address, sales_person,
              items:[{name, qty, unit}]}
    回傳存檔絕對路徑，失敗回 None。"""
    try:
        os.makedirs(_OUT_DIR, exist_ok=True)
        W, pad = 820, 32
        items = order.get("items", []) or []
        row_h, head_h = 38, 40

        # 足夠高的畫布，最後裁切
        H = 360 + max(1, len(items)) * row_h + 160
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)

        # ── 標題列 ──
        header_h = 92
        d.rectangle([0, 0, W, header_h], fill=INK)
        d.rectangle([0, header_h, W, header_h + 4], fill=GOLD)
        x_title = pad
        try:
            logo = Image.open(_LOGO_PATH).convert("RGBA").resize((48, 48))
            img.paste(logo, (pad, 22), logo)
            x_title = pad + 62
        except Exception:
            pass
        d.text((x_title, 24), "瑀墨塗料　報價單", font=_font(30), fill=GOLD)
        d.text((x_title, 62), "YUMO PAINT ｜ 線上備料", font=_font(14), fill=GOLD_SOFT)

        y = header_h + 22

        # ── 客戶資訊（雙欄 + 全寬地址）──
        def kv(cx, ky, label, value, vw):
            d.text((cx, ky), label, font=_font(14), fill=GRAY)
            d.text((cx + 70, ky), _fit(d, value if value else "—", _font(15), vw), font=_font(15), fill=DARK)

        colL, colR = pad, W // 2 + 6
        vw = (W // 2) - pad - 76
        pairs = [
            ("單號", order.get("order_number", ""), "日期", order.get("date", "")),
            ("客戶", order.get("customer_name", ""), "聯絡人", order.get("contact_person", "")),
            ("電話", order.get("phone", ""), "統編", order.get("tax_id", "")),
        ]
        for lL, vL, lR, vR in pairs:
            kv(colL, y, lL, vL, vw)
            kv(colR, y, lR, vR, vw)
            y += 34
        full_vw = W - pad - 76 - pad
        kv(colL, y, "取貨", order.get("delivery_method", ""), full_vw); y += 34
        kv(colL, y, "公司", order.get("company_address", ""), full_vw); y += 34
        kv(colL, y, "案場", order.get("site_address", ""), full_vw); y += 34

        y += 8
        d.line([pad, y, W - pad, y], fill=LINE, width=1)
        y += 14

        # ── 品項表 ──
        items_top = y
        x_seq, x_name = pad + 12, pad + 54
        x_qty, x_unit = W - pad - 150, W - pad - 70
        d.rectangle([pad, y, W - pad, y + head_h], fill=INK)
        d.text((x_seq, y + 11), "序", font=_font(15), fill=GOLD)
        d.text((x_name, y + 11), "品項", font=_font(15), fill=GOLD)
        d.text((x_qty, y + 11), "數量", font=_font(15), fill=GOLD)
        d.text((x_unit, y + 11), "單位", font=_font(15), fill=GOLD)
        y += head_h

        name_w = x_qty - x_name - 12
        if not items:
            d.text((x_name, y + 9), "（無品項）", font=_font(15), fill=GRAY)
            y += row_h
        for i, it in enumerate(items, 1):
            if i % 2 == 0:
                d.rectangle([pad, y, W - pad, y + row_h], fill=STRIPE)
            d.text((x_seq, y + 9), str(i), font=_font(15), fill=DARK)
            d.text((x_name, y + 9), _fit(d, it.get("name", ""), _font(15), name_w), font=_font(15), fill=DARK)
            d.text((x_qty, y + 9), str(it.get("qty", "")), font=_font(15), fill=DARK)
            d.text((x_unit, y + 9), str(it.get("unit", "")), font=_font(15), fill=DARK)
            y += row_h
        d.rectangle([pad, items_top, W - pad, y], outline=LINE, width=1)

        # ── 底部 ──
        y += 18
        d.text((pad, y), "※ 金額另計，專員確認後會與您報價並聯繫。", font=_font(15), fill=NOTE)
        y += 28
        d.text((pad, y), f"共 {len(items)} 項　|　瑀墨塗料有限公司", font=_font(13), fill=GRAY)
        y += 24

        img = img.crop((0, 0, W, min(H, y + pad)))
        out_path = os.path.join(_OUT_DIR, f"{order.get('order_number', 'quote')}.png")
        img.save(out_path, "PNG")
        return out_path
    except Exception as e:
        logger.error(f"產生報價單圖失敗：{e}")
        return None
