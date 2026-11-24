from __future__ import annotations

import io
from typing import Optional

from .models import Room


def generate_room_qr_plaque(room: Room, college_name: str = "California University, America") -> bytes:
    """Generate a printable PNG QR plaque for a campus room."""
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    qr_value = room.qr_code_value or f"CU:MAB:F{room.floor_id}:{room.room_number}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(qr_value)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0f172a", back_color="#ffffff").convert("RGB")

    width = max(420, qr_img.width + 80)
    height = qr_img.height + 150
    canvas = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([(0, 0), (width, 52)], fill="#1d4ed8")
    font_default = ImageFont.load_default()
    draw.text((20, 18), f"{college_name} — Smart Campus Plaque", fill="#ffffff", font=font_default)

    qr_x = (width - qr_img.width) // 2
    canvas.paste(qr_img, (qr_x, 68))

    text_y = 78 + qr_img.height
    draw.text((24, text_y), f"{room.room_number} · {room.name}", fill="#0f172a", font=font_default)
    draw.text((24, text_y + 20), f"Department: {room.department}", fill="#475569", font=font_default)
    draw.text((24, text_y + 40), f"Scan Code: {qr_value}", fill="#1d4ed8", font=font_default)

    draw.rectangle([(4, 4), (width - 5, height - 5)], outline="#cbd5e1", width=2)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def match_room_by_qr(raw_code: str, rooms: list[Room]) -> Optional[Room]:
    cleaned = raw_code.strip()
    if not cleaned:
        return None
    upper = cleaned.upper()
    for r in rooms:
        if (r.qr_code_value or "").upper() == upper:
            return r
    for r in rooms:
        if r.room_number.upper() == upper or upper.endswith(f":{r.room_number.upper()}"):
            return r
    return None
