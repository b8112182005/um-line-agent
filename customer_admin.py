"""客戶管理頁 BFF — 工程師/老闆專用的客戶名單管理（搜尋/分頁/設熟客）。

不走 LIFF，改用 bot 簽發的「短效簽章連結」：
  內部人員打「客戶名單」→ bot 回 https://.../customers?t=<token>
  網頁帶 t 呼叫本路由 → 驗簽 + 確認 boss/engineer → 回客戶資料 / 改身分。
token 以 LINE_CHANNEL_SECRET HMAC 簽章，預設 2 小時有效。
"""
import time
import hmac
import base64
import hashlib
import logging

from fastapi import APIRouter, Request, HTTPException

from config import LINE_CHANNEL_SECRET
from user_db import get_role, list_customers, count_customers, set_role, set_note, set_wms_customer
from api_client import wms_get

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/staff", tags=["客戶管理"])

PAGE_SIZE = 30
_TTL = 2 * 3600  # 2 小時


def make_token(user_id: str, ttl: int = _TTL) -> str:
    """簽發短效存取 token（給內部人員的客戶管理連結用）。"""
    exp = int(time.time()) + ttl
    payload = f"{user_id}.{exp}"
    sig = hmac.new(LINE_CHANNEL_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def _verify_token(token: str) -> str | None:
    """驗簽 + 檢查過期，回 user_id；失敗回 None。"""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, exp, sig = raw.rsplit(".", 2)
        good = hmac.new(LINE_CHANNEL_SECRET.encode(), f"{user_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, good):
            return None
        if int(exp) < int(time.time()):
            return None
        return user_id
    except Exception:
        return None


def _auth(request: Request) -> str:
    """驗證連結 token + 限 boss/engineer，回操作者 user_id。"""
    token = request.query_params.get("t", "")
    uid = _verify_token(token)
    if not uid:
        raise HTTPException(status_code=401, detail="連結已失效，請回 LINE 重新打「客戶名單」取得新連結")
    if get_role(uid) not in ("boss", "engineer"):
        raise HTTPException(status_code=403, detail="此功能限內部人員")
    return uid


@router.get("/customers")
async def customers(request: Request, status: str = "approved", search: str = "", offset: int = 0):
    """查客戶清單（分頁）。status: approved=熟客 / pending=非熟客。"""
    _auth(request)
    role = status if status in ("approved", "pending", "blocked") else ""
    search = search.strip()
    rows = list_customers(role=role, search=search, limit=PAGE_SIZE, offset=max(0, offset))
    # 解析綁定的 WMS 客戶名稱（用 id→name 對照），失敗不影響清單
    wms_map = {}
    if any(r.get("wms_customer_id") for r in rows):
        try:
            data = await wms_get("/api/customers")
            for c in (data if isinstance(data, list) else data.get("data", [])):
                wms_map[str(c.get("id"))] = c.get("name", "")
        except Exception as e:
            logger.warning(f"取 WMS 客戶對照失敗：{e}")
    return {
        "items": [{
            "user_id": r["user_id"], "name": r["display_name"] or "(未命名)",
            "role": r["role"], "note": r["note"],
            "wms_customer_id": r.get("wms_customer_id", ""),
            "wms_customer_name": wms_map.get(str(r.get("wms_customer_id")), ""),
        } for r in rows],
        "offset": offset,
        "page_size": PAGE_SIZE,
        "has_more": len(rows) == PAGE_SIZE,
        "counts": {
            "approved": count_customers(role="approved", search=search),
            "pending": count_customers(role="pending", search=search),
        },
    }


@router.post("/customers/role")
async def set_customer_role(request: Request):
    """設/取消熟客。body: {user_id, action: 'approve'|'demote'}。"""
    _auth(request)
    body = await request.json()
    target = body.get("user_id", "")
    action = body.get("action", "")
    if not target or action not in ("approve", "demote"):
        raise HTTPException(status_code=400, detail="參數錯誤")
    new_role = "approved" if action == "approve" else "pending"
    if not set_role(target, new_role):
        raise HTTPException(status_code=400, detail="無法變更（對象可能是內部人員或不存在）")
    # 同步切換該客戶的 rich menu（延後匯入避免循環相依）
    try:
        from main import _switch_menu
        await _switch_menu("vip" if action == "approve" else "regular", target)
    except Exception as e:
        logger.warning(f"設身分後切換選單失敗：{e}")
    return {"ok": True, "role": new_role}


@router.post("/customers/note")
async def set_customer_note(request: Request):
    """設定客戶備註（標真實姓名/公司/電話）。body: {user_id, note}。"""
    _auth(request)
    body = await request.json()
    target = body.get("user_id", "")
    note = (body.get("note") or "").strip()[:200]
    if not target:
        raise HTTPException(status_code=400, detail="參數錯誤")
    set_note(target, note)
    return {"ok": True, "note": note}


@router.get("/wms-customers")
async def search_wms_customers(request: Request, search: str = ""):
    """搜尋 WMS 客戶（給綁定用）。比對名稱/統編/電話。"""
    _auth(request)
    s = search.strip().lower()
    try:
        data = await wms_get("/api/customers")
    except Exception as e:
        logger.error(f"取 WMS 客戶失敗：{e}")
        raise HTTPException(status_code=502, detail="無法連到 WMS 客戶資料")
    rows = data if isinstance(data, list) else data.get("data", [])
    out = []
    for c in rows:
        blob = f"{c.get('name','')} {c.get('tax_id','')} {c.get('phone','')} {c.get('contact','')}".lower()
        if s and s not in blob:
            continue
        out.append({
            "id": c.get("id"), "name": c.get("name", ""), "tax_id": c.get("tax_id", ""),
            "phone": c.get("phone", ""), "contact": c.get("contact", ""),
            "company_address": c.get("company_address", ""),
        })
        if len(out) >= 30:
            break
    return {"items": out}


@router.post("/customers/bind")
async def bind_wms_customer(request: Request):
    """綁定 / 解除綁定 熟客 ↔ WMS 客戶。body: {user_id, wms_customer_id}（空字串=解除）。"""
    _auth(request)
    body = await request.json()
    target = body.get("user_id", "")
    wms_id = str(body.get("wms_customer_id", "") or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="參數錯誤")
    if not set_wms_customer(target, wms_id):
        raise HTTPException(status_code=400, detail="綁定失敗（對象不存在）")
    return {"ok": True, "wms_customer_id": wms_id}
