"""Admin dashboard — quản lý tồn kho và xem đơn hàng gần đây."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings
from app.inventory import _load as _load_inv, set_banh_kem_available, set_su_kem_quantity

router = APIRouter()
_security = HTTPBasic()


def _require_auth(credentials: Annotated[HTTPBasicCredentials, Depends(_security)]) -> None:
    cfg = get_settings()
    ok = (
        secrets.compare_digest(credentials.username.encode(), b"admin")
        and secrets.compare_digest(credentials.password.encode(), cfg.admin_password.encode())
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Sai mật khẩu",
            headers={"WWW-Authenticate": "Basic"},
        )


def _render_dashboard(inv: dict, orders: list[dict], message: str = "") -> str:
    su_kem_qty = inv.get("banh_su_kem", {}).get("quantity")
    banh_kem = inv.get("banh_kem", {})
    updated_at = inv.get("updated_at", "—")

    # Su kem badge
    if su_kem_qty is None:
        su_badge = '<span class="badge-ok">✅ Theo dõi thủ công</span>'
        su_display = 0
    elif su_kem_qty == 0:
        su_badge = '<span class="badge-out">❌ Hết hàng</span>'
        su_display = 0
    else:
        su_badge = f'<span class="badge-ok">✅ Còn {su_kem_qty} hộp</span>'
        su_display = su_kem_qty

    # Banh kem rows
    banh_kem_rows = ""
    for size, info in banh_kem.items():
        avail = info.get("available", True)
        badge = '<span class="badge-ok">✅ Có sẵn</span>' if avail else '<span class="badge-out">❌ Hết / đặt trước</span>'
        field = f"available_{size}"
        checked = "checked" if avail else ""
        banh_kem_rows += (
            f"<tr><td><strong>{size}</strong></td><td>{badge}</td>"
            f'<td><label><input type="checkbox" name="{field}" {checked}> Có sẵn</label></td></tr>'
        )

    # Order rows
    order_rows = ""
    for o in orders:
        notes = o.get("notes", "") or ""
        same_day = "ĐẶTCÙNGNGÀY" in notes
        sd_badge = '<span class="badge-sameday">⚡ Cùng ngày</span> ' if same_day else ""
        status = o.get("status", "")
        order_rows += (
            f'<tr class="{"tr-sameday" if same_day else ""}">'
            f"<td>{o.get('order_id', '')}</td>"
            f"<td>{o.get('created_at', '')}</td>"
            f"<td>{o.get('name', '')}<br><small>{o.get('phone', '')}</small></td>"
            f"<td>{o.get('cake_type', '')} {o.get('size', '')}</td>"
            f"<td>{sd_badge}{o.get('delivery_date', '')}</td>"
            f"<td>{o.get('total_price', '')}</td>"
            f'<td><span class="status-{status}">{status}</span></td>'
            "</tr>"
        )

    msg_html = f'<div class="banner">✅ {message}</div>' if message else ""
    orders_html = (
        "<p style='color:#888;padding:12px 0'>Chưa có đơn hàng nào.</p>"
        if not orders
        else (
            "<table><thead><tr>"
            "<th>Mã đơn</th><th>Thời gian</th><th>Khách hàng</th>"
            "<th>Bánh</th><th>Ngày giao</th><th>Tổng tiền</th><th>Trạng thái</th>"
            f"</tr></thead><tbody>{order_rows}</tbody></table>"
        )
    )

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lucky Cake — Quản lý</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:1000px;margin:32px auto;padding:0 20px;background:#f7f7f7;color:#333}}
h1{{color:#e74c3c;margin-bottom:2px}}
.sub{{color:#999;font-size:.88em;margin-bottom:24px}}
.card{{background:#fff;border:1px solid #e0e0e0;border-radius:10px;padding:20px 24px;margin-bottom:20px}}
h2{{color:#444;border-bottom:2px solid #fdecea;padding-bottom:8px;margin-top:0}}
.badge-ok{{background:#27ae60;color:#fff;padding:3px 10px;border-radius:12px;font-size:.84em}}
.badge-out{{background:#e74c3c;color:#fff;padding:3px 10px;border-radius:12px;font-size:.84em}}
.badge-sameday{{background:#f39c12;color:#fff;padding:2px 8px;border-radius:10px;font-size:.78em}}
.banner{{background:#d4edda;border:1px solid #c3e6cb;color:#155724;padding:10px 16px;border-radius:6px;margin-bottom:16px}}
.row{{display:flex;align-items:center;gap:12px;margin:10px 0;flex-wrap:wrap}}
input[type=number]{{width:88px;padding:7px;border:1px solid #ccc;border-radius:6px;font-size:1em}}
button{{padding:8px 20px;border:none;border-radius:6px;cursor:pointer;font-size:.93em;font-weight:600}}
.btn-r{{background:#e74c3c;color:#fff}}.btn-r:hover{{background:#c0392b}}
.btn-b{{background:#3498db;color:#fff}}.btn-b:hover{{background:#2980b9}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
@media(max-width:600px){{.grid2{{grid-template-columns:1fr}}}}
table{{width:100%;border-collapse:collapse;font-size:.87em}}
th{{background:#f5f5f5;text-align:left;padding:9px 8px;font-weight:600;border-bottom:2px solid #ddd}}
td{{padding:8px;border-bottom:1px solid #f0f0f0;vertical-align:top}}
tr.tr-sameday{{background:#fff8e1}}
.status-pending{{color:#e67e22}}.status-confirmed{{color:#27ae60}}
.status-preparing{{color:#2980b9}}.status-completed{{color:#95a5a6}}
.status-cancelled{{color:#e74c3c;text-decoration:line-through}}
small{{color:#888}}
</style>
</head>
<body>
<h1>🎂 Lucky Cake — Quản lý</h1>
<div class="sub">Cập nhật lần cuối: {updated_at} &nbsp;|&nbsp; <a href="/admin">Làm mới</a></div>
{msg_html}
<div class="grid2">
  <div class="card">
    <h2>🧁 Bánh Su Kem</h2>
    <div class="row">{su_badge}</div>
    <form method="post" action="/admin/inventory/su-kem">
      <div class="row">
        <label>Số hộp hiện có:</label>
        <input type="number" name="quantity" value="{su_display}" min="0" max="9999">
        <button type="submit" class="btn-r">Lưu</button>
      </div>
    </form>
    <p style="color:#888;font-size:.83em;margin:4px 0 0">Khi bán hết → nhập 0. Khi nhập thêm hàng → nhập số mới.</p>
  </div>
  <div class="card">
    <h2>🎂 Bánh Kem</h2>
    <form method="post" action="/admin/inventory/banh-kem">
      <table>
        <tr><th>Size</th><th>Trạng thái</th><th>Thay đổi</th></tr>
        {banh_kem_rows}
      </table>
      <div class="row" style="margin-top:14px">
        <button type="submit" class="btn-b">Lưu trạng thái</button>
      </div>
    </form>
    <p style="color:#888;font-size:.83em;margin:4px 0 0">Bỏ tick = hết / cần đặt trước. Đánh tick = có sẵn.</p>
  </div>
</div>
<div class="card">
  <h2>📋 Đơn hàng gần đây <span style="font-weight:400;font-size:.8em;color:#aaa">(20 đơn mới nhất)</span></h2>
  {orders_html}
</div>
</body>
</html>"""


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    msg: str = "",
    _auth: None = Depends(_require_auth),
):
    import asyncio
    from app.sheets import get_recent_orders

    inv = _load_inv()
    orders = await asyncio.to_thread(get_recent_orders, 20)
    return _render_dashboard(inv, orders, msg)


@router.post("/admin/inventory/su-kem")
async def update_su_kem(
    quantity: int = Form(...),
    _auth: None = Depends(_require_auth),
):
    set_su_kem_quantity(max(0, quantity))
    return RedirectResponse("/admin?msg=Đã+cập+nhật+bánh+su+kem", status_code=303)


@router.post("/admin/inventory/banh-kem")
async def update_banh_kem(
    available_16cm: str = Form(default="off"),
    available_20cm: str = Form(default="off"),
    _auth: None = Depends(_require_auth),
):
    set_banh_kem_available("16cm", available_16cm == "on")
    set_banh_kem_available("20cm", available_20cm == "on")
    return RedirectResponse("/admin?msg=Đã+cập+nhật+bánh+kem", status_code=303)
