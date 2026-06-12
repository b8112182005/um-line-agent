"""LIFF 線上叫貨 BFF — 熟客在 LINE 內填表單下單，轉成 WMS 待確認訂單

流程：熟客在 LINE 開 LIFF 頁 → 前端帶 idToken 呼叫本路由 →
驗證身份(限 approved 熟客) → 代理 WMS 查品項/建待確認單/查歷史 → 通知老闆。
"""
import os
import re
import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Request, HTTPException

from config import LINE_LOGIN_CHANNEL_ID, LIFF_ID, LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID, PUBLIC_BASE_URL
from user_db import get_role, get_wms_customer, get_note
from api_client import wms_get, wms_post
from push import push_message, push_image
from quote_image import build_quote_image


def _valid_phone(s: str) -> bool:
    """台灣手機(09+8碼) 或 市話(0+9~10碼)；擋全同數字/連號。"""
    d = re.sub(r"[\s\-()]", "", s or "")
    if not re.fullmatch(r"0\d{8,9}", d):
        return False
    if re.fullmatch(r"(\d)\1+", d):
        return False
    if d in "01234567890123" or d in "09876543210":
        return False
    return True


def _valid_name(s: str) -> bool:
    """至少 2 字、非純數字、且含中文或英文字母。"""
    s = (s or "").strip()
    if len(s) < 2 or s.isdigit():
        return False
    return bool(re.search(r"[一-龥A-Za-z]", s))


def _valid_addr(s: str) -> bool:
    """送到案場地址：要像真地址。至少 6 字、含數字門牌、含道路/地段字，
    且門牌數字不超過 4 位、無同數字連按（擋 5199999999、9999 之類）。"""
    s = (s or "").strip()
    if len(s) < 6 or not re.search(r"\d", s):
        return False
    if not re.search(r"[路街巷弄段道里村鄰]", s):   # 要有道路/地段類字，不能只有「號」
        return False
    if re.search(r"\d{5,}", s):                      # 門牌/巷段號碼 >4 位 = 不合理
        return False
    if re.search(r"(\d)\1{3,}", s):                  # 同一數字連 4 次(9999)= 亂填
        return False
    return True


async def _resolve_bound_customer(line_user_id: str) -> dict:
    """取得熟客綁定的 WMS 客戶完整資料（未綁定/失敗回空 dict）。"""
    cid = get_wms_customer(line_user_id)
    if not cid:
        return {}
    try:
        data = await wms_get("/api/customers")
        rows = data if isinstance(data, list) else data.get("data", [])
        for c in rows:
            if str(c.get("id")) == str(cid):
                return c
    except Exception as e:
        logger.warning(f"撈綁定客戶失敗 {cid}：{e}")
    return {}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/liff", tags=["LIFF 線上叫貨"])

LINE_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"


async def _verify(request: Request) -> dict:
    """驗證 LIFF idToken，回 {user_id, name}。限熟客(approved)使用。"""
    id_token = request.headers.get("X-Line-IdToken", "")
    if not id_token:
        raise HTTPException(status_code=401, detail="缺少身份憑證")
    if not LINE_LOGIN_CHANNEL_ID:
        raise HTTPException(status_code=500, detail="伺服器未設定 LINE_LOGIN_CHANNEL_ID")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_VERIFY_URL, data={
            "id_token": id_token,
            "client_id": LINE_LOGIN_CHANNEL_ID,
        })
    if resp.status_code != 200:
        logger.warning(f"idToken 驗證失敗：{resp.status_code} {resp.text}")
        raise HTTPException(status_code=401, detail="LINE 身份驗證失敗")
    payload = resp.json()
    uid = payload.get("sub", "")
    name = payload.get("name", "")
    if get_role(uid) not in ("approved", "boss", "engineer"):
        raise HTTPException(status_code=403, detail="此功能限熟客使用，請洽專員開通")
    return {"user_id": uid, "name": name}


@router.get("/config")
async def liff_config():
    """前端取得 LIFF ID（不寫死在 HTML）"""
    return {"liff_id": LIFF_ID}


@router.get("/catalog")
async def catalog(request: Request, search: str = ""):
    """查品項目錄（只回下單需要的欄位，不外洩價格/成本）"""
    await _verify(request)
    params = {"search": search} if search else {}
    data = await wms_get("/api/products", params=params)
    products = data if isinstance(data, list) else data.get("products", data.get("data", []))
    # 只顯示有定價的品項；無價=尚未開賣的占位，不給客人看到（避免下到沒價的單）
    return [{
        "id": p.get("id"),
        "brand": p.get("brand", ""),
        "name": p.get("name", ""),
        "color_name": p.get("color_name", ""),
        "spec": p.get("spec", ""),
        "unit": p.get("unit", "桶"),
    } for p in products if (p.get("price") or 0) > 0]


@router.get("/history")
async def history(request: Request):
    """上次您訂的：回最近一筆訂單的品項，供一鍵帶入"""
    user = await _verify(request)
    orders = await wms_get("/api/orders", params={"line_user_id": user["user_id"], "limit": 1})
    rows = orders if isinstance(orders, list) else []
    if not rows:
        return {"items": []}
    detail = await wms_get(f"/api/orders/{rows[0]['id']}")
    items = [{
        "product_id": it.get("product_id"),
        "product_name": it.get("product_name", ""),
        "quantity": it.get("quantity", 0),
        "unit": it.get("unit", "桶"),
    } for it in detail.get("items", [])]
    return {
        "order_number": rows[0].get("order_number", ""),
        "date": rows[0].get("order_date", ""),
        "items": items,
    }


@router.post("/order")
async def submit_order(request: Request):
    """送出叫貨單 → 建 WMS 待確認訂單 → 通知老闆"""
    user = await _verify(request)
    body = await request.json()
    clean_items = []
    for it in body.get("items", []):
        qty = float(it.get("quantity", 0) or 0)
        if qty <= 0:
            continue
        clean_items.append({
            "product_id": it.get("product_id"),
            "product_name": it.get("product_name", ""),
            "quantity": qty,
            "unit": it.get("unit", "桶"),
            "notes": it.get("notes", ""),
        })
    if not clean_items:
        raise HTTPException(status_code=400, detail="品項數量需大於 0")

    pickup = body.get("delivery_method", "")  # '自取' or '公司代送'
    site = body.get("site_address", "")
    sales = body.get("sales_person", "")
    phone = body.get("phone", "")
    # 必填欄位格式查證（後端強制，前端被繞過也擋）
    if not _valid_name(sales):
        raise HTTPException(status_code=400, detail="請填寫正確的現場負責人姓名")
    if not _valid_phone(phone):
        raise HTTPException(status_code=400, detail="請填寫正確的聯絡電話（手機 09 開頭 10 碼，或市話含區碼）")
    if pickup == "公司代送" and not _valid_addr(site):
        raise HTTPException(status_code=400, detail="請填寫完整正確的案場地址（含路名與門牌號，例：○○路123號）")
    # 綁定的 WMS 客戶 → 自動帶統編/公司地址/聯絡人/電話到報價單
    cust = await _resolve_bound_customer(user["user_id"])
    payload = {
        "line_user_id": user["user_id"],
        "customer_name": user["name"],
        "phone": body.get("phone", "") or cust.get("phone", ""),
        "note": body.get("note", ""),
        "site_address": site,
        "delivery_address": site,
        "delivery_method": pickup,
        "sales_person": body.get("sales_person", ""),
        "customer_id": cust.get("id"),
        "contact_person": cust.get("contact") or sales,  # 綁定用WMS聯絡人,否則用現場負責人(不用暱稱)
        "tax_id": cust.get("tax_id", ""),
        "company_address": cust.get("company_address", ""),
        "items": clean_items,
    }
    result = await wms_post("/api/orders/pending", json=payload)
    order_number = result.get("order_number", "")

    # 通知老闆（塗料部門）+ 工程師：一筆一行、編號、含數量單位，方便閱讀
    def _qty(n):
        n = float(n)
        return str(int(n)) if n == int(n) else str(n)
    lines = [
        f"{i}. {it['product_name']}　{_qty(it['quantity'])}{it.get('unit', '')}".rstrip()
        for i, it in enumerate(clean_items, 1)
    ]
    total_qty = sum(float(it["quantity"]) for it in clean_items)
    pickup_label = "自取" if pickup == "自取" else "送到案場"
    extra = f"取貨：{pickup_label}"
    if site:
        extra += f"\n案場：{site}"
    if payload["sales_person"]:
        extra += f"\n承辦：{payload['sales_person']}"
    notify_text = (
        "🛒 新線上叫貨單\n"
        f"單號：{order_number}\n"
        f"熟客：{user['name']}\n"
        f"{extra}\n"
        "━━━━━━━━━━\n"
        + "\n".join(lines) + "\n"
        "━━━━━━━━━━\n"
        f"共 {len(clean_items)} 項 / {_qty(total_qty)} 件\n"
        "👉 請到 WMS 後台放行出貨"
    )
    for boss_id in (LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID):
        if not boss_id:
            continue
        try:
            await push_message(boss_id, notify_text)
        except Exception as e:
            logger.error(f"通知 {boss_id[:8]} 失敗：{e}")

    # 報價單照片推給熟客本人（無金額）；產圖或推圖失敗時退回文字回條
    sent_image = False
    try:
        # 客戶名：綁定 WMS 客戶用真實名 → 其次用備註(真實姓名/公司) → 最後才暱稱
        try:
            note_name = get_note(user["user_id"]) or ""
        except Exception:
            note_name = ""
        quote_order = {
            "order_number": order_number,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "customer_name": cust.get("name") or note_name or user["name"],
            "contact_person": sales,   # 聯絡人＝表單填的現場負責人（不再用暱稱、不跟客戶重複）
            "phone": payload["phone"],
            "tax_id": payload["tax_id"],
            "company_address": payload["company_address"],
            "delivery_method": pickup_label,
            "site_address": site,
            "items": [
                {"name": it["product_name"], "qty": _qty(it["quantity"]), "unit": it.get("unit", "")}
                for it in clean_items
            ],
        }
        path = build_quote_image(quote_order)
        if path:
            url = f"{PUBLIC_BASE_URL}/assets/quotes/{os.path.basename(path)}"
            await push_image(user["user_id"], url)
            await push_message(
                user["user_id"],
                f"✅ 已收到叫貨單 {order_number}，報價單如上圖 👆\n💰 金額另計，專員確認後會與您聯繫。",
            )
            sent_image = True
    except Exception as e:
        logger.error(f"報價單照片推播失敗 {user['user_id'][:8]}：{e}")

    if not sent_image:
        receipt = (
            "✅ 已收到您的叫貨單\n"
            f"單號：{order_number}\n"
            f"{extra}\n"
            "━━━━━━━━━━\n"
            + "\n".join(lines) + "\n"
            "━━━━━━━━━━\n"
            f"共 {len(clean_items)} 項 / {_qty(total_qty)} 件\n"
            "💰 金額另計，專員確認後會與您聯繫。"
        )
        try:
            await push_message(user["user_id"], receipt)
        except Exception as e:
            logger.error(f"回條推播失敗 {user['user_id'][:8]}：{e}")

    return {"order_number": order_number, "message": "訂單已送出，報價單已傳到您的聊天室"}
