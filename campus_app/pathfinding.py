from __future__ import annotations

import heapq
import math
from typing import Iterable, Optional

from .models import (
    ComputedRoute,
    CrossFloorRouteResult,
    EmergencyEvacuationPlan,
    EmergencyMarker,
    NavEdge,
    NavNode,
    Room,
    RouteStep,
)


def _angle_between(a_x: float, a_y: float, b_x: float, b_y: float) -> float:
    return math.atan2(b_y - a_y, b_x - a_x)


def _normalize_angle_diff(diff: float) -> float:
    d = diff
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


def get_turn_direction(prev: NavNode, curr: NavNode, nxt: NavNode) -> str:
    a1 = _angle_between(prev.x, prev.y, curr.x, curr.y)
    a2 = _angle_between(curr.x, curr.y, nxt.x, nxt.y)
    diff = _normalize_angle_diff(a2 - a1)
    if abs(diff) < 0.42:
        return "straight"
    return "right" if diff > 0 else "left"


def _build_step_instructions(
    path_nodes: list[NavNode],
    edges: list[NavEdge],
    start_label: str,
    end_label: str,
    is_emergency: bool,
) -> list[RouteStep]:
    if not path_nodes:
        return []
    if len(path_nodes) == 1:
        n = path_nodes[0]
        return [
            RouteStep(
                instruction=f"You are already at {end_label}.",
                instruction_kn=f"ನೀವು ಈಗಾಗಲೇ {end_label} ಬಳಿ ಇದ್ದೀರಿ.",
                distance_meters=0.0,
                node_key=n.node_key,
                x=n.x,
                y=n.y,
                direction="arrive",
                floor_id=n.floor_id,
                node_type=n.node_type,
            )
        ]

    edge_lookup: dict[tuple[str, str], float] = {}
    for e in edges:
        edge_lookup[(e.from_node_key, e.to_node_key)] = e.distance_meters
        edge_lookup[(e.to_node_key, e.from_node_key)] = e.distance_meters

    node_lookup = {n.node_key: n for n in path_nodes}

    def edge_distance(a: str, b: str) -> float:
        if (a, b) in edge_lookup:
            return edge_lookup[(a, b)]
        na = node_lookup.get(a)
        nb = node_lookup.get(b)
        if not na or not nb:
            return 5.0
        return round(math.hypot(nb.x - na.x, nb.y - na.y) * 0.08, 1)

    first = path_nodes[0]
    steps: list[RouteStep] = [
        RouteStep(
            instruction=(
                f"Leave {start_label} immediately via the designated corridor exit."
                if is_emergency
                else f"Start from {start_label} and step into the adjacent corridor."
            ),
            instruction_kn=(
                f"{start_label} ನಿಂದ ತಕ್ಷಣವೇ ತುರ್ತು ನಿರ್ಗಮನ ಕಾರಿಡಾರ್ ಮೂಲಕ ಹೊರಡಿ."
                if is_emergency
                else f"{start_label} ನಿಂದ ಪ್ರಾರಂಭಿಸಿ ಪಕ್ಕದ ಕಾರಿಡಾರ್‌ಗೆ ಬನ್ನಿ."
            ),
            distance_meters=0.0,
            node_key=first.node_key,
            x=first.x,
            y=first.y,
            direction="start",
            floor_id=first.floor_id,
            node_type=first.node_type,
        )
    ]

    accumulated = 0.0
    for i in range(1, len(path_nodes)):
        prev = path_nodes[i - 1]
        curr = path_nodes[i]
        accumulated += edge_distance(prev.node_key, curr.node_key)
        is_last = i == len(path_nodes) - 1

        if is_last:
            rounded = round(accumulated)
            steps.append(
                RouteStep(
                    instruction=(
                        f"Proceed {rounded} m to {end_label} and continue outside to the verified assembly area."
                        if is_emergency
                        else f"Continue {rounded} m and arrive at {end_label}."
                    ),
                    instruction_kn=(
                        f"{rounded} ಮೀ ಮುಂದೆ ಸಾಗಿ {end_label} ಮೂಲಕ ಸುರಕ್ಷಿತ ಸಭಾ ಸ್ಥಳಕ್ಕೆ ತೆರಳಿ."
                        if is_emergency
                        else f"{rounded} ಮೀ ಮುಂದೆ ಸಾಗಿ {end_label} ತಲುಪಿ."
                    ),
                    distance_meters=round(accumulated, 1),
                    node_key=curr.node_key,
                    x=curr.x,
                    y=curr.y,
                    direction="exit" if is_emergency else "arrive",
                    floor_id=curr.floor_id,
                    node_type=curr.node_type,
                )
            )
            break

        nxt = path_nodes[i + 1]
        turn = get_turn_direction(prev, curr, nxt)
        if (
            turn != "straight"
            or curr.node_type in {"staircase", "entrance", "lift"}
            or "cy_center" in curr.node_key
        ):
            dist_rounded = max(1, round(accumulated))
            if turn == "left":
                instr = f"Walk {dist_rounded} m along {curr.label}, then turn left."
                instr_kn = f"{curr.label} ಬಳಿ {dist_rounded} ಮೀ ನಡೆದು ಎಡಕ್ಕೆ ತಿರುಗಿ."
            elif turn == "right":
                instr = f"Walk {dist_rounded} m along {curr.label}, then turn right."
                instr_kn = f"{curr.label} ಬಳಿ {dist_rounded} ಮೀ ನಡೆದು ಬಲಕ್ಕೆ ತಿರುಗಿ."
            else:
                instr = f"Continue straight {dist_rounded} m past {curr.label}."
                instr_kn = f"{curr.label} ದಾಟಿ {dist_rounded} ಮೀ ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ."

            steps.append(
                RouteStep(
                    instruction=instr,
                    instruction_kn=instr_kn,
                    distance_meters=float(dist_rounded),
                    node_key=curr.node_key,
                    x=curr.x,
                    y=curr.y,
                    direction=turn,
                    floor_id=curr.floor_id,
                    node_type=curr.node_type,
                )
            )
            accumulated = 0.0

    return steps


def _count_route_turns(path_nodes: list[NavNode]) -> int:
    turns = 0
    for i in range(1, len(path_nodes) - 1):
        t = get_turn_direction(path_nodes[i - 1], path_nodes[i], path_nodes[i + 1])
        if t in {"left", "right"}:
            turns += 1
    return turns


def find_indoor_route(
    nodes: list[NavNode],
    edges: list[NavEdge],
    start_node_key: str,
    end_node_key: str,
    mode: str = "shortest",
    start_label: str = "Starting Location",
    end_label: str = "Destination",
    avoid_lifts: bool = False,
) -> Optional[ComputedRoute]:
    node_map = {n.node_key: n for n in nodes}
    start_node = node_map.get(start_node_key)
    end_node = node_map.get(end_node_key)
    if not start_node or not end_node:
        return None
    if start_node.is_blocked or end_node.is_blocked:
        return None

    if start_node_key == end_node_key:
        return ComputedRoute(
            path_nodes=[start_node],
            total_distance_meters=0.0,
            estimated_seconds=5,
            steps=_build_step_instructions(
                [start_node], edges, start_label, end_label, mode == "emergency"
            ),
            accessible=start_node.is_accessible,
            mode=mode,
            warnings=[],
            turn_count=0,
            strategy_note="Already at destination",
        )

    adj: dict[str, list[tuple[str, float, NavEdge, NavNode, NavNode]]] = {
        n.node_key: [] for n in nodes
    }

    for edge in edges:
        if edge.is_blocked:
            continue
        from_n = node_map.get(edge.from_node_key)
        to_n = node_map.get(edge.to_node_key)
        if not from_n or not to_n or from_n.is_blocked or to_n.is_blocked:
            continue

        if mode == "stair_free":
            if edge.is_staircase:
                continue
            if (from_n.node_type == "staircase" and edge.from_node_key != start_node_key) or (
                to_n.node_type == "staircase" and edge.to_node_key != end_node_key
            ):
                continue

        if mode == "emergency" or avoid_lifts:
            if from_n.node_type == "lift" or to_n.node_type == "lift":
                continue

        # Keep indoor navigation (including Shortest) on enclosed indoor corridors rather than cutting through the open courtyard
        touches_courtyard = ("cy_" in edge.from_node_key) or ("cy_" in edge.to_node_key)
        if touches_courtyard and ("cy_" not in start_node_key) and ("cy_" not in end_node_key):
            continue

        adj[edge.from_node_key].append((edge.to_node_key, edge.distance_meters, edge, from_n, to_n))
        adj[edge.to_node_key].append((edge.from_node_key, edge.distance_meters, edge, to_n, from_n))

    START_PREV = "__START__"
    start_state = (start_node_key, START_PREV)
    cost_score: dict[tuple[str, str], float] = {start_state: 0.0}
    raw_dist_score: dict[tuple[str, str], float] = {start_state: 0.0}
    came_from: dict[tuple[str, str], tuple[str, str]] = {}

    heap: list[tuple[float, tuple[str, str]]] = [(0.0, start_state)]
    best_end_state: Optional[tuple[str, str]] = None

    while heap:
        lowest_cost, current_state = heapq.heappop(heap)
        if lowest_cost > cost_score.get(current_state, float("inf")):
            continue

        curr_key, prev_key = current_state
        if curr_key == end_node_key:
            best_end_state = current_state
            break

        curr_node = node_map[curr_key]
        prev_node = node_map.get(prev_key) if prev_key != START_PREV else None

        for nbr_to, raw_dist, edge, from_n, to_n in adj.get(curr_key, []):
            if nbr_to == prev_key:
                continue

            turn_dir = get_turn_direction(prev_node, curr_node, to_n) if prev_node else "straight"
            is_turn = 1 if turn_dir in {"left", "right"} else 0

            step_weight = raw_dist
            if mode == "shortest":
                step_weight = raw_dist
            elif mode == "easiest":
                is_courtyard = ("cy_" in from_n.node_key) or ("cy_" in to_n.node_key)
                is_narrow_door = (not edge.is_wheelchair_accessible) and (not edge.is_staircase)
                corridor_factor = (
                    0.84
                    if (from_n.node_type == "corridor" and to_n.node_type == "corridor")
                    else 1.0
                )
                obstacle_penalty = (
                    52.0
                    if is_courtyard
                    else 90.0
                    if is_narrow_door
                    else 4.0
                    if edge.is_staircase
                    else 0.0
                )
                turn_penalty = is_turn * 18.0
                step_weight = raw_dist * corridor_factor + obstacle_penalty + turn_penalty
            elif mode == "stair_free":
                step_weight = raw_dist + is_turn * 2.0
            elif mode == "emergency":
                step_weight = raw_dist * 0.85 if edge.is_evacuation_path else raw_dist * 1.45

            next_state = (nbr_to, curr_key)
            tentative_cost = lowest_cost + step_weight
            if tentative_cost < cost_score.get(next_state, float("inf")):
                cost_score[next_state] = tentative_cost
                raw_dist_score[next_state] = raw_dist_score[current_state] + raw_dist
                came_from[next_state] = current_state
                heapq.heappush(heap, (tentative_cost, next_state))

    if best_end_state is None:
        return None

    path_keys: list[str] = []
    trace: Optional[tuple[str, str]] = best_end_state
    while trace is not None:
        path_keys.append(trace[0])
        trace = came_from.get(trace)
    path_keys.reverse()

    path_nodes = [node_map[k] for k in path_keys if k in node_map]
    total_distance_meters = round(raw_dist_score.get(best_end_state, 0.0), 1)
    turn_count = _count_route_turns(path_nodes)
    speed_mps = 1.5 if mode == "emergency" else 1.2
    estimated_seconds = max(5, round(total_distance_meters / speed_mps))

    used_narrow_shortcut = False
    for idx in range(1, len(path_nodes)):
        p_node = path_nodes[idx - 1]
        c_node = path_nodes[idx]
        matched = next(
            (
                e
                for e in edges
                if (e.from_node_key == p_node.node_key and e.to_node_key == c_node.node_key)
                or (e.from_node_key == c_node.node_key and e.to_node_key == p_node.node_key)
            ),
            None,
        )
        if matched and (not matched.is_wheelchair_accessible) and (not matched.is_staircase):
            used_narrow_shortcut = True
            break

    strategy_note = ""
    if mode == "shortest":
        strategy_note = "Minimum physical indoor corridor distance"
    elif mode == "easiest":
        plural = "" if turn_count == 1 else "s"
        strategy_note = f"Simplest covered corridor route ({turn_count} turn{plural})"
    elif mode == "stair_free":
        strategy_note = (
            "Zero-stair flat pathway via direct indoor connector"
            if used_narrow_shortcut
            else "Zero-stair flat covered corridor route"
        )

    return ComputedRoute(
        path_nodes=path_nodes,
        total_distance_meters=total_distance_meters,
        estimated_seconds=estimated_seconds,
        steps=_build_step_instructions(
            path_nodes, edges, start_label, end_label, mode == "emergency"
        ),
        accessible=(mode == "stair_free") or all(n.is_accessible for n in path_nodes),
        mode=mode,
        warnings=[],
        turn_count=turn_count,
        strategy_note=strategy_note,
    )


def find_cross_floor_route(
    nodes: list[NavNode],
    edges: list[NavEdge],
    start_room: Room,
    end_room: Room,
    start_floor_name: str,
    end_floor_name: str,
    mode: str = "shortest",
) -> Optional[CrossFloorRouteResult]:
    s_nodes = [n for n in nodes if n.floor_id == start_room.floor_id]
    s_edges = [e for e in edges if e.floor_id == start_room.floor_id]
    d_nodes = [n for n in nodes if n.floor_id == end_room.floor_id]
    d_edges = [e for e in edges if e.floor_id == end_room.floor_id]

    connector_groups = [
        ("lift", "Campus Elevator / Lift", lambda k: "lift" in k),
        ("staircase", "Main Central Staircase", lambda k: "main_stairs" in k),
        ("staircase", "SW Emergency Staircase", lambda k: "sw_exit" in k),
        ("staircase", "SE Emergency Staircase", lambda k: "se_exit" in k),
    ]

    allowed = (
        [g for g in connector_groups if g[0] == "lift"]
        if mode == "stair_free"
        else connector_groups
    )

    candidates: list[tuple[float, CrossFloorRouteResult]] = []
    for c_type, label, matcher in allowed:
        s_conn = next((n for n in s_nodes if matcher(n.node_key) and not n.is_blocked), None)
        d_conn = next((n for n in d_nodes if matcher(n.node_key) and not n.is_blocked), None)
        if not s_conn or not d_conn:
            continue

        leg1 = find_indoor_route(
            s_nodes,
            s_edges,
            start_room.door_node_key,
            s_conn.node_key,
            mode=mode,
            start_label=start_room.name,
            end_label=s_conn.label,
        )
        leg2 = find_indoor_route(
            d_nodes,
            d_edges,
            d_conn.node_key,
            end_room.door_node_key,
            mode=mode,
            start_label=d_conn.label,
            end_label=end_room.name,
        )
        if not leg1 or not leg2:
            continue

        vertical_meters = 4.0 if c_type == "lift" else 8.0
        vertical_seconds = 32 if c_type == "lift" else 25
        total_dist = round(leg1.total_distance_meters + leg2.total_distance_meters + vertical_meters, 1)
        est_secs = leg1.estimated_seconds + leg2.estimated_seconds + vertical_seconds
        total_turns = leg1.turn_count + leg2.turn_count

        transition_instr = (
            f"Take {s_conn.label} (Step-Free Elevator) to {end_floor_name}."
            if c_type == "lift"
            else f"Take {s_conn.label} to {end_floor_name}."
        )
        transition_kn = (
            f"{end_floor_name} ಗೆ {'ಲಿಫ್ಟ್' if c_type == 'lift' else 'ಮೆಟ್ಟಿಲುಗಳ'} ಮೂಲಕ ತೆರಳಿ."
        )

        score = total_dist
        if mode == "easiest":
            main_bonus = -30.0 if "Main" in label else (-10.0 if c_type == "lift" else 45.0)
            score = total_dist + total_turns * 14.0 + main_bonus

        if mode == "stair_free":
            strategy_note = f"100% stair-free route via {label} (0 stairs)"
        elif mode == "easiest":
            strategy_note = f"Simplest cross-floor route via {label} ({total_turns} turns)"
        else:
            strategy_note = f"Fastest route via {label} ({total_dist} m)"

        transition_step = RouteStep(
            instruction=transition_instr,
            instruction_kn=transition_kn,
            distance_meters=vertical_meters,
            node_key=f"{s_conn.node_key}->{d_conn.node_key}",
            x=s_conn.x,
            y=s_conn.y,
            direction="straight",
            floor_id=start_room.floor_id,
            node_type=c_type,
        )

        result = CrossFloorRouteResult(
            leg1=leg1,
            leg2=leg2,
            connector_type="lift" if c_type == "lift" else "staircase",
            connector_label=label,
            total_distance_meters=total_dist,
            estimated_seconds=est_secs,
            turn_count=total_turns,
            strategy_note=strategy_note,
            all_steps=[*leg1.steps, transition_step, *leg2.steps],
        )
        candidates.append((score, result))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def find_nearest_node_key(nodes: list[NavNode], x: float, y: float) -> Optional[str]:
    best_key: Optional[str] = None
    best_dist = float("inf")
    for n in nodes:
        if n.is_blocked:
            continue
        d = math.hypot(n.x - x, n.y - y)
        if d < best_dist:
            best_dist = d
            best_key = n.node_key
    return best_key


def compute_emergency_evacuation(
    nodes: list[NavNode],
    edges: list[NavEdge],
    markers: list[EmergencyMarker],
    start_node_key: str,
    start_label: str,
    step_free_only: bool = False,
) -> EmergencyEvacuationPlan:
    exit_types = {"primary_exit", "secondary_exit", "fire_exit", "staircase_exit"}
    verified_exits = [
        m
        for m in markers
        if m.marker_type in exit_types and m.is_verified and m.status == "available"
    ]

    node_keys = {n.node_key for n in nodes}
    candidates: list[tuple[float, EmergencyMarker, ComputedRoute]] = []

    for exit_marker in verified_exits:
        target_key = (
            exit_marker.node_key
            if exit_marker.node_key and exit_marker.node_key in node_keys
            else find_nearest_node_key(nodes, exit_marker.x, exit_marker.y)
        )
        if not target_key:
            continue

        route = find_indoor_route(
            nodes,
            edges,
            start_node_key,
            target_key,
            mode="stair_free" if step_free_only else "emergency",
            start_label=start_label,
            end_label=exit_marker.name,
            avoid_lifts=True,
        )
        if route:
            priority_bonus = -3.0 if exit_marker.marker_type == "primary_exit" else 0.0
            candidates.append((route.total_distance_meters + priority_bonus, exit_marker, route))

    candidates.sort(key=lambda item: item[0])
    primary = candidates[0] if len(candidates) > 0 else None
    alternative = candidates[1] if len(candidates) > 1 else None

    start_node = next((n for n in nodes if n.node_key == start_node_key), None)
    extinguishers = [
        m for m in markers if m.marker_type == "extinguisher" and m.status == "available"
    ]
    nearest_ext: Optional[EmergencyMarker] = None
    if start_node and extinguishers:
        nearest_ext = min(
            extinguishers,
            key=lambda ext: math.hypot(ext.x - start_node.x, ext.y - start_node.y),
        )

    assembly_points = [m for m in markers if m.marker_type == "assembly_point"]
    warnings: list[str] = []
    if not primary:
        warnings.append(
            "No verified unobstructed evacuation route was found from this point. Follow posted fire signage and emergency personnel immediately."
        )
    if any(m.marker_type in exit_types and m.status == "blocked" for m in markers):
        warnings.append(
            "One or more campus exits are currently marked blocked/maintenance. Routing strictly avoids closed exits."
        )
    warnings.append(
        "Do not use elevators or lifts during fire evacuation. Follow official fire alarms and emergency responders."
    )

    return EmergencyEvacuationPlan(
        recommended_exit=primary[1] if primary else None,
        primary_route=primary[2] if primary else None,
        alternative_exit=alternative[1] if alternative else None,
        alternative_route=alternative[2] if alternative else None,
        nearest_extinguisher=nearest_ext,
        assembly_points=assembly_points,
        warnings=warnings,
    )


def resolve_room_search(rooms: Iterable[Room], query: str) -> list[Room]:
    q = query.strip().lower()
    room_list = list(rooms)
    if not q:
        return room_list
    return [
        r
        for r in room_list
        if q in r.name.lower()
        or q in r.room_number.lower()
        or q in r.department.lower()
        or q in r.category.lower()
        or q in (r.description or "").lower()
    ]


def get_step_visual_asset(step: RouteStep) -> tuple[str, str, str]:
    key = (step.node_key or "").lower()
    ntype = step.node_type or ""
    if step.direction in {"arrive", "exit"}:
        return (
            "assets/images/bp_destination_pin.jpg",
            "Destination Entrance",
            "Blue entrance pin marks your room or verified exit door",
        )
    if ntype in {"lift", "staircase"} or "->" in key or "lift" in key or "stairs" in key:
        return (
            "assets/images/bp_floor_transition.jpg",
            "Elevator & Stairwell Connector",
            "Vertical transfer hub linking Ground, First & Second Floors",
        )
    if "cy_" in key:
        return (
            "assets/images/bp_courtyard_route.jpg",
            "Central Quadrangle Path",
            "Central quadrangle blueprint view",
        )
    if step.direction in {"left", "right"}:
        return (
            "assets/images/bp_turn_corner.jpg",
            f"Corridor Junction — Turn {step.direction.capitalize()}",
            "Blueprint corridor intersection marker ahead",
        )
    return (
        "assets/images/bp_corridor_straight.jpg",
        "Covered Corridor Walkway",
        "Continue straight along the highlighted indoor corridor",
    )
