from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

RouteMode = Literal["shortest", "easiest", "stair_free"]
LanguageCode = Literal["en", "kn"]


@dataclass
class NavNode:
    id: int
    floor_id: int
    node_key: str
    label: str
    node_type: str
    x: float
    y: float
    is_accessible: bool = True
    is_blocked: bool = False
    connects_to_floor_id: Optional[int] = None
    connects_to_node_key: Optional[str] = None


@dataclass
class NavEdge:
    id: int
    floor_id: int
    from_node_key: str
    to_node_key: str
    distance_meters: float
    is_wheelchair_accessible: bool = True
    is_staircase: bool = False
    is_evacuation_path: bool = True
    is_blocked: bool = False


@dataclass
class Room:
    id: int
    college_id: int
    building_id: int
    floor_id: int
    room_number: str
    name: str
    department: str
    category: str
    x: float
    y: float
    door_node_key: str
    description: str = ""
    accessibility_info: str = "Step-free corridor access"
    is_wheelchair_accessible: bool = True
    availability_status: str = "available"
    current_subject: str = ""
    faculty_in_charge: str = ""
    timetable_summary: str = ""
    qr_code_value: str = ""


@dataclass
class RouteStep:
    instruction: str
    instruction_kn: str
    distance_meters: float
    node_key: str
    x: float
    y: float
    direction: str  # start, straight, left, right, arrive, exit
    floor_id: Optional[int] = None
    node_type: Optional[str] = None


@dataclass
class ComputedRoute:
    path_nodes: list[NavNode]
    total_distance_meters: float
    estimated_seconds: int
    steps: list[RouteStep]
    accessible: bool
    mode: str
    warnings: list[str] = field(default_factory=list)
    turn_count: int = 0
    strategy_note: str = ""


@dataclass
class CrossFloorRouteResult:
    leg1: ComputedRoute
    leg2: ComputedRoute
    connector_type: Literal["lift", "staircase"]
    connector_label: str
    total_distance_meters: float
    estimated_seconds: int
    turn_count: int
    strategy_note: str
    all_steps: list[RouteStep]


@dataclass
class EmergencyMarker:
    id: int
    college_id: int
    floor_id: int
    name: str
    marker_type: str
    x: float
    y: float
    node_key: str
    status: str
    is_verified: bool
    approved_by: str
    description: str = ""


@dataclass
class EmergencyEvacuationPlan:
    recommended_exit: Optional[EmergencyMarker]
    primary_route: Optional[ComputedRoute]
    alternative_exit: Optional[EmergencyMarker]
    alternative_route: Optional[ComputedRoute]
    nearest_extinguisher: Optional[EmergencyMarker]
    assembly_points: list[EmergencyMarker]
    warnings: list[str]
