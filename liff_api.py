"""LIFF 線上叫貨 BFF — 熟客在 LINE 內填表單下單，轉成 WMS 待確認訂單

流程：熟客在 LINE 開 LIFF 頁 → 前端帶 idToken 呼叫本路由 →
驗證身份(限 approved 熟客) → 代理 WMS 查品項/建待確認單/查歷史 → 通知老闆。
"""
import logging
import httpx
from fastapi import APIRouter, Request, HTTPException

from config import LINE_LOGIN_CHANNEL_ID, LIFF_ID, LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID
from user_db import get_role
from api_client import wms_get, wms_post
from push import push_message

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
    return [{
        "id": p.get("id"),
        "brand": p.get("brand", ""),
        "name": p.get("name", ""),
        "color_name": p.get("color_name", ""),
        "spec": p.get("spec", ""),
        "unit": p.get("unit", "桶"),
    } for p in products]


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

    payload = {
        "line_user_id": user["user_id"],
        "customer_name": user["name"],
        "phone": body.get("phone", ""),
        "note": body.get("note", ""),
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
    notify_text = (
        "🛒 新線上叫貨單\n"
        f"單號：{order_number}\n"
        f"熟客：{user['name']}\n"
        "━━━━━━━━━━\n"
        + "\n".join(lines) + "\n"
        "━━━━━━━━━━\n"
        f"共 {len(clean_items)} 項 / {_qty(total_qty)} 件\n"
        "👉 請到 WMS 後台確認出貨"
    )
    for boss_id in (LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID):
        if not boss_id:
            continue
        try:
            await push_message(boss_id, notify_text)
        except Exception as e:
            logger.error(f"通知 {boss_id[:8]} 失敗：{e}")

    return {"order_number": order_number, "message": "訂單已送出，專員確認後會與您聯繫"}
