#!/usr/bin/env python3
# 產生本次 session 成果示意圖
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
def f(sz): return ImageFont.truetype(FONT, sz)

# 調色
BG       = (18, 18, 34)
CARD     = (30, 31, 52)
GOLD     = (201, 168, 76)
WHITE    = (238, 238, 242)
DIM      = (160, 162, 180)
W = 1280
PAD = 56

groups = [
    ("安全強化", (224, 101, 76), [
        "小墨不再自報底層模型身份（進 LLM 前硬攔模型探詢）",
        "Prompt injection／越獄防護強化，並修掉誤殺正常客人的詞",
        "Webhook 簽章 fail-closed ＋ 事件 timestamp 防重放",
    ]),
    ("防騷擾 / 防濫用", (43, 138, 201), [
        "「找真人」通知冷卻＋去重，防止灌爆老闆",
        "圖片(Vision)／語音(Whisper) 納入每日額度，防成本型濫用",
        "記憶體狀態定期清理，避免長期洩漏",
    ]),
    ("Bug 修復", (63, 179, 107), [
        "備料訂單不再掉單（持久化不受通知冷卻影響）",
        "客服傳照片後不再「失憶」，後續提問記得照片",
        "語音額度精準計費，擋下並發繞過上限",
    ]),
    ("工程 / 維運", (155, 123, 208), [
        "新增 GitHub Actions CI，PR 自動跑語法檢查＋測試",
        "修復早已脫節的 test_bot.py（29 項全綠）",
        "CLAUDE.md 準確性校對，標清未接線的功能",
    ]),
    ("新功能", (201, 168, 76), [
        "內部人員可切換「客服模式 ⇄ 內部同仁模式」＋查目前模式",
    ]),
]

f_title = f(46)
f_sub   = f(24)
f_grp   = f(30)
f_item  = f(24)
f_foot  = f(22)
f_badge = f(20)

def wrap(text, font, maxw, draw):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= maxw:
            cur += ch
        else:
            lines.append(cur); cur = ch
    if cur: lines.append(cur)
    return lines

# 預先量測高度
tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
inner = W - PAD * 2
text_x_off = 84
item_maxw = inner - text_x_off - 30
item_lh = 38
grp_head_h = 64

card_layouts = []
for name, color, items in groups:
    h = grp_head_h + 14
    wrapped_items = []
    for it in items:
        wl = wrap(it, f_item, item_maxw, tmp)
        wrapped_items.append(wl)
        h += len(wl) * item_lh + 8
    h += 18
    card_layouts.append((name, color, wrapped_items, h))

header_h = 200
footer_h = 96
total_h = header_h + sum(c[3] + 22 for c in card_layouts) + footer_h + 30

img = Image.new("RGB", (W, total_h), BG)
d = ImageDraw.Draw(img)

# 頂部金色條
d.rectangle([0, 0, W, 8], fill=GOLD)

# 標題
d.text((PAD, 44), "瑀墨助理 LINE Bot", font=f_title, fill=GOLD)
d.text((PAD, 108), "本次優化成果總覽", font=f(34), fill=WHITE)
d.text((PAD, 156), "6 個 PR 全數合併上線 · 2026-06-01", font=f_sub, fill=DIM)

y = header_h
for name, color, wrapped_items, h in card_layouts:
    # 卡片
    d.rounded_rectangle([PAD, y, W - PAD, y + h], radius=18, fill=CARD)
    # 左側色條
    d.rounded_rectangle([PAD, y, PAD + 10, y + h], radius=6, fill=color)
    # 群組標題 + 色點
    cy = y + 22
    d.ellipse([PAD + 34, cy + 6, PAD + 34 + 22, cy + 28], fill=color)
    d.text((PAD + 74, cy), name, font=f_grp, fill=WHITE)
    # 項目
    iy = y + grp_head_h + 6
    for wl in wrapped_items:
        d.ellipse([PAD + text_x_off - 26, iy + 11, PAD + text_x_off - 14, iy + 23], fill=color)
        for li, line in enumerate(wl):
            d.text((PAD + text_x_off, iy), line, font=f_item, fill=WHITE if li == 0 else DIM)
            iy += item_lh
        iy += 8
    y += h + 22

# Footer
d.text((PAD, y + 8),
       "待辦：WMS／UMmoney 庫存・收支查詢（目前休眠，未接線）— 後續再詳細調整",
       font=f_foot, fill=DIM)
d.text((W - PAD - 220, y + 8), "Claude Code", font=f_badge, fill=GOLD)

out = "/home/user/um-line-agent/assets/session_achievements.png"
img.save(out)
print("saved", out, img.size)
