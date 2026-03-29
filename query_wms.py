from api_client import wms_get


async def get_stock(item_name: str) -> str:
    """查單項材料庫存（透過 WMS API）"""
    data = await wms_get("/api/products", params={"search": item_name})
    products = data if isinstance(data, list) else data.get("products", data.get("data", []))

    if not products:
        return f"找不到「{item_name}」相關的品項"

    lines = []
    for r in products:
        status = ""
        min_stock = r.get("min_stock", 0) or 0
        stock = r.get("stock", 0) or 0
        if min_stock > 0 and stock < min_stock:
            status = " ⚠️低於安全庫存"
        lines.append(
            f"• {r.get('brand', '')} {r.get('name', '')} {r.get('color_name', '')}\n"
            f"  規格：{r.get('spec', '')}　庫存：{stock}{r.get('unit', '')}"
            f"（安全量：{min_stock}{r.get('unit', '')}）{status}"
        )
    return "\n".join(lines)


async def get_low_stock() -> str:
    """查低於安全庫存的品項"""
    data = await wms_get("/api/alerts")
    alerts = data if isinstance(data, list) else data.get("alerts", data.get("data", []))

    if not alerts:
        # fallback：取庫存最低 5 筆
        data = await wms_get("/api/products")
        products = data if isinstance(data, list) else data.get("products", data.get("data", []))
        products.sort(key=lambda x: x.get("stock", 0) or 0)
        top5 = products[:5]
        if not top5:
            return "目前沒有庫存資料"
        lines = ["📦 庫存最低的 5 項（無品項低於安全庫存）："]
        for r in top5:
            lines.append(f"• {r.get('brand', '')} {r.get('name', '')} {r.get('color_name', '')} — {r.get('stock', 0)}{r.get('unit', '')}")
        return "\n".join(lines)

    lines = [f"⚠️ 共 {len(alerts)} 項低於安全庫存："]
    for r in alerts:
        lines.append(
            f"• {r.get('brand', '')} {r.get('name', '')} {r.get('color_name', '')}\n"
            f"  庫存：{r.get('stock', 0)}{r.get('unit', '')} / 安全量：{r.get('min_stock', 0)}{r.get('unit', '')}"
        )
    return "\n".join(lines)


async def get_recent_transactions(days: int = 7) -> str:
    """查最近 N 天進出貨紀錄"""
    data = await wms_get("/api/transactions", params={"limit": 50})
    rows = data if isinstance(data, list) else data.get("transactions", data.get("data", []))

    if not rows:
        return f"最近沒有進出貨紀錄"

    lines = [f"📋 最近進出貨（共 {len(rows)} 筆）："]
    for r in rows[:20]:
        type_label = "入庫" if r.get("type") == "in" else "出庫"
        product_name = r.get("product_name", r.get("name", ""))
        lines.append(
            f"• [{type_label}] {product_name} "
            f"{r.get('quantity', '')}{r.get('unit', '')} — {str(r.get('created_at', ''))[:10]}"
        )
    return "\n".join(lines)


async def get_orders_summary(days: int = 30) -> str:
    """查最近訂單摘要"""
    data = await wms_get("/api/orders", params={"limit": 20})
    rows = data if isinstance(data, list) else data.get("orders", data.get("data", []))

    if not rows:
        return f"最近沒有訂單"

    lines = [f"📋 最近訂單（共 {len(rows)} 筆）："]
    for r in rows[:15]:
        type_label = "銷售" if r.get("order_type") == "out" else "進貨"
        lines.append(
            f"• [{type_label}] {r.get('order_number', '')} — "
            f"數量：{r.get('total_qty', 0)}　金額：${r.get('total_amount', 0):,.0f}　日期：{r.get('order_date', '')}"
        )
    return "\n".join(lines)
