"""產生「瑀墨報價單」圖片（銷貨明細表樣式，含金額），線上備料完成後推給熟客。

設計：白底、黑金品牌；上方標題列，中段雙欄客戶資訊，下方品項表（序/品項/數量/單位/單價/金額），
底部總計。畫在足夠高的畫布上，最後裁切到實際內容高度，避免高度估算誤差。
"""
import os
import time
import secrets
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


def _money(v):
    try:
        return f"{int(round(float(v))):,}"
    except Exception:
        return "—"


def build_quote_image(order: dict):
    """order: {order_number, date, customer_name, contact_person, phone, tax_id,
              company_address, delivery_method, site_address, sales_person,
              total_amount, items:[{name, qty, unit, price, amount}]}
    回傳存檔絕對路徑，失敗回 None。"""
    try:
        os.makedirs(_OUT_DIR, exist_ok=True)
        _cleanup_old(7)
        W, pad = 900, 32
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

        # ── 品項表（序/品項/數量/單位/單價/金額）──
        def rt(x_right, ky, text, font, fill):
            t = "" if text is None else str(text)
            d.text((x_right - d.textlength(t, font=font), ky), t, font=font, fill=fill)

        items_top = y
        x_seq, x_name = pad + 12, pad + 50
        x_qty_r = W - pad - 290          # 數量(右對齊)
        x_unit_l = W - pad - 275         # 單位(左)
        x_price_r = W - pad - 110        # 單價(右對齊)
        x_amt_r = W - pad - 10           # 金額(右對齊)
        d.rectangle([pad, y, W - pad, y + head_h], fill=INK)
        d.text((x_seq, y + 11), "序", font=_font(15), fill=GOLD)
        d.text((x_name, y + 11), "品項", font=_font(15), fill=GOLD)
        rt(x_qty_r, y + 11, "數量", _font(15), GOLD)
        d.text((x_unit_l, y + 11), "單位", font=_font(15), fill=GOLD)
        rt(x_price_r, y + 11, "單價", _font(15), GOLD)
        rt(x_amt_r, y + 11, "金額", _font(15), GOLD)
        y += head_h

        name_w = x_qty_r - x_name - 50
        total = 0.0
        if not items:
            d.text((x_name, y + 9), "（無品項）", font=_font(15), fill=GRAY)
            y += row_h
        for i, it in enumerate(items, 1):
            if i % 2 == 0:
                d.rectangle([pad, y, W - pad, y + row_h], fill=STRIPE)
            amt = it.get("amount")
            if amt is None:
                try:
                    amt = float(it.get("qty") or 0) * float(it.get("price") or 0)
                except Exception:
                    amt = 0
            total += float(amt or 0)
            d.text((x_seq, y + 9), str(i), font=_font(15), fill=DARK)
            d.text((x_name, y + 9), _fit(d, it.get("name", ""), _font(15), name_w), font=_font(15), fill=DARK)
            rt(x_qty_r, y + 9, it.get("qty", ""), _font(15), DARK)
            d.text((x_unit_l, y + 9), str(it.get("unit", "")), font=_font(15), fill=DARK)
            rt(x_price_r, y + 9, _money(it.get("price")) if it.get("price") not in (None, "", 0) else "—", _font(15), DARK)
            rt(x_amt_r, y + 9, _money(amt), _font(15), DARK)
            y += row_h
        d.rectangle([pad, items_top, W - pad, y], outline=LINE, width=1)

        # ── 總計列 ──
        grand = order.get("total_amount")
        grand = float(grand) if grand not in (None, "") else total
        th = 42
        d.rectangle([pad, y, W - pad, y + th], fill=INK)
        d.text((x_name, y + 12), f"合計　共 {len(items)} 項", font=_font(16), fill=GOLD_SOFT)
        rt(x_price_r, y + 12, "總計", _font(16), GOLD)
        rt(x_amt_r, y + 11, "NT$ " + _money(grand), _font(18), GOLD)
        y += th

        # ── 底部 ──
        y += 18
        d.text((pad, y), "※ 本報價為商品金額參考，實際以專員確認為準（未含運費／另議）。", font=_font(14), fill=NOTE)
        y += 26
        d.text((pad, y), "瑀墨塗料有限公司　|　線上備料報價", font=_font(13), fill=GRAY)
        y += 24

        img = img.crop((0, 0, W, min(H, y + pad)))
        # 檔名加隨機 token，避免單號可被猜到而外洩他人報價單（含姓名/電話/地址）
        on = order.get("order_number", "quote")
        out_path = os.path.join(_OUT_DIR, f"{on}-{secrets.token_hex(8)}.png")
        img.save(out_path, "PNG")
        return out_path
    except Exception as e:
        logger.error(f"產生報價單圖失敗：{e}")
        return None


def _cleanup_old(days: int = 7):
    """刪除 days 天前的舊報價單圖，避免長期堆積。"""
    try:
        cutoff = time.time() - days * 86400
        for f in os.listdir(_OUT_DIR):
            if f.endswith(".png"):
                fp = os.path.join(_OUT_DIR, f)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass
    except Exception:
        pass
