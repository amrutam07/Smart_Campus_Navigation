from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

from .models import ComputedRoute, EmergencyEvacuationPlan, EmergencyMarker, NavEdge, NavNode, Room


def _scale_pt(x: float, y: float, logical_w: float, logical_h: float, img_w: int, img_h: int) -> tuple[float, float]:
    return (x / logical_w) * img_w, (y / logical_h) * img_h


def _draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    p1: tuple[float, float],
    p2: tuple[float, float],
    fill: str,
    width: int = 3,
    dash_len: float = 10.0,
) -> None:
    import math

    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.hypot(dx, dy)
    if dist < 1:
        return
    steps = max(1, int(dist / (dash_len * 2)))
    for i in range(steps):
        t0 = (i * 2 * dash_len) / dist
        t1 = min(1.0, ((i * 2 + 1) * dash_len) / dist)
        draw.line(
            [(p1[0] + dx * t0, p1[1] + dy * t0), (p1[0] + dx * t1, p1[1] + dy * t1)],
            fill=fill,
            width=width,
        )


def render_floor_map(
    base_dir: Path,
    floor: dict[str, Any],
    rooms: list[Room],
    nodes: list[NavNode],
    edges: list[NavEdge],
    emergency_markers: list[EmergencyMarker],
    wifi_networks: list[dict[str, Any]],
    active_route: Optional[ComputedRoute] = None,
    comparison_route: Optional[ComputedRoute] = None,
    evacuation_plan: Optional[EmergencyEvacuationPlan] = None,
    start_room: Optional[Room] = None,
    dest_room: Optional[Room] = None,
    active_step_node_key: Optional[str] = None,
    show_graph: bool = False,
    show_wifi: bool = False,
    emergency_mode: bool = False,
) -> bytes:
    rel_img = floor.get("map_image_url", "assets/images/first_floor_plan.jpg").lstrip("/")
    img_path = base_dir / rel_img
    if not img_path.exists():
        img_path = base_dir / "assets" / "images" / "first_floor_plan.jpg"

    base_img = Image.open(img_path).convert("RGBA")
    img_w, img_h = base_img.size
    logical_w = float(floor.get("map_width", 1000))
    logical_h = float(floor.get("map_height", 562))

    overlay = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    node_map = {n.node_key: n for n in nodes}

    # Optional Wi-Fi hotspot coverage zones
    if show_wifi:
        for w in wifi_networks:
            if w["floor_id"] != floor["id"]:
                continue
            cx, cy = _scale_pt(w["x"], w["y"], logical_w, logical_h, img_w, img_h)
            rad = (w.get("coverage_radius", 110) / logical_w) * img_w
            color = (37, 99, 235, 36) if w["status"] == "online" else (245, 158, 11, 40)
            border = (37, 99, 235, 160) if w["status"] == "online" else (217, 119, 6, 180)
            draw.ellipse([(cx - rad, cy - rad), (cx + rad, cy + rad)], fill=color, outline=border, width=2)
            draw.ellipse([(cx - 7, cy - 7), (cx + 7, cy + 7)], fill="#2563eb", outline="#ffffff", width=2)
            draw.text((cx + 10, cy - 8), f"{w['ssid']} ({w['speed_mbps']}M)", fill="#1e3a8a", font=font)

    # Optional Corridor Navigation Graph
    if show_graph:
        for e in edges:
            n1 = node_map.get(e.from_node_key)
            n2 = node_map.get(e.to_node_key)
            if not n1 or not n2:
                continue
            p1 = _scale_pt(n1.x, n1.y, logical_w, logical_h, img_w, img_h)
            p2 = _scale_pt(n2.x, n2.y, logical_w, logical_h, img_w, img_h)
            col = "#ef4444" if e.is_blocked else ("#f59e0b" if e.is_staircase else "#64748b")
            draw.line([p1, p2], fill=col, width=2)
        for n in nodes:
            px, py = _scale_pt(n.x, n.y, logical_w, logical_h, img_w, img_h)
            ncol = "#dc2626" if n.is_blocked else ("#0284c7" if n.node_type == "lift" else "#334155")
            draw.ellipse([(px - 4, py - 4), (px + 4, py + 4)], fill=ncol, outline="#ffffff", width=1)

    # Highlight blocked edges clearly even if graph overlay is off
    for e in edges:
        if e.is_blocked:
            n1 = node_map.get(e.from_node_key)
            n2 = node_map.get(e.to_node_key)
            if n1 and n2:
                p1 = _scale_pt(n1.x, n1.y, logical_w, logical_h, img_w, img_h)
                p2 = _scale_pt(n2.x, n2.y, logical_w, logical_h, img_w, img_h)
                draw.line([p1, p2], fill="#dc2626", width=5)
                mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
                draw.ellipse([(mx - 10, my - 10), (mx + 10, my + 10)], fill="#dc2626", outline="#ffffff", width=2)
                draw.text((mx - 3, my - 6), "X", fill="#ffffff", font=font)

    # Comparison dashed baseline route
    if comparison_route and len(comparison_route.path_nodes) >= 2 and not emergency_mode:
        pts = [_scale_pt(n.x, n.y, logical_w, logical_h, img_w, img_h) for n in comparison_route.path_nodes]
        for i in range(len(pts) - 1):
            _draw_dashed_line(draw, pts[i], pts[i + 1], fill="#64748b", width=4, dash_len=10.0)

    # Emergency evacuation path or standard indoor route
    route_to_draw: Optional[ComputedRoute] = None
    route_color = "#2563eb"
    halo_color = (37, 99, 235, 95)

    if emergency_mode and evacuation_plan:
        if evacuation_plan.alternative_route and len(evacuation_plan.alternative_route.path_nodes) >= 2:
            alt_pts = [
                _scale_pt(n.x, n.y, logical_w, logical_h, img_w, img_h)
                for n in evacuation_plan.alternative_route.path_nodes
            ]
            for i in range(len(alt_pts) - 1):
                _draw_dashed_line(draw, alt_pts[i], alt_pts[i + 1], fill="#f59e0b", width=5, dash_len=12.0)
        route_to_draw = evacuation_plan.primary_route
        route_color = "#dc2626"
        halo_color = (220, 38, 38, 100)
    elif active_route:
        route_to_draw = active_route

    if route_to_draw and len(route_to_draw.path_nodes) >= 2:
        pts = [_scale_pt(n.x, n.y, logical_w, logical_h, img_w, img_h) for n in route_to_draw.path_nodes]
        draw.line(pts, fill=halo_color, width=14, joint="curve")
        draw.line(pts, fill=route_color, width=6, joint="curve")
        for pt in pts[1:-1]:
            draw.ellipse([(pt[0] - 4, pt[1] - 4), (pt[0] + 4, pt[1] + 4)], fill="#ffffff", outline=route_color, width=2)

    # Emergency markers (Exits, Extinguishers, Assembly Points)
    for m in emergency_markers:
        if m.floor_id != floor["id"]:
            continue
        if not emergency_mode and m.marker_type not in {"primary_exit", "secondary_exit"}:
            continue
        mx, my = _scale_pt(m.x, m.y, logical_w, logical_h, img_w, img_h)
        if m.status == "blocked":
            m_col = "#64748b"
            tag = "CLOSED"
        elif m.marker_type == "extinguisher":
            m_col = "#ea580c"
            tag = "EXT"
        elif m.marker_type == "assembly_point":
            m_col = "#059669"
            tag = "SAFE"
        else:
            m_col = "#dc2626" if emergency_mode else "#16a34a"
            tag = "EXIT"

        draw.rounded_rectangle([(mx - 18, my - 10), (mx + 18, my + 10)], radius=5, fill=m_col, outline="#ffffff", width=2)
        draw.text((mx - 12, my - 6), tag, fill="#ffffff", font=font)

    # Subtle room pins on active floor
    for r in rooms:
        if r.floor_id != floor["id"]:
            continue
        rx, ry = _scale_pt(r.x, r.y, logical_w, logical_h, img_w, img_h)
        is_start = start_room is not None and r.id == start_room.id
        is_dest = dest_room is not None and r.id == dest_room.id
        if is_start or is_dest:
            continue
        dot_col = "#0284c7" if r.category == "laboratory" else ("#7c3aed" if r.category == "office" else "#475569")
        draw.ellipse([(rx - 5, ry - 5), (rx + 5, ry + 5)], fill=dot_col, outline="#ffffff", width=1)
        draw.text((rx + 7, ry - 6), r.room_number, fill="#0f172a", font=font)

    # Highlight Start Room Pin (Green)
    if start_room and start_room.floor_id == floor["id"]:
        sx, sy = _scale_pt(start_room.x, start_room.y, logical_w, logical_h, img_w, img_h)
        draw.ellipse([(sx - 13, sy - 13), (sx + 13, sy + 13)], fill=(16, 185, 129, 90))
        draw.ellipse([(sx - 9, sy - 9), (sx + 9, sy + 9)], fill="#10b981", outline="#ffffff", width=3)
        draw.rounded_rectangle([(sx + 12, sy - 12), (sx + 165, sy + 10)], radius=4, fill="#065f46")
        draw.text((sx + 17, sy - 7), f"START: {start_room.room_number}", fill="#ffffff", font=font)

    # Highlight Destination Room Pin (Blue)
    if dest_room and dest_room.floor_id == floor["id"] and not emergency_mode:
        dx, dy = _scale_pt(dest_room.x, dest_room.y, logical_w, logical_h, img_w, img_h)
        draw.ellipse([(dx - 15, dy - 15), (dx + 15, dy + 15)], fill=(37, 99, 235, 95))
        draw.ellipse([(dx - 10, dy - 10), (dx + 10, dy + 10)], fill="#2563eb", outline="#ffffff", width=3)
        draw.rounded_rectangle([(dx + 12, dy - 12), (dx + 185, dy + 10)], radius=4, fill="#1e3a8a")
        draw.text((dx + 17, dy - 7), f"DEST: {dest_room.room_number}", fill="#ffffff", font=font)

    # Active Step Focus Beacon during Live Navigation
    if active_step_node_key:
        focus_key = active_step_node_key.split("->")[0]
        fn = node_map.get(focus_key)
        if fn and fn.floor_id == floor["id"]:
            fx, fy = _scale_pt(fn.x, fn.y, logical_w, logical_h, img_w, img_h)
            draw.ellipse([(fx - 18, fy - 18), (fx + 18, fy + 18)], outline="#10b981", width=4)
            draw.ellipse([(fx - 8, fy - 8), (fx + 8, fy + 8)], fill="#10b981", outline="#ffffff", width=2)

    combined = Image.alpha_composite(base_img, overlay).convert("RGB")
    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    return buf.getvalue()
