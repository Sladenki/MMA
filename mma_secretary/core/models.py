from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class AgeGroup:
    id: int
    label: str
    year_from: int
    year_to: int
    sort_order: int = 0


@dataclass(frozen=True)
class Division:
    id: int
    code: str
    sort_order: int = 0
    rank_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class WeightClass:
    id: int
    limit_kg: float
    label: str
    age_group_id: int | None = None
    sort_order: int = 0


@dataclass
class Participant:
    id: int
    name: str
    organization: str
    rank: str
    birth_year: int | None
    coach: str
    weight: float | None
    status: str = "заявлен"
    draw_number: int | None = None
    gender: str = "муж"
    division_id: int | None = None
    declared_weight: float | None = None


@dataclass(frozen=True)
class CategoryKey:
    age_group_id: int
    division_id: int
    weight_class_id: int
    gender: str = "муж"


@dataclass(frozen=True)
class Unplaced:
    participant_id: int
    reason: str


@dataclass(frozen=True)
class FirstRoundSlot:
    kind: Literal["fight", "bye", "empty"]
    a: int
    b: int | None = None


@dataclass
class MatchSpec:
    key: str
    round_code: str
    slot: int
    blue_ctrl: int | None = None
    red_ctrl: int | None = None
    source_blue: str | None = None
    source_red: str | None = None
    winner_ctrl: int | None = None
    is_bye: bool = False


@dataclass
class Bracket:
    n: int
    size: int
    kind: Literal["empty", "single_elim"]
    first_round: list[FirstRoundSlot] = field(default_factory=list)
    matches: list[MatchSpec] = field(default_factory=list)


@dataclass(frozen=True)
class Placement:
    control_number: int
    place: int
    tied: bool = False


@dataclass(frozen=True)
class PointRule:
    place_from: int
    place_to: int
    points: int


@dataclass
class TeamRow:
    organization: str
    points: int
    place: int
    category_places: dict[str, list[int]] = field(default_factory=dict)


DEFAULT_POINT_RULES: tuple[PointRule, ...] = (
    PointRule(1, 1, 10),
    PointRule(2, 2, 8),
    PointRule(3, 3, 6),
    PointRule(5, 8, 2),
    PointRule(9, 16, 1),
    PointRule(17, 64, 0),
)
