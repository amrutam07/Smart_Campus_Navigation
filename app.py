from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from campus_app.database import CampusDatabase
from campus_app.i18n import t
from campus_app.map_renderer import render_floor_map
from campus_app.models import RouteStep
from campus_app.pathfinding import (
    compute_emergency_evacuation,
    find_cross_floor_route,
    find_indoor_route,
    get_step_visual_asset,
    resolve_room_search,
)
from campus_app.qr_tools import generate_room_qr_plaque, match_room_by_qr

BASE_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="California University, America — Smart Campus Navigator",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1380px; }
    .cu-header-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 14px 18px;
        margin-bottom: 14px;
    }
    .cu-step-card {
        border: 1px solid #e2e8f0;
        background: #f8fafc;
        border-radius: 10px;
        padding: 10px 12px;
        margin-bottom: 8px;
    }
    .cu-step-active {
        border: 2px solid #10b981;
        background: #ecfdf5;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_db() -> CampusDatabase:
    return CampusDatabase(BASE_DIR)


db = get_db()
campus = db.load_bootstrap()
college = campus["activeCollege"]
college_name = college.get("name", "California University, America")
short_title = f"{college_name.split(',')[0].strip()} Navigator"
floors = campus["floors"]
rooms = campus["rooms"]
nodes = campus["navNodes"]
edges = campus["navEdges"]
markers = campus["emergencyMarkers"]
contacts = campus["emergencyContacts"]
active_alerts = campus["activeAlerts"]
faculty = campus["faculty"]
announcements = campus["announcements"]
wifi_networks = campus["wifiNetworks"]
feedback_reports = campus["feedbackReports"]
recent_logs = campus["recentLogs"]

default_floor = next((f for f in floors if f["is_default"]), floors[0])
default_start = next((r for r in rooms if r.room_number == "ENT-1"), rooms[0])

# Initialize session state cleanly
if "language" not in st.session_state:
    st.session_state.language = "en"
if "selected_floor_id" not in st.session_state:
    st.session_state.selected_floor_id = default_floor["id"]
if "start_room_id" not in st.session_state:
    st.session_state.start_room_id = default_start.id
if "dest_room_id" not in st.session_state:
    st.session_state.dest_room_id = None
if "route_mode" not in st.session_state:
    st.session_state.route_mode = "shortest"
if "is_navigating" not in st.session_state:
    st.session_state.is_navigating = False
if "active_step_idx" not in st.session_state:
    st.session_state.active_step_idx = 0
if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = True
if "speech_nonce" not in st.session_state:
    st.session_state.speech_nonce = 0
if "pending_speech_text" not in st.session_state:
    st.session_state.pending_speech_text = ""
if "stop_speech" not in st.session_state:
    st.session_state.stop_speech = False


def queue_speech(text: str) -> None:
    st.session_state.pending_speech_text = text
    st.session_state.stop_speech = False
    st.session_state.speech_nonce += 1


def render_speech_runner() -> None:
    if st.session_state.stop_speech:
        components.html(
            """
            <script>
            (function() {
              try { if (window.parent && window.parent.speechSynthesis) window.parent.speechSynthesis.cancel(); } catch (e) {}
              try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) {}
            })();
            </script>
            """,
            height=0,
        )
        st.session_state.stop_speech = False
        return

    text_to_speak = st.session_state.pending_speech_text
    if not text_to_speak:
        return
    lang_code = "kn-IN" if st.session_state.language == "kn" else "en-IN"
    nonce = st.session_state.speech_nonce
    safe_text = json.dumps(text_to_speak)
    safe_lang = json.dumps(lang_code)
    components.html(
        f"""
        <script>
        // nonce: {nonce}
        (function() {{
          var synth = null;
          try {{
            if (window.parent && window.parent.speechSynthesis) synth = window.parent.speechSynthesis;
          }} catch (e) {{}}
          if (!synth && window.speechSynthesis) synth = window.speechSynthesis;
          if (!synth) return;
          try {{
            synth.cancel();
            var u = new SpeechSynthesisUtterance({safe_text});
            u.lang = {safe_lang};
            u.rate = 0.96;
            synth.speak(u);
          }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
    )
    st.session_state.pending_speech_text = ""
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "recent_room_ids" not in st.session_state:
    st.session_state.recent_room_ids = []
if "admin_user" not in st.session_state:
    st.session_state.admin_user = None
if "last_logged_route_sig" not in st.session_state:
    st.session_state.last_logged_route_sig = ""

lang = st.session_state.language
room_by_id = {r.id: r for r in rooms}
floor_by_id = {f["id"]: f for f in floors}
active_floor = floor_by_id.get(st.session_state.selected_floor_id, default_floor)

# ---------------- TOP HEADER BAR ----------------
hdr_left, hdr_mid, hdr_right = st.columns([0.55, 0.25, 0.20], vertical_alignment="center")
with hdr_left:
    logo_col, title_col = st.columns([0.12, 0.88], vertical_alignment="center")
    with logo_col:
        emblem_path = BASE_DIR / college.get("logo_url", "assets/images/college_emblem.jpg")
        if emblem_path.exists():
            st.image(str(emblem_path), width=56)
    with title_col:
        st.markdown(f"### {short_title}")
        st.caption(f"{college.get('address', '')} · {active_floor['name']}")

with hdr_mid:
    floor_options = {f["id"]: f["name"] for f in floors}
    chosen_floor = st.selectbox(
        "Active Floor",
        options=list(floor_options.keys()),
        index=list(floor_options.keys()).index(active_floor["id"]),
        format_func=lambda fid: floor_options[fid],
        label_visibility="collapsed",
    )
    if chosen_floor != st.session_state.selected_floor_id:
        st.session_state.selected_floor_id = chosen_floor
        st.rerun()

with hdr_right:
    c_lang, c_qr = st.columns(2)
    with c_lang:
        lang_label = "ಕನ್ನಡ" if lang == "en" else "English"
        if st.button(lang_label, use_container_width=True):
            st.session_state.language = "kn" if lang == "en" else "en"
            st.rerun()
    with c_qr:
        with st.popover("QR Check-In", use_container_width=True):
            st.markdown("**Scan or Enter Room QR Plaque**")
            qr_text = st.text_input("QR Payload or Room No.", placeholder="e.g. CU:MAB:F1:101 or 101")
            if st.button("Locate Me Here", type="primary", use_container_width=True):
                matched = match_room_by_qr(qr_text, rooms)
                if matched:
                    st.session_state.start_room_id = matched.id
                    st.session_state.selected_floor_id = matched.floor_id
                    st.success(f"Start set to {matched.room_number} · {matched.name}")
                    st.rerun()
                else:
                    st.error("QR code not matched to any registered room.")

if active_alerts:
    top_alert = active_alerts[0]
    st.error(f"**Active Safety Alert:** {top_alert['title']} — {top_alert['message']}")

# ---------------- MAIN NAVIGATION TABS ----------------
tab_indoor, tab_emergency, tab_wifi, tab_outdoor, tab_directory, tab_admin = st.tabs(
    [
        "🧭 Indoor Navigation",
        "🚨 Emergency Evacuation",
        "📶 Wi-Fi Zones",
        "🗺️ Outdoor Map",
        "📋 Directory & Schedule",
        "🛠️ Admin Portal",
    ]
)

# ==============================================================================
# TAB 1: INDOOR NAVIGATION
# ==============================================================================
with tab_indoor:
    col_start, col_swap, col_dest, col_mode = st.columns([0.28, 0.06, 0.34, 0.32], vertical_alignment="bottom")

    room_ids = [r.id for r in rooms]
    with col_start:
        start_idx = room_ids.index(st.session_state.start_room_id) if st.session_state.start_room_id in room_ids else 0
        new_start_id = st.selectbox(
            t(lang, "select_start"),
            options=room_ids,
            index=start_idx,
            format_func=lambda rid: f"{room_by_id[rid].room_number} · {room_by_id[rid].name}",
        )
        if new_start_id != st.session_state.start_room_id:
            st.session_state.start_room_id = new_start_id
            st.session_state.active_step_idx = 0
            st.rerun()

    with col_swap:
        if st.button("⇄", help="Swap Start & Destination", use_container_width=True) and st.session_state.dest_room_id:
            s_id = st.session_state.start_room_id
            d_id = st.session_state.dest_room_id
            st.session_state.start_room_id = d_id
            st.session_state.dest_room_id = s_id
            if s_id in room_by_id:
                st.session_state.selected_floor_id = room_by_id[s_id].floor_id
            st.session_state.active_step_idx = 0
            st.rerun()

    with col_dest:
        search_q = st.text_input("Filter destination rooms", placeholder=t(lang, "search_placeholder"))
        filtered_rooms = resolve_room_search(rooms, search_q) if search_q.strip() else rooms
        filtered_ids = [None] + [r.id for r in filtered_rooms]
        curr_dest = st.session_state.dest_room_id if st.session_state.dest_room_id in filtered_ids else None
        new_dest_id = st.selectbox(
            t(lang, "select_dest"),
            options=filtered_ids,
            index=filtered_ids.index(curr_dest),
            format_func=lambda rid: "-- Choose Destination Room --"
            if rid is None
            else f"{room_by_id[rid].room_number} · {room_by_id[rid].name}",
        )
        if new_dest_id != st.session_state.dest_room_id:
            st.session_state.dest_room_id = new_dest_id
            st.session_state.active_step_idx = 0
            st.session_state.is_navigating = False
            if new_dest_id and new_dest_id in room_by_id:
                st.session_state.selected_floor_id = room_by_id[new_dest_id].floor_id
                if new_dest_id not in st.session_state.recent_room_ids:
                    st.session_state.recent_room_ids = ([new_dest_id] + st.session_state.recent_room_ids)[:6]
            st.rerun()

    with col_mode:
        mode_labels = {
            "shortest": t(lang, "shortest_route"),
            "easiest": t(lang, "easiest_route"),
            "stair_free": t(lang, "stair_free_route"),
        }
        chosen_mode = st.radio(
            "Route Preference",
            options=["shortest", "easiest", "stair_free"],
            index=["shortest", "easiest", "stair_free"].index(st.session_state.route_mode),
            format_func=lambda m: mode_labels[m],
            horizontal=True,
        )
        if chosen_mode != st.session_state.route_mode:
            st.session_state.route_mode = chosen_mode
            st.session_state.active_step_idx = 0
            st.rerun()

    # Quick favorites strip
    if st.session_state.favorites or st.session_state.recent_room_ids:
        qcols = st.columns([0.15, 0.85])
        with qcols[0]:
            st.caption("Quick Jump:")
        with qcols[1]:
            quick_ids = list(dict.fromkeys(st.session_state.favorites + st.session_state.recent_room_ids))[:6]
            btn_cols = st.columns(len(quick_ids))
            for idx, qid in enumerate(quick_ids):
                if qid in room_by_id:
                    rm = room_by_id[qid]
                    star = "★ " if qid in st.session_state.favorites else ""
                    if btn_cols[idx].button(f"{star}{rm.room_number} {rm.name}", key=f"quick_{qid}", use_container_width=True):
                        st.session_state.dest_room_id = qid
                        st.session_state.selected_floor_id = rm.floor_id
                        st.session_state.active_step_idx = 0
                        st.rerun()

    start_room = room_by_id.get(st.session_state.start_room_id)
    dest_room = room_by_id.get(st.session_state.dest_room_id) if st.session_state.dest_room_id else None

    indoor_route = None
    cross_plan = None
    comparison_route = None

    if start_room and dest_room:
        if start_room.floor_id == dest_room.floor_id:
            fl_nodes = [n for n in nodes if n.floor_id == start_room.floor_id]
            fl_edges = [e for e in edges if e.floor_id == start_room.floor_id]
            indoor_route = find_indoor_route(
                fl_nodes,
                fl_edges,
                start_room.door_node_key,
                dest_room.door_node_key,
                mode=st.session_state.route_mode,
                start_label=start_room.name,
                end_label=dest_room.name,
            )
            cmp_mode = "stair_free" if st.session_state.route_mode == "shortest" else "shortest"
            cmp_res = find_indoor_route(
                fl_nodes,
                fl_edges,
                start_room.door_node_key,
                dest_room.door_node_key,
                mode=cmp_mode,
                start_label=start_room.name,
                end_label=dest_room.name,
            )
            if cmp_res and indoor_route:
                if [n.node_key for n in cmp_res.path_nodes] != [n.node_key for n in indoor_route.path_nodes]:
                    comparison_route = cmp_res
            if indoor_route:
                sig = f"{start_room.id}->{dest_room.id}:{st.session_state.route_mode}"
                if st.session_state.last_logged_route_sig != sig:
                    db.log_navigation(
                        college["id"], start_room.name, dest_room.name, st.session_state.route_mode, indoor_route.total_distance_meters, False
                    )
                    st.session_state.last_logged_route_sig = sig
        else:
            s_floor = floor_by_id[start_room.floor_id]
            d_floor = floor_by_id[dest_room.floor_id]
            cross_plan = find_cross_floor_route(
                nodes,
                edges,
                start_room,
                dest_room,
                start_floor_name=s_floor["name"],
                end_floor_name=d_floor["name"],
                mode=st.session_state.route_mode,
            )
            if cross_plan:
                sig = f"X:{start_room.id}->{dest_room.id}:{st.session_state.route_mode}"
                if st.session_state.last_logged_route_sig != sig:
                    db.log_navigation(
                        college["id"], start_room.name, dest_room.name, st.session_state.route_mode, cross_plan.total_distance_meters, False
                    )
                    st.session_state.last_logged_route_sig = sig

    map_col, side_col = st.columns([0.66, 0.34], gap="large")

    with map_col:
        opt1, opt2, opt3 = st.columns([0.38, 0.32, 0.30])
        show_graph = opt1.checkbox("Show corridor navigation graph", value=False)
        show_wifi_overlay = opt2.checkbox("Show Wi-Fi access points", value=False)
        with opt3:
            offline_payload = json.dumps(
                {
                    "college": college_name,
                    "floors": floors,
                    "rooms": [r.__dict__ for r in rooms],
                    "navNodes": [n.__dict__ for n in nodes],
                    "navEdges": [e.__dict__ for e in edges],
                },
                indent=2,
            )
            st.download_button(
                "Export Offline Map Pack",
                data=offline_payload,
                file_name=f"{college.get('short_code', 'CU')}-offline-map.json",
                mime="application/json",
                use_container_width=True,
            )

        active_steps: list[RouteStep] = []
        if cross_plan:
            active_steps = cross_plan.all_steps
        elif indoor_route:
            active_steps = indoor_route.steps

        active_step_node_key = None
        if st.session_state.is_navigating and active_steps:
            idx = min(st.session_state.active_step_idx, len(active_steps) - 1)
            active_step_node_key = active_steps[idx].node_key

        route_for_active_floor = None
        if cross_plan and start_room and dest_room:
            if active_floor["id"] == start_room.floor_id:
                route_for_active_floor = cross_plan.leg1
            elif active_floor["id"] == dest_room.floor_id:
                route_for_active_floor = cross_plan.leg2
        elif indoor_route and start_room and active_floor["id"] == start_room.floor_id:
            route_for_active_floor = indoor_route

        fl_nodes_render = [n for n in nodes if n.floor_id == active_floor["id"]]
        fl_edges_render = [e for e in edges if e.floor_id == active_floor["id"]]
        fl_cmp_render = comparison_route if (comparison_route and start_room and active_floor["id"] == start_room.floor_id) else None

        map_png = render_floor_map(
            BASE_DIR,
            active_floor,
            rooms=rooms,
            nodes=fl_nodes_render,
            edges=fl_edges_render,
            emergency_markers=markers,
            wifi_networks=wifi_networks,
            active_route=route_for_active_floor,
            comparison_route=fl_cmp_render,
            start_room=start_room,
            dest_room=dest_room,
            active_step_node_key=active_step_node_key,
            show_graph=show_graph,
            show_wifi=show_wifi_overlay,
            emergency_mode=False,
        )
        st.image(map_png, caption=f"{active_floor['name']} — Interactive Blueprint", use_container_width=True)

    with side_col:
        if start_room and dest_room and (indoor_route or cross_plan):
            total_dist = cross_plan.total_distance_meters if cross_plan else indoor_route.total_distance_meters
            est_sec = cross_plan.estimated_seconds if cross_plan else indoor_route.estimated_seconds
            strategy_note = cross_plan.strategy_note if cross_plan else indoor_route.strategy_note

            hdr_r_col, hdr_v_col = st.columns([0.72, 0.28], vertical_alignment="center")
            with hdr_r_col:
                st.markdown(f"#### {start_room.name} → {dest_room.name}")
            with hdr_v_col:
                if st.button(f"🔊 {t(lang, 'voice_guide')}", use_container_width=True):
                    full_speech = ". ".join(
                        (s.instruction_kn if lang == "kn" else s.instruction) for s in active_steps
                    )
                    queue_speech(full_speech)
                    st.rerun()

            st.info(f"**{strategy_note}**")

            if cross_plan:
                leg1_col, leg2_col = st.columns(2)
                if leg1_col.button(f"Leg 1: Floor {floor_by_id[start_room.floor_id]['floor_number']}", use_container_width=True):
                    st.session_state.selected_floor_id = start_room.floor_id
                    st.rerun()
                if leg2_col.button(f"Leg 2: Floor {floor_by_id[dest_room.floor_id]['floor_number']}", use_container_width=True):
                    st.session_state.selected_floor_id = dest_room.floor_id
                    st.rerun()

            m1, m2 = st.columns(2)
            m1.metric(t(lang, "distance"), f"{total_dist} m")
            m2.metric(t(lang, "estimated_walk"), f"~{est_sec} s")

            nav_label = t(lang, "stop_navigation") if st.session_state.is_navigating else t(lang, "start_navigation")
            if st.button(nav_label, type="primary", use_container_width=True):
                st.session_state.is_navigating = not st.session_state.is_navigating
                st.session_state.active_step_idx = 0
                if st.session_state.is_navigating and active_steps:
                    if st.session_state.voice_enabled:
                        first_txt = active_steps[0].instruction_kn if lang == "kn" else active_steps[0].instruction
                        queue_speech(first_txt)
                else:
                    st.session_state.stop_speech = True
                st.rerun()

            if st.session_state.is_navigating and active_steps:
                idx = min(st.session_state.active_step_idx, len(active_steps) - 1)
                cur_step = active_steps[idx]
                vis_rel, vis_title, vis_desc = get_step_visual_asset(cur_step)
                vis_path = BASE_DIR / vis_rel
                if vis_path.exists():
                    st.image(str(vis_path), caption=f"{vis_title} — {vis_desc}", use_container_width=True)
                step_text = cur_step.instruction_kn if lang == "kn" else cur_step.instruction
                st.success(f"**Step {idx + 1} of {len(active_steps)}:** {step_text}")

                rem_meters = round(sum(s.distance_meters for s in active_steps[idx + 1 :]), 1)
                rem_secs = max(0 if idx >= len(active_steps) - 1 else 5, round(rem_meters / 1.2))
                eta_col, spk_col, mute_col = st.columns([0.44, 0.28, 0.28], vertical_alignment="center")
                eta_col.caption(f"**{rem_meters} m left · ~{rem_secs}s**")
                if spk_col.button(f"🔊 {t(lang, 'speak')}", key="btn_speak_step", use_container_width=True):
                    queue_speech(step_text)
                    st.rerun()
                voice_btn_label = f"🔊 {t(lang, 'voice_on')}" if st.session_state.voice_enabled else f"🔇 {t(lang, 'voice_muted')}"
                if mute_col.button(voice_btn_label, key="btn_toggle_voice", use_container_width=True):
                    st.session_state.voice_enabled = not st.session_state.voice_enabled
                    if not st.session_state.voice_enabled:
                        st.session_state.stop_speech = True
                    st.rerun()

                p_col, n_col = st.columns(2)
                if p_col.button(f"◀ {t(lang, 'prev_step')}", disabled=(idx <= 0), use_container_width=True):
                    new_idx = max(0, idx - 1)
                    st.session_state.active_step_idx = new_idx
                    nxt_step = active_steps[new_idx]
                    if nxt_step.floor_id:
                        st.session_state.selected_floor_id = nxt_step.floor_id
                    if st.session_state.voice_enabled:
                        queue_speech(nxt_step.instruction_kn if lang == "kn" else nxt_step.instruction)
                    st.rerun()
                if n_col.button(f"{t(lang, 'next_step')} ▶", disabled=(idx >= len(active_steps) - 1), use_container_width=True):
                    new_idx = min(len(active_steps) - 1, idx + 1)
                    st.session_state.active_step_idx = new_idx
                    nxt_step = active_steps[new_idx]
                    if nxt_step.floor_id:
                        st.session_state.selected_floor_id = nxt_step.floor_id
                    if st.session_state.voice_enabled:
                        queue_speech(nxt_step.instruction_kn if lang == "kn" else nxt_step.instruction)
                    st.rerun()

            render_speech_runner()

            st.markdown(f"**{t(lang, 'step_by_step')}**")
            for s_idx, s in enumerate(active_steps):
                is_cur = st.session_state.is_navigating and s_idx == st.session_state.active_step_idx
                css_cls = "cu-step-card cu-step-active" if is_cur else "cu-step-card"
                txt = s.instruction_kn if lang == "kn" else s.instruction
                st.markdown(
                    f"<div class='{css_cls}'><strong>{s_idx + 1}.</strong> {txt}"
                    + (f" <span style='color:#64748b;font-size:12px;'>({s.distance_meters} m)</span>" if s.distance_meters > 0 else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )
        elif dest_room and start_room:
            st.warning("No unobstructed corridor path could be computed for the selected mode.")
        else:
            st.markdown("#### Quick Campus Overview")
            st.write("Select a **Starting Location** and **Destination Room** above to compute turn-by-turn indoor corridor navigation.")

        # Room Inspector & Printable QR Plaque
        inspect_room = dest_room or start_room
        if inspect_room:
            with st.expander(f"Room Details · {inspect_room.room_number} {inspect_room.name}", expanded=bool(dest_room)):
                st.write(f"**Department:** {inspect_room.department}")
                if inspect_room.description:
                    st.write(inspect_room.description)
                st.write(f"**Accessibility:** {inspect_room.accessibility_info}")
                st.write(f"**Schedule:** {inspect_room.timetable_summary}")

                is_fav = inspect_room.id in st.session_state.favorites
                fav_btn = "★ Remove Favorite" if is_fav else "☆ Save to Favorites"
                if st.button(fav_btn, key=f"fav_btn_{inspect_room.id}", use_container_width=True):
                    if is_fav:
                        st.session_state.favorites.remove(inspect_room.id)
                    else:
                        st.session_state.favorites.append(inspect_room.id)
                    st.rerun()

                qr_bytes = generate_room_qr_plaque(inspect_room, college_name)
                st.download_button(
                    "Download Printable QR Plaque (PNG)",
                    data=qr_bytes,
                    file_name=f"{inspect_room.room_number}_qr_plaque.png",
                    mime="image/png",
                    use_container_width=True,
                )

# ==============================================================================
# TAB 2: EMERGENCY EVACUATION
# ==============================================================================
with tab_emergency:
    st.error(f"**EMERGENCY EVACUATION MODE** — {t(lang, 'safety_notice')}")

    ev_col1, ev_col2 = st.columns([0.65, 0.35], gap="large")
    with ev_col2:
        ev_start_id = st.selectbox(
            "Current Room / Wing",
            options=room_ids,
            index=room_ids.index(st.session_state.start_room_id) if st.session_state.start_room_id in room_ids else 0,
            format_func=lambda rid: f"{room_by_id[rid].room_number} · {room_by_id[rid].name}",
            key="evac_start_room",
        )
        ev_start_room = room_by_id[ev_start_id]
        step_free_evac = st.checkbox("Accessible step-free evacuation only (no stairs)", value=False)

        ev_floor = floor_by_id[ev_start_room.floor_id]
        ev_nodes = [n for n in nodes if n.floor_id == ev_floor["id"]]
        ev_edges = [e for e in edges if e.floor_id == ev_floor["id"]]
        ev_markers = [m for m in markers if m.floor_id == ev_floor["id"]]

        evac_plan = compute_emergency_evacuation(
            ev_nodes,
            ev_edges,
            ev_markers,
            start_node_key=ev_start_room.door_node_key,
            start_label=ev_start_room.name,
            step_free_only=step_free_evac,
        )

        if evac_plan.recommended_exit and evac_plan.primary_route:
            st.success(
                f"**Recommended Exit:** {evac_plan.recommended_exit.name}\n\n"
                f"Distance: **{evac_plan.primary_route.total_distance_meters} m** · "
                f"Est. Time: **~{evac_plan.primary_route.estimated_seconds} s**"
            )
            for idx, stp in enumerate(evac_plan.primary_route.steps):
                st.write(f"**{idx + 1}.** {stp.instruction_kn if lang == 'kn' else stp.instruction}")
        else:
            st.warning("No verified unobstructed exit path found on this floor.")

        if evac_plan.alternative_exit and evac_plan.alternative_route:
            st.info(
                f"**Alternative Exit:** {evac_plan.alternative_exit.name} "
                f"({evac_plan.alternative_route.total_distance_meters} m)"
            )
        if evac_plan.nearest_extinguisher:
            st.write(f"**Nearest Extinguisher:** {evac_plan.nearest_extinguisher.name}")
        if evac_plan.assembly_points:
            st.write("**Assembly Points:** " + ", ".join(a.name for a in evac_plan.assembly_points))

        st.markdown("**Emergency Contacts**")
        for c in contacts:
            st.write(f"- **{c['title']}:** `{c['phone']}`")

        with st.expander("Report Fire / Corridor Hazard"):
            with st.form("hazard_report_form"):
                hz_title = st.text_input("Hazard Title", value="Blocked Corridor / Hazard")
                hz_msg = st.text_area("Location & Details")
                hz_by = st.text_input("Reported By", value="Campus User")
                if st.form_submit_button("Broadcast Safety Alert", type="primary"):
                    if hz_msg.strip():
                        db.create_alert(college["id"], hz_title, hz_msg.strip(), "warning", hz_by)
                        st.success("Safety alert recorded.")
                        st.rerun()

    with ev_col1:
        evac_png = render_floor_map(
            BASE_DIR,
            ev_floor,
            rooms=rooms,
            nodes=ev_nodes,
            edges=ev_edges,
            emergency_markers=ev_markers,
            wifi_networks=wifi_networks,
            evacuation_plan=evac_plan,
            start_room=ev_start_room,
            show_graph=False,
            show_wifi=False,
            emergency_mode=True,
        )
        st.image(evac_png, caption=f"Verified Evacuation Blueprint — {ev_floor['name']}", use_container_width=True)

# ==============================================================================
# TAB 3: WI-FI ZONES
# ==============================================================================
with tab_wifi:
    st.subheader("Campus Wi-Fi Network Availability")
    online_aps = [w for w in wifi_networks if w["status"] == "online"]
    fastest_ap = max(online_aps, key=lambda w: w["speed_mbps"], default=None)
    total_clients = sum(w["connected_devices"] for w in wifi_networks)

    k1, k2, k3 = st.columns(3)
    k1.metric("Active Online Hotspots", f"{len(online_aps)} / {len(wifi_networks)}")
    k2.metric("Peak Campus Speed", f"{fastest_ap['speed_mbps']} Mbps" if fastest_ap else "N/A")
    k3.metric("Connected Clients", f"{total_clients}")

    wf1, wf2 = st.columns(2)
    wifi_floor_filter = wf1.selectbox(
        "Filter by Floor",
        options=["all"] + [f["id"] for f in floors],
        format_func=lambda fid: "All Floors" if fid == "all" else floor_by_id[fid]["name"],
    )
    wifi_status_filter = wf2.selectbox("Filter by Status", options=["all", "online", "degraded", "maintenance"])

    filtered_wifi = [
        w
        for w in wifi_networks
        if (wifi_floor_filter == "all" or w["floor_id"] == wifi_floor_filter)
        and (wifi_status_filter == "all" or w["status"] == wifi_status_filter)
    ]

    def _nearest_room(wifi_row: dict) -> Room | None:
        fl_rooms = [r for r in rooms if r.floor_id == wifi_row["floor_id"]]
        if not fl_rooms:
            return None
        return min(fl_rooms, key=lambda r: math.hypot(r.x - wifi_row["x"], r.y - wifi_row["y"]))

    cols = st.columns(3)
    for i, w in enumerate(filtered_wifi):
        with cols[i % 3]:
            with st.container(border=True):
                fl_name = floor_by_id.get(w["floor_id"], {}).get("name", "Campus")
                st.caption(f"{fl_name} · {w['band']}")
                st.markdown(f"**`{w['ssid']}`**")
                st.write(w["zone_name"])
                st.write(f"Speed: **{w['speed_mbps']} Mbps** · Signal: **{w['signal_strength_dbm']} dBm**")
                st.caption(f"Status: {w['status'].upper()} · Auth: {w['auth_type']} · {w['connected_devices']} devices")
                near = _nearest_room(w)
                if near and st.button(f"Set Destination ({near.room_number})", key=f"wifi_nav_{w['id']}", use_container_width=True):
                    st.session_state.dest_room_id = near.id
                    st.session_state.selected_floor_id = near.floor_id
                    st.success(f"Destination set to {near.name} — switch to Indoor Navigation tab.")

# ==============================================================================
# TAB 4: OUTDOOR CAMPUS MAP & BLE CALIBRATION
# ==============================================================================
with tab_outdoor:
    out_left, out_right = st.columns([0.65, 0.35], gap="large")
    with out_left:
        st.subheader(f"Outdoor Campus Map · {college_name}")
        lat = float(college.get("latitude", 37.8719))
        lon = float(college.get("longitude", -122.2585))
        delta = 0.004
        osm_url = (
            f"https://www.openstreetmap.org/export/embed.html?"
            f"bbox={lon - delta}%2C{lat - delta}%2C{lon + delta}%2C{lat + delta}"
            f"&layer=mapnik&marker={lat}%2C{lon}"
        )
        components.iframe(osm_url, height=460)
        st.caption(f"Campus GPS Coordinates: {lat:.4f}, {lon:.4f}")

    with out_right:
        st.markdown("#### Campus Buildings")
        for b in campus["buildings"]:
            with st.container(border=True):
                st.markdown(f"**{b['name']} ({b['code']})**")
                st.caption(b["description"])
                st.write(f"GPS: `{b['latitude']:.4f}, {b['longitude']:.4f}` · {b['floors_count']} floors")

        st.markdown("#### Indoor Wi-Fi & BLE Beacons")
        beacons = [
            ("BLE-CU-N1", "North Lobby Beacon", "CU-Lobby-5G", "-54 dBm", "LOB-01"),
            ("BLE-CU-W1", "CS Labs Corridor Beacon", "CU-CSE-WiFi", "-58 dBm", "101"),
            ("BLE-CU-E1", "ECE & Physics Wing Beacon", "CU-ECE-WiFi", "-61 dBm", "104"),
            ("BLE-CU-S1", "South Classrooms Beacon", "CU-South-WiFi", "-63 dBm", "110"),
        ]
        for bid, label, ssid, rssi, rnum in beacons:
            if st.button(f"{label} ({ssid} · {rssi})", key=bid, use_container_width=True):
                matched_r = next((r for r in rooms if r.room_number == rnum), rooms[0])
                st.session_state.start_room_id = matched_r.id
                st.session_state.selected_floor_id = matched_r.floor_id
                st.success(f"Start calibrated to {matched_r.room_number} · {matched_r.name}")

# ==============================================================================
# TAB 5: DIRECTORY & SCHEDULE
# ==============================================================================
with tab_directory:
    dir_left, dir_right = st.columns(2, gap="large")
    with dir_left:
        st.subheader("Teachers & Availability")
        for f_row in faculty:
            with st.container(border=True):
                c1, c2 = st.columns([0.72, 0.28], vertical_alignment="center")
                with c1:
                    st.markdown(f"**{f_row['name']}**")
                    st.caption(f_row["designation"])
                    if f_row.get("availability"):
                        st.write(f"Available: `{f_row['availability']}`")
                with c2:
                    office_id = f_row.get("office_room_id")
                    if office_id and office_id in room_by_id:
                        off = room_by_id[office_id]
                        if st.button(f"Go ({off.room_number})", key=f"fac_{f_row['id']}", use_container_width=True):
                            st.session_state.dest_room_id = off.id
                            st.session_state.selected_floor_id = off.floor_id
                            st.success(f"Destination set to {off.name}")

    with dir_right:
        st.subheader("Campus Announcements")
        for a in announcements:
            with st.container(border=True):
                st.markdown(f"**{a['title']}** · _{a['category'].title()}_")
                st.write(a["body"])

    st.subheader("Room Availability & Class Timetable")
    acad_rooms = [r for r in rooms if r.category in {"classroom", "laboratory", "hall", "office"}]
    tt_df = pd.DataFrame(
        [
            {
                "Room Number": r.room_number,
                "Name": r.name,
                "Department": r.department,
                "Schedule": r.timetable_summary,
            }
            for r in acad_rooms
        ]
    )
    st.dataframe(tt_df, use_container_width=True, hide_index=True)

    st.subheader("Feedback & Map Error Reporting")
    with st.form("feedback_form"):
        fb1, fb2, fb3 = st.columns(3)
        reporter = fb1.text_input("Your Name (optional)")
        rtype = fb2.selectbox(
            "Report Type",
            ["map_error", "blocked_path", "hazard", "suggestion"],
            format_func=lambda v: {
                "map_error": "Room Position / Label Correction",
                "blocked_path": "Temporarily Blocked Corridor",
                "hazard": "Safety / Exit Maintenance Issue",
                "suggestion": "Navigation Suggestion",
            }[v],
        )
        rel_room = fb3.selectbox(
            "Related Room (optional)",
            options=[None] + room_ids,
            format_func=lambda rid: "None" if rid is None else f"{room_by_id[rid].room_number} · {room_by_id[rid].name}",
        )
        fb_msg = st.text_input("Describe the map correction, blocked pathway, or feedback...")
        if st.form_submit_button("Submit Report", type="primary"):
            if fb_msg.strip():
                db.submit_feedback(
                    college["id"],
                    active_floor["id"],
                    rel_room,
                    reporter.strip() or "Student / Visitor",
                    rtype,
                    fb_msg.strip(),
                )
                st.success("Thank you. Your report has been saved for campus administrators.")

# ==============================================================================
# TAB 6: ADMIN PORTAL
# ==============================================================================
with tab_admin:
    st.subheader("Campus Administrator Portal")

    if st.session_state.admin_user is None:
        auth_l, auth_r = st.columns(2, gap="large")
        with auth_l:
            with st.form("admin_login_form"):
                st.markdown("**Sign In**")
                email = st.text_input("Administrator Email", value="admin@californiauniversity.edu")
                password = st.text_input("Password", type="password", placeholder="Default local demo: Admin@1234")
                if st.form_submit_button("Sign In", type="primary"):
                    usr = db.authenticate_user(email, password)
                    if usr:
                        st.session_state.admin_user = usr
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")
        with auth_r:
            with st.form("admin_register_form"):
                st.markdown("**Register New Administrator**")
                reg_name = st.text_input("Full Name")
                reg_email = st.text_input("Email")
                reg_pw = st.text_input("Password (6+ chars)", type="password")
                if st.form_submit_button("Create Account"):
                    ok, msg = db.register_user(reg_email, reg_pw, reg_name)
                    if ok:
                        st.session_state.admin_user = {"email": reg_email, "name": reg_name or "Campus Admin", "role": "campus_admin"}
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        u = st.session_state.admin_user
        top_a1, top_a2 = st.columns([0.8, 0.2])
        top_a1.success(f"Signed in as **{u['name']}** ({u['email']})")
        if top_a2.button("Sign Out", use_container_width=True):
            st.session_state.admin_user = None
            st.rerun()

        adm_t1, adm_t2, adm_t3, adm_t4 = st.tabs(
            ["Corridors & Exits", "Rooms & Wi-Fi", "Alerts & Feedback", "Navigation Analytics"]
        )

        with adm_t1:
            st.markdown("**Toggle Corridor Edge Blockages (Live Dijkstra Rerouting)**")
            fl_sel = st.selectbox(
                "Floor Edges",
                options=[f["id"] for f in floors],
                format_func=lambda fid: floor_by_id[fid]["name"],
                key="adm_edge_fl",
            )
            fl_edges_adm = [e for e in edges if e.floor_id == fl_sel][:20]
            for e in fl_edges_adm:
                c1, c2 = st.columns([0.75, 0.25], vertical_alignment="center")
                c1.write(f"`{e.from_node_key}` ↔ `{e.to_node_key}` ({e.distance_meters} m)")
                label = "Unblock" if e.is_blocked else "Block Path"
                if c2.button(label, key=f"edge_tog_{e.id}", use_container_width=True):
                    db.toggle_edge_blocked(e.id, not e.is_blocked)
                    st.rerun()

            st.markdown("**Emergency Exits Status**")
            for m in [mk for mk in markers if mk.floor_id == fl_sel and "exit" in mk.marker_type]:
                m1, m2 = st.columns([0.75, 0.25], vertical_alignment="center")
                m1.write(f"{m.name} — **{m.status.upper()}**")
                new_st = "available" if m.status == "blocked" else "blocked"
                if m2.button(f"Mark {new_st}", key=f"mk_tog_{m.id}", use_container_width=True):
                    db.set_marker_status(m.id, new_st)
                    st.rerun()

        with adm_t2:
            with st.form("add_room_form"):
                st.markdown("**Add New Campus Room**")
                r1, r2, r3 = st.columns(3)
                nr_num = r1.text_input("Room Number", placeholder="e.g. 215")
                nr_name = r2.text_input("Room Name", placeholder="e.g. Cloud Computing Lab")
                nr_dept = r3.text_input("Department", value="Computer Science")
                r4, r5 = st.columns(2)
                nr_fl = r4.selectbox("Floor", options=[f["id"] for f in floors], format_func=lambda fid: floor_by_id[fid]["name"])
                fl_node_keys = [n.node_key for n in nodes if n.floor_id == nr_fl]
                nr_node = r5.selectbox("Connected Corridor Node", options=fl_node_keys)
                nr_desc = st.text_input("Description")
                if st.form_submit_button("Add Room", type="primary"):
                    if nr_num.strip() and nr_name.strip():
                        ref_node = next((n for n in nodes if n.node_key == nr_node), None)
                        db.create_room(
                            college["id"],
                            campus["buildings"][0]["id"],
                            nr_fl,
                            nr_num.strip(),
                            nr_name.strip(),
                            nr_dept.strip(),
                            "classroom",
                            nr_node,
                            ref_node.x if ref_node else 500.0,
                            ref_node.y if ref_node else 280.0,
                            nr_desc.strip(),
                        )
                        st.success("Room added to SQLite campus database.")
                        st.rerun()

            st.markdown("**Wi-Fi Hotspot Operational Control**")
            for w in wifi_networks:
                wc1, wc2 = st.columns([0.72, 0.28], vertical_alignment="center")
                wc1.write(f"`{w['ssid']}` — {w['zone_name']} (**{w['status']}**)")
                nxt_w = "maintenance" if w["status"] == "online" else "online"
                if wc2.button(f"Set {nxt_w}", key=f"wf_adm_{w['id']}", use_container_width=True):
                    db.set_wifi_status(w["id"], nxt_w)
                    st.rerun()

        with adm_t3:
            st.markdown("**Active Safety Alerts**")
            if not active_alerts:
                st.caption("No active safety alerts.")
            for al in active_alerts:
                ac1, ac2 = st.columns([0.8, 0.2], vertical_alignment="center")
                ac1.warning(f"**{al['title']}**: {al['message']}")
                if ac2.button("Clear Alert", key=f"clr_al_{al['id']}", use_container_width=True):
                    db.clear_alert(al["id"])
                    st.rerun()

            st.markdown("**User Feedback & Map Reports**")
            for fb in feedback_reports:
                fc1, fc2 = st.columns([0.8, 0.2], vertical_alignment="center")
                fc1.write(f"[{fb['status'].upper()}] **{fb['report_type']}** by {fb['reporter_name']}: {fb['message']}")
                if fb["status"] == "open" and fc2.button("Resolve", key=f"res_fb_{fb['id']}", use_container_width=True):
                    db.resolve_feedback(fb["id"])
                    st.rerun()

        with adm_t4:
            if recent_logs:
                logs_df = pd.DataFrame(recent_logs)
                st.dataframe(logs_df[["from_room_name", "to_room_name", "route_mode", "distance_meters", "created_at"]], use_container_width=True, hide_index=True)
                mode_counts = logs_df["route_mode"].value_counts()
                st.bar_chart(mode_counts)
            else:
                st.caption("Navigate between rooms to record route analytics.")
