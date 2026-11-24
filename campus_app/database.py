from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .models import EmergencyMarker, NavEdge, NavNode, Room


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    s = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), s.encode("utf-8"), 120_000).hex()
    return f"{s}:{digest}"


def _verify_password(password: str, stored: str) -> bool:
    if ":" not in stored:
        return False
    salt, expected = stored.split(":", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return secrets.compare_digest(check, expected)


class CampusDatabase:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.db_path = base_dir / "data" / "campus.db"
        self.seed_path = base_dir / "data" / "campus_seed.json"
        self._init_schema()
        self.ensure_seeded()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS colleges (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    short_code TEXT NOT NULL,
                    logo_url TEXT NOT NULL,
                    address TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    contact_email TEXT NOT NULL,
                    contact_phone TEXT NOT NULL,
                    website TEXT DEFAULT '',
                    departments_json TEXT NOT NULL DEFAULT '[]',
                    total_buildings INTEGER NOT NULL DEFAULT 1,
                    total_floors INTEGER NOT NULL DEFAULT 1,
                    is_default INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS buildings (
                    id INTEGER PRIMARY KEY,
                    college_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    floors_count INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS floors (
                    id INTEGER PRIMARY KEY,
                    college_id INTEGER NOT NULL,
                    building_id INTEGER NOT NULL,
                    floor_number INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    map_image_url TEXT NOT NULL,
                    map_width INTEGER NOT NULL DEFAULT 1000,
                    map_height INTEGER NOT NULL DEFAULT 562,
                    scale_meters_per_unit REAL NOT NULL DEFAULT 0.08,
                    is_default INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    building_id INTEGER NOT NULL,
                    floor_id INTEGER NOT NULL,
                    room_number TEXT NOT NULL,
                    name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    category TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    door_node_key TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    accessibility_info TEXT DEFAULT '',
                    is_wheelchair_accessible INTEGER NOT NULL DEFAULT 1,
                    availability_status TEXT NOT NULL DEFAULT 'available',
                    current_subject TEXT DEFAULT '',
                    faculty_in_charge TEXT DEFAULT '',
                    timetable_summary TEXT DEFAULT '',
                    qr_code_value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS nav_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    floor_id INTEGER NOT NULL,
                    node_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    is_accessible INTEGER NOT NULL DEFAULT 1,
                    is_blocked INTEGER NOT NULL DEFAULT 0,
                    connects_to_floor_id INTEGER,
                    connects_to_node_key TEXT
                );

                CREATE TABLE IF NOT EXISTS nav_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    floor_id INTEGER NOT NULL,
                    from_node_key TEXT NOT NULL,
                    to_node_key TEXT NOT NULL,
                    distance_meters REAL NOT NULL,
                    is_wheelchair_accessible INTEGER NOT NULL DEFAULT 1,
                    is_staircase INTEGER NOT NULL DEFAULT 0,
                    is_evacuation_path INTEGER NOT NULL DEFAULT 1,
                    is_blocked INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS emergency_markers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    floor_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    marker_type TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    node_key TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'available',
                    is_verified INTEGER NOT NULL DEFAULT 1,
                    approved_by TEXT DEFAULT '',
                    description TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS emergency_contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_primary INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS emergency_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'warning',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    affected_floor_id INTEGER,
                    reported_by TEXT DEFAULT 'Campus Safety',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS faculty (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    designation TEXT NOT NULL,
                    department TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT DEFAULT '',
                    office_room_id INTEGER,
                    availability TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'academic',
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS wifi_networks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    floor_id INTEGER NOT NULL,
                    room_id INTEGER,
                    ssid TEXT NOT NULL,
                    band TEXT NOT NULL,
                    zone_name TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    coverage_radius INTEGER NOT NULL DEFAULT 110,
                    signal_strength_dbm INTEGER NOT NULL DEFAULT -55,
                    speed_mbps INTEGER NOT NULL DEFAULT 250,
                    status TEXT NOT NULL DEFAULT 'online',
                    auth_type TEXT NOT NULL DEFAULT 'Campus SSO',
                    connected_devices INTEGER NOT NULL DEFAULT 18
                );

                CREATE TABLE IF NOT EXISTS feedback_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    floor_id INTEGER,
                    room_id INTEGER,
                    reporter_name TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS navigation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    college_id INTEGER NOT NULL,
                    from_room_name TEXT NOT NULL,
                    to_room_name TEXT NOT NULL,
                    route_mode TEXT NOT NULL,
                    distance_meters REAL NOT NULL,
                    is_emergency INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'campus_admin',
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def ensure_seeded(self) -> None:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM colleges").fetchone()[0]
            if count > 0:
                return
            if not self.seed_path.exists():
                raise FileNotFoundError(f"Seed file missing: {self.seed_path}")

            data = json.loads(self.seed_path.read_text(encoding="utf-8"))
            c = data["activeCollege"]
            conn.execute(
                """
                INSERT INTO colleges (
                    id, name, short_code, logo_url, address, latitude, longitude,
                    contact_email, contact_phone, website, departments_json,
                    total_buildings, total_floors, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c["id"],
                    c["name"],
                    c["shortCode"],
                    c["logoUrl"],
                    c["address"],
                    c["latitude"],
                    c["longitude"],
                    c["contactEmail"],
                    c["contactPhone"],
                    c.get("website", ""),
                    json.dumps(c.get("departments", [])),
                    c.get("totalBuildings", 2),
                    c.get("totalFloors", 3),
                    1 if c.get("isDefault") else 0,
                ),
            )

            for b in data.get("buildings", []):
                conn.execute(
                    """
                    INSERT INTO buildings (id, college_id, name, code, description, latitude, longitude, floors_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        b["id"],
                        b["collegeId"],
                        b["name"],
                        b["code"],
                        b.get("description", ""),
                        b["latitude"],
                        b["longitude"],
                        b.get("floorsCount", 1),
                    ),
                )

            for fl in data.get("floors", []):
                conn.execute(
                    """
                    INSERT INTO floors (id, college_id, building_id, floor_number, name, map_image_url, map_width, map_height, scale_meters_per_unit, is_default)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fl["id"],
                        fl["collegeId"],
                        fl["buildingId"],
                        fl["floorNumber"],
                        fl["name"],
                        fl["mapImageUrl"],
                        fl["mapWidth"],
                        fl["mapHeight"],
                        fl.get("scaleMetersPerUnit", 0.08),
                        1 if fl.get("isDefault") else 0,
                    ),
                )

            for r in data.get("rooms", []):
                conn.execute(
                    """
                    INSERT INTO rooms (
                        id, college_id, building_id, floor_id, room_number, name, department, category,
                        x, y, door_node_key, description, accessibility_info, is_wheelchair_accessible,
                        availability_status, current_subject, faculty_in_charge, timetable_summary, qr_code_value
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["id"],
                        r["collegeId"],
                        r["buildingId"],
                        r["floorId"],
                        r["roomNumber"],
                        r["name"],
                        r["department"],
                        r["category"],
                        r["x"],
                        r["y"],
                        r["doorNodeKey"],
                        r.get("description", ""),
                        r.get("accessibilityInfo", ""),
                        1 if r.get("isWheelchairAccessible", True) else 0,
                        r.get("availabilityStatus", "available"),
                        r.get("currentSubject", ""),
                        r.get("facultyInCharge", ""),
                        r.get("timetableSummary", ""),
                        r.get("qrCodeValue", ""),
                    ),
                )

            for n in data.get("navNodes", []):
                conn.execute(
                    """
                    INSERT INTO nav_nodes (
                        id, floor_id, node_key, label, node_type, x, y,
                        is_accessible, is_blocked, connects_to_floor_id, connects_to_node_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        n["id"],
                        n["floorId"],
                        n["nodeKey"],
                        n["label"],
                        n["nodeType"],
                        n["x"],
                        n["y"],
                        1 if n.get("isAccessible", True) else 0,
                        1 if n.get("isBlocked", False) else 0,
                        n.get("connectsToFloorId"),
                        n.get("connectsToNodeKey"),
                    ),
                )

            for e in data.get("navEdges", []):
                conn.execute(
                    """
                    INSERT INTO nav_edges (
                        id, floor_id, from_node_key, to_node_key, distance_meters,
                        is_wheelchair_accessible, is_staircase, is_evacuation_path, is_blocked
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        e["id"],
                        e["floorId"],
                        e["fromNodeKey"],
                        e["toNodeKey"],
                        e["distanceMeters"],
                        1 if e.get("isWheelchairAccessible", True) else 0,
                        1 if e.get("isStaircase", False) else 0,
                        1 if e.get("isEvacuationPath", True) else 0,
                        1 if e.get("isBlocked", False) else 0,
                    ),
                )

            for m in data.get("emergencyMarkers", []):
                conn.execute(
                    """
                    INSERT INTO emergency_markers (
                        id, college_id, floor_id, name, marker_type, x, y, node_key,
                        status, is_verified, approved_by, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m["id"],
                        m["collegeId"],
                        m["floorId"],
                        m["name"],
                        m["markerType"],
                        m["x"],
                        m["y"],
                        m.get("nodeKey", ""),
                        m.get("status", "available"),
                        1 if m.get("isVerified", True) else 0,
                        m.get("approvedBy", "Campus Safety"),
                        m.get("description", ""),
                    ),
                )

            for ec in data.get("emergencyContacts", []):
                conn.execute(
                    """
                    INSERT INTO emergency_contacts (id, college_id, title, phone, category, is_primary)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ec["id"],
                        ec["collegeId"],
                        ec["title"],
                        ec["phone"],
                        ec["category"],
                        1 if ec.get("isPrimary") else 0,
                    ),
                )

            for al in data.get("activeAlerts", []):
                conn.execute(
                    """
                    INSERT INTO emergency_alerts (id, college_id, title, message, severity, is_active, affected_floor_id, reported_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        al["id"],
                        al["collegeId"],
                        al["title"],
                        al["message"],
                        al.get("severity", "drill"),
                        1 if al.get("isActive", True) else 0,
                        al.get("affectedFloorId"),
                        al.get("reportedBy", "Campus Safety"),
                    ),
                )

            for f_row in data.get("faculty", []):
                conn.execute(
                    """
                    INSERT INTO faculty (id, college_id, name, designation, department, email, phone, office_room_id, availability)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f_row["id"],
                        f_row["collegeId"],
                        f_row["name"],
                        f_row["designation"],
                        f_row["department"],
                        f_row["email"],
                        f_row.get("phone", ""),
                        f_row.get("officeRoomId"),
                        f_row.get("availability", ""),
                    ),
                )

            for a in data.get("announcements", []):
                conn.execute(
                    """
                    INSERT INTO announcements (id, college_id, title, body, category)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (a["id"], a["collegeId"], a["title"], a["body"], a.get("category", "academic")),
                )

            for w in data.get("wifiNetworks", []):
                conn.execute(
                    """
                    INSERT INTO wifi_networks (
                        id, college_id, floor_id, room_id, ssid, band, zone_name, x, y,
                        coverage_radius, signal_strength_dbm, speed_mbps, status, auth_type, connected_devices
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        w["id"],
                        w["collegeId"],
                        w["floorId"],
                        w.get("roomId"),
                        w["ssid"],
                        w["band"],
                        w["zoneName"],
                        w["x"],
                        w["y"],
                        w.get("coverageRadius", 110),
                        w.get("signalStrengthDbm", -52),
                        w.get("speedMbps", 250),
                        w.get("status", "online"),
                        w.get("authType", "Campus SSO"),
                        w.get("connectedDevices", 18),
                    ),
                )

            # Seed default admin account for local portal management
            conn.execute(
                """
                INSERT INTO users (email, name, role, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "admin@californiauniversity.edu",
                    "Campus Administrator",
                    "campus_admin",
                    _hash_password("Admin@1234"),
                ),
            )

    def load_bootstrap(self) -> dict[str, Any]:
        with self._connect() as conn:
            college_row = conn.execute("SELECT * FROM colleges ORDER BY is_default DESC, id ASC LIMIT 1").fetchone()
            college = dict(college_row) if college_row else {}
            if college:
                college["departments"] = json.loads(college.get("departments_json") or "[]")

            cid = college.get("id", 1)
            buildings = [dict(r) for r in conn.execute("SELECT * FROM buildings WHERE college_id = ? ORDER BY id", (cid,))]
            floors = [dict(r) for r in conn.execute("SELECT * FROM floors WHERE college_id = ? ORDER BY floor_number", (cid,))]

            rooms = [
                Room(
                    id=r["id"],
                    college_id=r["college_id"],
                    building_id=r["building_id"],
                    floor_id=r["floor_id"],
                    room_number=r["room_number"],
                    name=r["name"],
                    department=r["department"],
                    category=r["category"],
                    x=r["x"],
                    y=r["y"],
                    door_node_key=r["door_node_key"],
                    description=r["description"] or "",
                    accessibility_info=r["accessibility_info"] or "",
                    is_wheelchair_accessible=bool(r["is_wheelchair_accessible"]),
                    availability_status=r["availability_status"],
                    current_subject=r["current_subject"] or "",
                    faculty_in_charge=r["faculty_in_charge"] or "",
                    timetable_summary=r["timetable_summary"] or "",
                    qr_code_value=r["qr_code_value"],
                )
                for r in conn.execute("SELECT * FROM rooms WHERE college_id = ? ORDER BY id", (cid,))
            ]

            floor_ids = [f["id"] for f in floors]
            placeholders = ",".join("?" for _ in floor_ids) or "0"
            nodes = [
                NavNode(
                    id=n["id"],
                    floor_id=n["floor_id"],
                    node_key=n["node_key"],
                    label=n["label"],
                    node_type=n["node_type"],
                    x=n["x"],
                    y=n["y"],
                    is_accessible=bool(n["is_accessible"]),
                    is_blocked=bool(n["is_blocked"]),
                    connects_to_floor_id=n["connects_to_floor_id"],
                    connects_to_node_key=n["connects_to_node_key"],
                )
                for n in conn.execute(f"SELECT * FROM nav_nodes WHERE floor_id IN ({placeholders})", floor_ids)
            ]
            edges = [
                NavEdge(
                    id=e["id"],
                    floor_id=e["floor_id"],
                    from_node_key=e["from_node_key"],
                    to_node_key=e["to_node_key"],
                    distance_meters=e["distance_meters"],
                    is_wheelchair_accessible=bool(e["is_wheelchair_accessible"]),
                    is_staircase=bool(e["is_staircase"]),
                    is_evacuation_path=bool(e["is_evacuation_path"]),
                    is_blocked=bool(e["is_blocked"]),
                )
                for e in conn.execute(f"SELECT * FROM nav_edges WHERE floor_id IN ({placeholders})", floor_ids)
            ]

            markers = [
                EmergencyMarker(
                    id=m["id"],
                    college_id=m["college_id"],
                    floor_id=m["floor_id"],
                    name=m["name"],
                    marker_type=m["marker_type"],
                    x=m["x"],
                    y=m["y"],
                    node_key=m["node_key"] or "",
                    status=m["status"],
                    is_verified=bool(m["is_verified"]),
                    approved_by=m["approved_by"] or "",
                    description=m["description"] or "",
                )
                for m in conn.execute("SELECT * FROM emergency_markers WHERE college_id = ? ORDER BY id", (cid,))
            ]

            contacts = [dict(r) for r in conn.execute("SELECT * FROM emergency_contacts WHERE college_id = ? ORDER BY is_primary DESC, id ASC", (cid,))]
            alerts = [dict(r) for r in conn.execute("SELECT * FROM emergency_alerts WHERE college_id = ? AND is_active = 1 ORDER BY id DESC", (cid,))]
            faculty = [dict(r) for r in conn.execute("SELECT * FROM faculty WHERE college_id = ? ORDER BY id", (cid,))]
            announcements = [dict(r) for r in conn.execute("SELECT * FROM announcements WHERE college_id = ? ORDER BY id DESC", (cid,))]
            wifi = [dict(r) for r in conn.execute("SELECT * FROM wifi_networks WHERE college_id = ? ORDER BY id", (cid,))]
            feedback = [dict(r) for r in conn.execute("SELECT * FROM feedback_reports WHERE college_id = ? ORDER BY id DESC", (cid,))]
            logs = [dict(r) for r in conn.execute("SELECT * FROM navigation_logs WHERE college_id = ? ORDER BY id DESC LIMIT 100", (cid,))]

        return {
            "activeCollege": college,
            "buildings": buildings,
            "floors": floors,
            "rooms": rooms,
            "navNodes": nodes,
            "navEdges": edges,
            "emergencyMarkers": markers,
            "emergencyContacts": contacts,
            "activeAlerts": alerts,
            "faculty": faculty,
            "announcements": announcements,
            "wifiNetworks": wifi,
            "feedbackReports": feedback,
            "recentLogs": logs,
        }

    def log_navigation(
        self, college_id: int, from_name: str, to_name: str, route_mode: str, distance: float, is_emergency: bool
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO navigation_logs (college_id, from_room_name, to_room_name, route_mode, distance_meters, is_emergency)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (college_id, from_name, to_name, route_mode, distance, 1 if is_emergency else 0),
            )

    def submit_feedback(
        self, college_id: int, floor_id: Optional[int], room_id: Optional[int], reporter_name: str, report_type: str, message: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback_reports (college_id, floor_id, room_id, reporter_name, report_type, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (college_id, floor_id, room_id, reporter_name, report_type, message),
            )

    def resolve_feedback(self, report_id: int, status: str = "resolved") -> None:
        with self._connect() as conn:
            conn.execute("UPDATE feedback_reports SET status = ? WHERE id = ?", (status, report_id))

    def create_alert(self, college_id: int, title: str, message: str, severity: str, reported_by: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO emergency_alerts (college_id, title, message, severity, is_active, reported_by)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (college_id, title, message, severity, reported_by),
            )

    def clear_alert(self, alert_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE emergency_alerts SET is_active = 0 WHERE id = ?", (alert_id,))

    def toggle_edge_blocked(self, edge_id: int, is_blocked: bool) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE nav_edges SET is_blocked = ? WHERE id = ?", (1 if is_blocked else 0, edge_id))

    def set_marker_status(self, marker_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE emergency_markers SET status = ? WHERE id = ?", (status, marker_id))

    def set_wifi_status(self, wifi_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE wifi_networks SET status = ? WHERE id = ?", (status, wifi_id))

    def create_room(
        self,
        college_id: int,
        building_id: int,
        floor_id: int,
        room_number: str,
        name: str,
        department: str,
        category: str,
        door_node_key: str,
        x: float,
        y: float,
        description: str,
    ) -> None:
        qr_val = f"CU:MAB:F{floor_id}:{room_number}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rooms (
                    college_id, building_id, floor_id, room_number, name, department,
                    category, x, y, door_node_key, description, qr_code_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (college_id, building_id, floor_id, room_number, name, department, category, x, y, door_node_key, description, qr_val),
            )

    def delete_room(self, room_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))

    def authenticate_user(self, email: str, password: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email.strip().lower(),)).fetchone()
            if not row:
                return None
            if not _verify_password(password, row["password_hash"]):
                return None
            return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]}

    def register_user(self, email: str, password: str, name: str, role: str = "campus_admin") -> tuple[bool, str]:
        clean = email.strip().lower()
        if not clean or len(password) < 6:
            return False, "Valid email and 6+ character password required."
        with self._connect() as conn:
            exists = conn.execute("SELECT id FROM users WHERE LOWER(email) = ?", (clean,)).fetchone()
            if exists:
                return False, "An administrator account with this email already exists."
            conn.execute(
                "INSERT INTO users (email, name, role, password_hash) VALUES (?, ?, ?, ?)",
                (clean, name.strip() or "Campus Admin", role, _hash_password(password)),
            )
            return True, "Account created and signed in."
