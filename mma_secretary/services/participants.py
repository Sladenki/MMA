"""Заявка, взвешивание и история веса."""

from __future__ import annotations

from mma_secretary.core.models import Participant
from mma_secretary.core.normalize import (
    looks_like_duplicate,
    normalize_gender,
    normalize_name,
    normalize_org,
    normalize_rank,
    parse_weight,
)
from mma_secretary.services.common import _now


def participant_from_row(row) -> Participant:
    data = dict(row)
    return Participant(
        id=data["id"],
        name=data["name"],
        organization=data.get("organization") or "",
        rank=data.get("rank") or "",
        birth_year=data.get("birth_year"),
        coach=data.get("coach") or "",
        weight=data.get("weight"),
        status=data.get("status") or "заявлен",
        draw_number=data.get("draw_number"),
        gender=data.get("gender") or "муж",
        division_id=data.get("division_id"),
        declared_weight=data.get("declared_weight"),
    )


class ParticipantsMixin:
    conn: object

    def list_participants(self, sort: str = "seq") -> list[dict]:
        order = {
            "seq": "seq, id",
            "team": "organization COLLATE NOCASE, birth_year, draw_number, name",
            "weight": "weight IS NULL, weight, name",
            "year_weight": "birth_year, weight IS NULL, weight, name",
            "alpha": "name COLLATE NOCASE",
            "draw": "draw_number IS NULL, draw_number, name",
        }.get(sort, "seq, id")
        rows = self.conn.execute(
            f"SELECT * FROM participant WHERE tournament_id=? ORDER BY {order}",
            (self.tid(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def _dup_warning(self, name: str, year: int | None, exclude_id: int | None = None) -> bool:
        others = []
        for r in self.list_participants():
            if exclude_id and r["id"] == exclude_id:
                continue
            others.append((r["name"], r["birth_year"]))
        return looks_like_duplicate(name, year, others)

    def add_participant(self, data: dict) -> dict:
        name = normalize_name(data.get("name"))
        if not name:
            raise ValueError("Нужны фамилия и имя")
        org = normalize_org(data.get("organization"))
        rank = normalize_rank(data.get("rank"))
        year = data.get("birth_year")
        year = int(year) if year not in (None, "") else None
        coach = (data.get("coach") or "").strip()
        weight = parse_weight(data.get("weight"))
        declared = parse_weight(data.get("declared_weight"))
        status = data.get("status") or ("взвешен" if weight is not None else "заявлен")
        draw = data.get("draw_number")
        draw = int(draw) if draw not in (None, "") else None
        gender = normalize_gender(data.get("gender"))
        division_id = data.get("division_id")
        division_id = int(division_id) if division_id not in (None, "") else None
        seq = data.get("seq")
        if seq in (None, ""):
            mx = self.conn.execute(
                "SELECT COALESCE(MAX(seq),0) FROM participant WHERE tournament_id=?",
                (self.tid(),),
            ).fetchone()[0]
            seq = mx + 1
        warning = self._dup_warning(name, year)
        cur = self.conn.execute(
            """INSERT INTO participant
               (tournament_id, seq, name, organization, rank, birth_year, coach, weight, declared_weight, status, draw_number, gender, division_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self.tid(), seq, name, org, rank, year, coach, weight, declared, status, draw, gender, division_id),
        )
        pid = cur.lastrowid
        if weight is not None:
            self.conn.execute(
                "INSERT INTO weight_history (participant_id, weight, recorded_at) VALUES (?,?,?)",
                (pid, weight, _now()),
            )
        self._audit("add_participant", {"id": pid, "name": name})
        self.conn.commit()
        row = dict(self.conn.execute("SELECT * FROM participant WHERE id=?", (pid,)).fetchone())
        row["duplicate_warning"] = warning
        return row

    def update_participant(self, pid: int, data: dict) -> dict:
        prev = self.conn.execute("SELECT * FROM participant WHERE id=?", (pid,)).fetchone()
        if not prev:
            raise KeyError("Участник не найден")
        prev_d = dict(prev)
        name = normalize_name(data.get("name", prev["name"]))
        org = normalize_org(data.get("organization", prev["organization"]))
        rank = normalize_rank(data.get("rank", prev["rank"]))
        year = data.get("birth_year", prev["birth_year"])
        year = int(year) if year not in (None, "") else None
        coach = (data.get("coach", prev["coach"]) or "").strip()
        weight = parse_weight(data.get("weight")) if "weight" in data else prev["weight"]
        if "declared_weight" in data:
            declared = parse_weight(data.get("declared_weight"))
        else:
            declared = prev["declared_weight"] if "declared_weight" in prev.keys() else None
        status = data.get("status", prev["status"])
        draw = data.get("draw_number", prev["draw_number"])
        draw = int(draw) if draw not in (None, "") else None
        gender = normalize_gender(data.get("gender", prev["gender"] if "gender" in prev.keys() else "муж"))
        division_id = data.get("division_id", prev["division_id"] if "division_id" in prev.keys() else None)
        division_id = int(division_id) if division_id not in (None, "") else None
        warning = self._dup_warning(name, year, exclude_id=pid)
        self.conn.execute(
            """UPDATE participant SET name=?, organization=?, rank=?, birth_year=?, coach=?,
               weight=?, declared_weight=?, status=?, draw_number=?, gender=?, division_id=? WHERE id=?""",
            (name, org, rank, year, coach, weight, declared, status, draw, gender, division_id, pid),
        )
        if "weight" in data and weight != prev["weight"] and weight is not None:
            self.conn.execute(
                "INSERT INTO weight_history (participant_id, weight, recorded_at) VALUES (?,?,?)",
                (pid, weight, _now()),
            )
            if status == "заявлен":
                self.conn.execute("UPDATE participant SET status='взвешен' WHERE id=?", (pid,))
        self._audit("update_participant", {"id": pid, "before": prev_d})
        self.conn.commit()
        row = dict(self.conn.execute("SELECT * FROM participant WHERE id=?", (pid,)).fetchone())
        row["duplicate_warning"] = warning
        return row

    def delete_participant(self, pid: int) -> None:
        prev = self.conn.execute("SELECT * FROM participant WHERE id=?", (pid,)).fetchone()
        if not prev:
            return
        self.conn.execute("DELETE FROM participant WHERE id=?", (pid,))
        self._audit("delete_participant", {"before": dict(prev)})
        self.conn.commit()

    def weigh_in(
        self,
        pid: int,
        weight_raw,
        status: str | None = None,
        *,
        declared_weight=None,
        update_declared: bool = False,
    ) -> dict:
        weight = parse_weight(weight_raw)
        if weight is None:
            raise ValueError("Нужен фактический вес")
        prev = dict(self.conn.execute("SELECT * FROM participant WHERE id=?", (pid,)).fetchone())
        st = status or ("допущен" if prev["status"] in {"заявлен", "взвешен", "допущен"} else prev["status"])
        limits = [w.limit_kg for w in self.list_weights()]
        if limits and weight > max(limits) + 1e-9:
            st = "снят"
        declared = prev.get("declared_weight")
        if update_declared:
            declared = parse_weight(declared_weight)
        self.conn.execute(
            "UPDATE participant SET weight=?, declared_weight=?, status=? WHERE id=?",
            (weight, declared, st, pid),
        )
        self.conn.execute(
            "INSERT INTO weight_history (participant_id, weight, recorded_at) VALUES (?,?,?)",
            (pid, weight, _now()),
        )
        self._audit("weigh_in", {"id": pid, "before": prev})
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM participant WHERE id=?", (pid,)).fetchone())

    def weight_history(self, pid: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM weight_history WHERE participant_id=? ORDER BY recorded_at",
            (pid,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _participants_models(self) -> list[Participant]:
        return [participant_from_row(r) for r in self.list_participants()]
