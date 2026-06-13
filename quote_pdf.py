"""產生「瑀墨塗料報價單」PDF（A4 直式，含金額），版面參考上游班傑明摩爾報價單。

特色：
- reportlab 向量輸出，文字可選取、列印清晰（非圖片）。
- CJK 字型用 repo 內已 bundle 的 NotoSansTC-Regular.ttf 嵌入，Railway 無系統中文字型也能正常顯示。
- 黑金品牌；上方標題＋公司資訊雙欄，中段品項表（序/產品編號/產品名稱/色號/數量/單位/單價/金額），
  下方總計、匯款資訊、注意事項、公司／簽章頁尾。

對外介面與 quote_image.build_quote_image 對齊：build_quote_pdf(order) -> 存檔絕對路徑 / None。

★ 公司、匯款資訊集中在下方 SELLER 常數，請依實際資料填寫（標 TODO 者為待補）。
"""
import os
import time
import secrets
import logging

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

_BASE = os.path.dirname(os.path.abspath(__file__))
_FONT_PATH = os.path.join(_BASE, "assets", "fonts", "NotoSansTC-Regular.ttf")
_LOGO_PATH = os.path.join(_BASE, "assets", "logo_gold.png")
_OUT_DIR = os.path.join(_BASE, "assets", "quotes")

# ── 賣方（瑀墨塗料）資訊：請依實際資料填寫 ──────────────────────────────
SELLER = {
    "name": "瑀墨塗料有限公司",
    "name_en": "Yumo Coating Co., Ltd.",
    "tax_id": "60309610",
    "rep": "葉采鑫",
    "address": "台中市北屯區仁美里環中路一段519號",
    "phone": "04-24220614",
    "sales_default": "",                 # 預設負責業務（order 未帶時用，目前由表單帶入）
    "quote_valid_days": 30,              # 報價效期天數
    "bank_name": "土地銀行",
    "bank_code": "0051220",
    "bank_account_name": "瑀墨塗料有限公司",
    "bank_account_no": "122001029191",
}

# 注意事項（瑀墨自有版本，依商品特性可再調整）
NOTES = [
    "一、本報價金額為商品參考價，未含運費（另計／另議）；實際以專員確認為準。",
    "二、本公司產品為客製化商品，出貨後恕無法退換。",
    "三、產品應直接施工，不可摻水或添加稀釋劑，以免顏色、光澤、性能劣化。",
    "四、運送方式與運費以雙方確認為準；滿一定金額另有免運優惠，詳洽專員。",
]

# 品牌色
INK = colors.HexColor("#1B1B1F")
GOLD = colors.HexColor("#C8A45C")
GOLD_SOFT = colors.HexColor("#CDB682")
GRAY = colors.HexColor("#787880")
LINE_C = colors.HexColor("#D2D6DC")
DARK = colors.HexColor("#282C34")
STRIPE = colors.HexColor("#F7F8FA")
NOTE_C = colors.HexColor("#5A5A5A")

_FONT = "NotoSansTC"
_font_registered = False


def _ensure_font():
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(TTFont(_FONT, _FONT_PATH))
        _font_registered = True


def _money(v):
    try:
        return f"{int(round(float(v))):,}"
    except Exception:
        return "—"


def _qty(v):
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:g}"
    except Exception:
        return "" if v is None else str(v)


def _amt(it):
    """品項金額：有 amount 用 amount，否則 數量×單價。"""
    amt = it.get("amount")
    if amt is None:
        try:
            amt = float(it.get("qty") or 0) * float(it.get("price") or 0)
        except Exception:
            amt = 0
    return amt


def build_quote_pdf(order: dict):
    """order: {order_number, date, customer_name, contact_person, phone, tax_id,
              company_address, delivery_method, site_address, sales_person,
              total_amount, items:[{name|product_name, code, color, qty, unit, price, amount, note}]}
    回傳存檔絕對路徑，失敗回 None。"""
    # 延後 import（避免頂層 import 名稱問題）
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, Flowable
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

    try:
        _ensure_font()
        os.makedirs(_OUT_DIR, exist_ok=True)
        _cleanup_old(7)

        items = order.get("items", []) or []

        # 樣式
        def st(name, size, color=DARK, align=TA_LEFT, leading=None):
            return ParagraphStyle(name, fontName=_FONT, fontSize=size,
                                  textColor=color, alignment=align,
                                  leading=leading or size + 3)
        p_label = st("lbl", 8, GRAY)
        p_val = st("val", 9, DARK)
        p_cell = st("cell", 8.5, DARK)
        p_cell_r = st("cellr", 8.5, DARK, TA_RIGHT)
        p_cell_c = st("cellc", 8.5, DARK, TA_CENTER)
        p_th = st("th", 8.5, GOLD, TA_CENTER)
        p_note = st("note", 8, NOTE_C, leading=12)

        on = order.get("order_number", "quote")
        out_path = os.path.join(_OUT_DIR, f"{on}-{secrets.token_hex(8)}.pdf")

        doc = SimpleDocTemplate(
            out_path, pagesize=A4,
            leftMargin=14 * mm, rightMargin=14 * mm,
            topMargin=12 * mm, bottomMargin=12 * mm,
            title=f"瑀墨塗料報價單 {on}", author=SELLER["name"],
        )
        usable_w = doc.width
        story = []

        # ── 標題列：報價單 + 公司名（左）/ logo（右）──
        title_left = [
            [Paragraph("報　價　單", st("t1", 20, INK))],
            [Paragraph(f"{SELLER['name']}　<font color='#787880' size=8>{SELLER['name_en']}</font>",
                       st("t2", 11, INK))],
        ]
        left_tbl = Table(title_left, colWidths=[usable_w * 0.66])
        left_tbl.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ]))
        logo_cell = ""
        if os.path.exists(_LOGO_PATH):
            try:
                logo_cell = Image(_LOGO_PATH, width=14 * mm, height=14 * mm)
            except Exception:
                logo_cell = ""
        head = Table([[left_tbl, logo_cell]],
                     colWidths=[usable_w * 0.78, usable_w * 0.22])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, 0), (-1, -1), 1.4, GOLD),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(head)
        story.append(Spacer(1, 8))

        # ── 客戶／報價資訊（label/value 四欄格）──
        def L(t):
            return Paragraph(t, p_label)

        def V(t):
            return Paragraph((t if t not in (None, "") else "—"), p_val)

        valid = order.get("quote_valid") or ""
        info_rows = [
            [L("客戶名稱"), V(order.get("customer_name")), L("報價單號"), V(on)],
            [L("聯絡人"), V(order.get("contact_person")), L("報價日期"), V(order.get("date"))],
            [L("聯絡電話"), V(order.get("phone")), L("報價效期"), V(valid)],
            [L("統一編號"), V(order.get("tax_id")), L("負責業務"),
             V(order.get("sales_person") or SELLER["sales_default"])],
            [L("公司地址"), V(order.get("company_address")), L("送貨方式"), V(order.get("delivery_method"))],
            [L("案場地址"), V(order.get("site_address")), L("收款方式"), V(order.get("payment") or "匯款")],
        ]
        lw, vw = 52, (usable_w - 52 * 2) / 2
        info = Table(info_rows, colWidths=[lw, vw, lw, vw])
        info.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, LINE_C),
            ("BACKGROUND", (0, 0), (0, -1), STRIPE),
            ("BACKGROUND", (2, 0), (2, -1), STRIPE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]))
        story.append(info)
        story.append(Spacer(1, 10))

        # ── 報價內容（品項表）──
        # 欄：序/產品編號/產品名稱/色號/數量/單位/單價/金額
        # 動態欄位：有資料才顯示。線上備料目前無 產品編號/色號（WMS 已移除），故自動隱藏；
        # 備註為線上備料表單既有欄位，有填才出現。未來 WMS 若再帶色號等欄位亦自動支援。
        def _has(*keys):
            return any(it.get(k) for it in items for k in keys)

        show_code = _has("code")
        show_color = _has("color")
        show_note = _has("note", "notes")

        # (header, 取值函式, 樣式, 固定寬;0=彈性吃剩餘)
        cols = [("序", lambda i, it: str(i), p_cell_c, 22)]
        if show_code:
            cols.append(("產品編號", lambda i, it: str(it.get("code") or "—"), p_cell, 68))
        cols.append(("產品名稱", lambda i, it: str(it.get("name") or it.get("product_name") or ""), p_cell, 0))
        if show_color:
            cols.append(("色號", lambda i, it: str(it.get("color") or "—"), p_cell, 84))
        cols.append(("數量", lambda i, it: _qty(it.get("qty")), p_cell_r, 38))
        cols.append(("單位", lambda i, it: str(it.get("unit") or ""), p_cell_c, 38))
        cols.append(("單價", lambda i, it: (_money(it.get("price")) if it.get("price") not in (None, "", 0) else "—"), p_cell_r, 64))
        cols.append(("金額", lambda i, it: _money(_amt(it)), p_cell_r, 72))
        if show_note:
            cols.append(("備註", lambda i, it: str(it.get("note") or it.get("notes") or ""), p_cell, 88))

        col_w = [c[3] for c in cols]
        flex_idx = col_w.index(0)
        col_w[flex_idx] = usable_w - sum(w for w in col_w if w)  # 產品名稱吃剩餘寬
        n_cols = len(cols)

        header = [Paragraph(c[0], p_th) for c in cols]
        data = [header]
        total_amt = 0.0
        total_qty = 0.0
        for i, it in enumerate(items, 1):
            total_amt += float(_amt(it) or 0)
            try:
                total_qty += float(it.get("qty") or 0)
            except Exception:
                pass
            data.append([Paragraph(getter(i, it), style) for (_h, getter, style, _w) in cols])
        if not items:
            data.append([Paragraph("（無品項）", p_cell)] + [Paragraph("", p_cell)] * (n_cols - 1))

        tbl = Table(data, colWidths=col_w, repeatRows=1)
        ts = [
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE_C),
            ("BOX", (0, 0), (-1, -1), 0.6, INK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for r in range(1, len(data)):
            if r % 2 == 0:
                ts.append(("BACKGROUND", (0, r), (-1, r), STRIPE))
        tbl.setStyle(TableStyle(ts))
        story.append(tbl)

        # ── 總計列 ──
        grand = order.get("total_amount")
        grand = float(grand) if grand not in (None, "") else total_amt
        tot = Table(
            [[Paragraph(f"合計　共 {len(items)} 項", st("tl", 9, GOLD_SOFT)),
              Paragraph(f"總數量 {_qty(total_qty)}", st("tq", 9, GOLD_SOFT, TA_CENTER)),
              Paragraph("總金額(含稅)", st("tm", 9.5, GOLD, TA_RIGHT)),
              Paragraph(f"NT$ {_money(grand)}", st("tv", 12, GOLD, TA_RIGHT))]],
            colWidths=[usable_w - 70 - 130 - 110, 130, 110, 70],
        )
        tot.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), INK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(tot)
        story.append(Spacer(1, 12))

        # ── 匯款資訊 ──
        if SELLER["bank_account_no"]:
            bank_lines = (
                f"匯款銀行：{SELLER['bank_name']}　銀行代號：{SELLER['bank_code']}<br/>"
                f"戶名：{SELLER['bank_account_name']}　帳號：{SELLER['bank_account_no']}"
            )
            bank = Table([[Paragraph("匯款資訊", st("bk", 9, INK)),
                           Paragraph(bank_lines, st("bkv", 8.5, DARK, leading=14))]],
                         colWidths=[60, usable_w - 60])
            bank.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, LINE_C),
                ("BACKGROUND", (0, 0), (0, 0), STRIPE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(bank)
            story.append(Spacer(1, 10))

        # ── 注意事項 ──
        story.append(Paragraph("注意事項", st("nh", 9, INK)))
        story.append(Spacer(1, 2))
        for n in NOTES:
            story.append(Paragraph(n, p_note))
        story.append(Spacer(1, 14))

        # ── 頁尾：公司資訊 + 簽章 ──
        seller_block = (
            f"{SELLER['name']}<br/>"
            f"統一編號：{SELLER['tax_id']}　負責人：{SELLER['rep']}<br/>"
            f"{SELLER['address']}"
            + (f"<br/>電話：{SELLER['phone']}" if SELLER["phone"] else "")
        )
        sign_block = "客戶確認簽章 / 日期：<br/><br/>______________________"
        foot = Table(
            [[Paragraph(seller_block, st("sb", 8.5, DARK, leading=13)),
              Paragraph(sign_block, st("sg", 8.5, DARK, leading=14))]],
            colWidths=[usable_w * 0.58, usable_w * 0.42],
        )
        foot.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (-1, 0), 0.8, GOLD),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
        ]))
        story.append(foot)
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"製表日期：{order.get('date', '')}　|　製表：{order.get('sales_person') or SELLER['sales_default'] or '—'}　|　頁次：1/1",
            st("meta", 7.5, GRAY)))

        doc.build(story)
        return out_path
    except Exception as e:
        logger.error(f"產生報價單 PDF 失敗：{e}")
        return None


def _cleanup_old(days: int = 7):
    """刪除 days 天前的舊報價單檔（含 png/pdf），避免長期堆積。"""
    try:
        cutoff = time.time() - days * 86400
        for f in os.listdir(_OUT_DIR):
            if f.endswith((".pdf", ".png")):
                fp = os.path.join(_OUT_DIR, f)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass
    except Exception:
        pass


if __name__ == "__main__":
    # 用上游報價單同款資料產生樣張，方便檢視版面
    sample = {
        "order_number": "YM202606130001",
        "date": "2026/06/13",
        "quote_valid": "2026/07/13",
        "customer_name": "敦品室內裝修工程有限公司",
        "contact_person": "張紘瑀",
        "phone": "0987-852157",
        "tax_id": "60402453",
        "company_address": "台中市北屯區南興二路75號",
        "site_address": "台中市南屯區懷德路50號",
        "delivery_method": "自取",
        "payment": "匯款",
        "sales_person": "葉采鑫",
        "total_amount": 12960,
        "items": [
            {"code": "V3922X1G", "name": "康滿得系列-緞光-2X1G", "color": "HC-77 Alexandria Beige",
             "qty": 1, "unit": "加侖", "price": 4800, "amount": 4320},
            {"code": "V3922X1G", "name": "康滿得系列-緞光-2X1G", "color": "2138-40 Carolina Gull",
             "qty": 1, "unit": "加侖", "price": 4800, "amount": 4320},
            {"code": "V3924X1G", "name": "康滿得系列-緞光-4X1G", "color": "HC-154 Hale Navy",
             "qty": 1, "unit": "加侖", "price": 4800, "amount": 4320},
        ],
    }
    p = build_quote_pdf(sample)
    print("OUT:", p)
