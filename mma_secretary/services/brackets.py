"""Жеребьёвка, сетки и результаты боёв."""

from __future__ import annotations

import json

from mma_secretary.core.bracket import apply_winner, build_bracket, clear_result, propagate
from mma_secretary.core.draw import assign_control_numbers, redraw_control_numbers
from mma_secretary.core.grouping import classify_all
from mma_secretary.core.labels import bracket_kind_ru, round_ru
from mma_secretary.core.models import Bracket
from mma_secretary.core.placements import apply_points, placements_from_bracket
from mma_secretary.services.common import _now, _row
from mma_secretary.services.participants import participant_from_row


class BracketsMixin:
    conn: object

    def _bracket_flags(self) -> tuple[bool, bool]:
        """Бой за 3–4 и две бронзы берутся из реквизитов, а не из разрозненных констант."""
        t = self.get_tournament()
        two = t.get("two_bronzes")
        return bool(t.get("bronze_bout")), True if two is None else bool(two)

    def classify(self) -> dict:
        snapshot = self._snapshot_brackets()
        groups = self.list_age_groups()
        divs = self.list_divisions()
        weights = self.list_weights()
        parts = self._participants_models()
        buckets, unplaced = classify_all(parts, groups, divs, weights)
        tid = self.tid()
        self.conn.execute("DELETE FROM placement WHERE category_id IN (SELECT id FROM category WHERE tournament_id=?)", (tid,))
        self.conn.execute("DELETE FROM bout WHERE tournament_id=?", (tid,))
        self.conn.execute("DELETE FROM category_entry WHERE category_id IN (SELECT id FROM category WHERE tournament_id=?)", (tid,))
        self.conn.execute("DELETE FROM category WHERE tournament_id=?", (tid,))
        created = []
        bronze, _ = self._bracket_flags()
        for u in unplaced:
            if "выше самой тяжёлой" in u.reason:
                self.conn.execute("UPDATE participant SET status='снят' WHERE id=?", (u.participant_id,))
        for key, plist in buckets.items():
            cur = self.conn.execute(
                """INSERT INTO category (tournament_id, age_group_id, division_id, weight_class_id, gender, drawn_at)
                   VALUES (?,?,?,?,?,?)""",
                (tid, key.age_group_id, key.division_id, key.weight_class_id, key.gender, _now()),
            )
            cid = cur.lastrowid
            assigned = assign_control_numbers(plist)
            for pid, ctrl in assigned:
                self.conn.execute(
                    "INSERT INTO category_entry (category_id, participant_id, control_number) VALUES (?,?,?)",
                    (cid, pid, ctrl),
                )
            bracket = build_bracket(len(assigned), bronze_bout=bronze)
            self._write_bracket(cid, bracket)
            created.append(self._category_dict(cid))
        self._renumber_bouts()
        self._audit("classify", {"before": snapshot})
        self.conn.commit()
        return {
            "categories": created,
            "unplaced": [
                {
                    "participant_id": u.participant_id,
                    "reason": u.reason,
                    "participant": _row(
                        self.conn.execute("SELECT * FROM participant WHERE id=?", (u.participant_id,)).fetchone()
                    ),
                }
                for u in unplaced
            ],
        }

    def list_categories(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT c.*, ag.label AS age_label, d.code AS division_code,
                      w.label AS weight_label, w.limit_kg,
                      (SELECT COUNT(*) FROM category_entry e WHERE e.category_id=c.id) AS n
               FROM category c
               JOIN age_group ag ON ag.id=c.age_group_id
               JOIN division d ON d.id=c.division_id
               JOIN weight_class w ON w.id=c.weight_class_id
               WHERE c.tournament_id=?
               ORDER BY ag.sort_order, c.gender, d.sort_order, w.limit_kg""",
            (self.tid(),),
        ).fetchall()
        return [self._decorate_category(dict(r)) for r in rows]

    def _decorate_category(self, row: dict) -> dict:
        row["bracket_title"] = bracket_kind_ru(row.get("bracket_kind"))
        row["gender_label"] = "женщины" if row.get("gender") == "жен" else "мужчины"
        return row

    def _category_dict(self, cid: int) -> dict:
        return self._decorate_category(dict(
            self.conn.execute(
                """SELECT c.*, ag.label AS age_label, d.code AS division_code,
                          w.label AS weight_label, w.limit_kg,
                          (SELECT COUNT(*) FROM category_entry e WHERE e.category_id=c.id) AS n
                   FROM category c
                   JOIN age_group ag ON ag.id=c.age_group_id
                   JOIN division d ON d.id=c.division_id
                   JOIN weight_class w ON w.id=c.weight_class_id
                   WHERE c.id=?""",
                (cid,),
            ).fetchone()
        ))

    def category_detail(self, cid: int) -> dict:
        cat = self._category_dict(cid)
        entries = [
            dict(r)
            for r in self.conn.execute(
                """SELECT e.*, p.name, p.organization, p.rank, p.birth_year, p.coach, p.weight, p.draw_number
                   FROM category_entry e JOIN participant p ON p.id=e.participant_id
                   WHERE e.category_id=? ORDER BY e.control_number""",
                (cid,),
            ).fetchall()
        ]
        bouts = [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM bout WHERE category_id=? ORDER BY scheduled_order, bout_no, id",
                (cid,),
            ).fetchall()
        ]
        self._hydrate_bouts(bouts)
        places = [
            dict(r)
            for r in self.conn.execute(
                """SELECT pl.*, p.name, p.organization, p.rank, p.birth_year, p.coach
                   FROM placement pl JOIN participant p ON p.id=pl.participant_id
                   WHERE pl.category_id=? ORDER BY pl.place, p.name""",
                (cid,),
            ).fetchall()
        ]
        return {
            "category": cat,
            "entries": entries,
            "bouts": bouts,
            "placements": places,
            "pool": self._bracket_pool(cid),
        }

    def redraw(self, cid: int, seed: int | None = None) -> dict:
        snapshot = self.category_detail(cid)
        people = [
            participant_from_row(r)
            for r in self.conn.execute(
                """SELECT p.* FROM category_entry e
                   JOIN participant p ON p.id=e.participant_id
                   WHERE e.category_id=? ORDER BY e.control_number""",
                (cid,),
            ).fetchall()
        ]
        assigned, used_seed = redraw_control_numbers(people, seed=seed)
        assigned.sort(key=lambda x: x[1])
        self.conn.execute("DELETE FROM placement WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM bout WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM category_entry WHERE category_id=?", (cid,))
        for pid, ctrl in assigned:
            self.conn.execute(
                "INSERT INTO category_entry (category_id, participant_id, control_number) VALUES (?,?,?)",
                (cid, pid, ctrl),
            )
        bronze, _ = self._bracket_flags()
        bracket = build_bracket(len(assigned), bronze_bout=bronze)
        self._write_bracket(cid, bracket)
        self.conn.execute("UPDATE category SET drawn_at=? WHERE id=?", (_now(), cid))
        self.conn.execute(
            "INSERT INTO draw_log (category_id, method, seed, created_at, payload) VALUES (?,?,?,?,?)",
            (cid, "redraw", used_seed, _now(), json.dumps({"pairs": assigned})),
        )
        self._renumber_bouts()
        self._audit("redraw", {"category_id": cid, "before": snapshot, "seed": used_seed})
        self.conn.commit()
        return self.category_detail(cid)

    def _bracket_pool(self, cid: int) -> list[dict]:
        """Кого можно добавить в эту сетку: все, кто сейчас не в ней."""
        rows = self.conn.execute(
            """SELECT p.id, p.name, p.organization, p.rank, p.gender, p.status,
                      p.weight, p.declared_weight, p.birth_year,
                      c.id AS other_category_id,
                      ag.label AS age_label, d.code AS division_code, w.label AS weight_label
               FROM participant p
               LEFT JOIN category_entry e ON e.participant_id=p.id
               LEFT JOIN category c ON c.id=e.category_id AND c.tournament_id=p.tournament_id
               LEFT JOIN age_group ag ON ag.id=c.age_group_id
               LEFT JOIN division d ON d.id=c.division_id
               LEFT JOIN weight_class w ON w.id=c.weight_class_id
               WHERE p.tournament_id=? AND (e.category_id IS NULL OR e.category_id!=?)
               ORDER BY p.name COLLATE NOCASE""",
            (self.tid(), cid),
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            if item.get("other_category_id"):
                item["where"] = " · ".join(
                    x for x in (item.get("age_label"), item.get("division_code"),
                                f"до {item['weight_label']} кг" if item.get("weight_label") else "")
                    if x
                )
            else:
                item["where"] = "не в сетке"
            out.append(item)
        return out

    def _replace_members(self, cid: int, participant_ids: list[int]) -> None:
        self.conn.execute("DELETE FROM placement WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM bout WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM category_entry WHERE category_id=?", (cid,))
        for i, pid in enumerate(participant_ids, start=1):
            self.conn.execute(
                "INSERT INTO category_entry (category_id, participant_id, control_number) VALUES (?,?,?)",
                (cid, pid, i),
            )
        bronze, _ = self._bracket_flags()
        bracket = build_bracket(len(participant_ids), bronze_bout=bronze)
        self._write_bracket(cid, bracket)
        self.conn.execute("UPDATE category SET drawn_at=? WHERE id=?", (_now(), cid))

    def manual_order(self, cid: int, participant_ids: list[int]) -> dict:
        """Состав сетки в заданном порядке. Можно добавить людей из других категорий и из списка без сетки."""
        if len(participant_ids) > 64:
            raise ValueError("В категории больше 64 участников: сетка не строится")
        if len(set(participant_ids)) != len(participant_ids):
            raise ValueError("Один и тот же человек указан дважды")
        known = {
            r["id"]
            for r in self.conn.execute(
                "SELECT id FROM participant WHERE tournament_id=?", (self.tid(),)
            )
        }
        missing = [pid for pid in participant_ids if pid not in known]
        if missing:
            raise ValueError("В списке есть человек не из этого турнира")
        snapshot = self._snapshot_brackets()
        affected: set[int] = set()
        for pid in participant_ids:
            row = self.conn.execute(
                """SELECT e.category_id FROM category_entry e
                   JOIN category c ON c.id=e.category_id
                   WHERE e.participant_id=? AND c.tournament_id=?""",
                (pid, self.tid()),
            ).fetchone()
            if row and row["category_id"] != cid:
                affected.add(row["category_id"])
        if participant_ids:
            marks = ",".join("?" * len(participant_ids))
            self.conn.execute(
                f"""DELETE FROM category_entry WHERE participant_id IN ({marks})
                    AND category_id IN (SELECT id FROM category WHERE tournament_id=?)""",
                (*participant_ids, self.tid()),
            )
        for other in affected:
            left = [
                r["participant_id"]
                for r in self.conn.execute(
                    "SELECT participant_id FROM category_entry WHERE category_id=? ORDER BY control_number",
                    (other,),
                )
            ]
            self._replace_members(other, left)
        self._replace_members(cid, participant_ids)
        self.conn.execute(
            "INSERT INTO draw_log (category_id, method, seed, created_at, payload) VALUES (?,?,?,?,?)",
            (cid, "manual", None, _now(), json.dumps({"ids": participant_ids})),
        )
        self._renumber_bouts()
        self._audit("manual_order", {"category_id": cid, "before": snapshot})
        self.conn.commit()
        return self.category_detail(cid)

    def _write_bracket(self, cid: int, bracket: Bracket) -> None:
        tid = self.tid()
        ctrl_to_entry = {
            r["control_number"]: r["id"]
            for r in self.conn.execute("SELECT id, control_number FROM category_entry WHERE category_id=?", (cid,))
        }
        self.conn.execute("UPDATE category SET bracket_kind=? WHERE id=?", (bracket.kind, cid))
        for m in bracket.matches:
            self.conn.execute(
                """INSERT INTO bout
                   (tournament_id, category_id, match_key, round_code, slot, blue_entry_id, red_entry_id,
                    winner_entry_id, is_bye, source_blue, source_red)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tid,
                    cid,
                    m.key,
                    m.round_code,
                    m.slot,
                    ctrl_to_entry.get(m.blue_ctrl) if m.blue_ctrl else None,
                    ctrl_to_entry.get(m.red_ctrl) if m.red_ctrl else None,
                    ctrl_to_entry.get(m.winner_ctrl) if m.winner_ctrl else None,
                    1 if m.is_bye else 0,
                    m.source_blue,
                    m.source_red,
                ),
            )
        if any(m.winner_ctrl for m in bracket.matches):
            self._recalc_category_places(cid)

    def _bracket_from_db(self, cid: int) -> tuple[Bracket, dict[int, int], dict[int, int]]:
        n = self.conn.execute("SELECT COUNT(*) FROM category_entry WHERE category_id=?", (cid,)).fetchone()[0]
        rows = self.conn.execute("SELECT * FROM bout WHERE category_id=?", (cid,)).fetchall()
        bronze = any(r["match_key"] == "BRONZE" for r in rows)
        bracket = build_bracket(n, bronze_bout=bronze)
        entry_to_ctrl = {
            r["id"]: r["control_number"]
            for r in self.conn.execute("SELECT id, control_number FROM category_entry WHERE category_id=?", (cid,))
        }
        ctrl_to_entry = {v: k for k, v in entry_to_ctrl.items()}
        by_key = {m.key: m for m in bracket.matches}
        for r in rows:
            m = by_key.get(r["match_key"])
            if not m:
                continue
            if r["winner_entry_id"] and not m.is_bye:
                m.winner_ctrl = entry_to_ctrl.get(r["winner_entry_id"])
        propagate(bracket)
        return bracket, entry_to_ctrl, ctrl_to_entry

    def set_result(self, bout_id: int, winner_entry_id: int) -> dict:
        bout = self.conn.execute("SELECT * FROM bout WHERE id=?", (bout_id,)).fetchone()
        if not bout:
            raise KeyError("Бой не найден")
        if bout["is_bye"]:
            raise ValueError("Это проход, не бой")
        if not bout["blue_entry_id"] or not bout["red_entry_id"]:
            raise ValueError("Нельзя внести результат, пока не определены оба участника")
        if winner_entry_id not in (bout["blue_entry_id"], bout["red_entry_id"]):
            raise ValueError("Победитель должен быть синим или красным углом")
        snapshot = self.category_detail(bout["category_id"])
        cid = bout["category_id"]
        bracket, entry_to_ctrl, ctrl_to_entry = self._bracket_from_db(cid)
        apply_winner(bracket, bout["match_key"], entry_to_ctrl[winner_entry_id])
        self._sync_winners(cid, bracket, ctrl_to_entry)
        self.conn.execute("UPDATE bout SET method=NULL WHERE id=?", (bout_id,))
        self._recalc_category_places(cid)
        self._audit("set_result", {"bout_id": bout_id, "before": snapshot})
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM bout WHERE id=?", (bout_id,)).fetchone())

    def clear_bout(self, bout_id: int) -> dict:
        bout = self.conn.execute("SELECT * FROM bout WHERE id=?", (bout_id,)).fetchone()
        if not bout:
            raise KeyError("Бой не найден")
        snapshot = self.category_detail(bout["category_id"])
        cid = bout["category_id"]
        bracket, _, ctrl_to_entry = self._bracket_from_db(cid)
        clear_result(bracket, bout["match_key"])
        self._sync_winners(cid, bracket, ctrl_to_entry)
        self.conn.execute("UPDATE bout SET method=NULL WHERE id=?", (bout_id,))
        self._recalc_category_places(cid)
        self._audit("clear_bout", {"bout_id": bout_id, "before": snapshot})
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM bout WHERE id=?", (bout_id,)).fetchone())

    def _sync_winners(self, cid: int, bracket: Bracket, ctrl_to_entry: dict[int, int]) -> None:
        for m in bracket.matches:
            self.conn.execute(
                """UPDATE bout SET blue_entry_id=?, red_entry_id=?, winner_entry_id=?
                   WHERE category_id=? AND match_key=?""",
                (
                    ctrl_to_entry.get(m.blue_ctrl) if m.blue_ctrl else None,
                    ctrl_to_entry.get(m.red_ctrl) if m.red_ctrl else None,
                    ctrl_to_entry.get(m.winner_ctrl) if m.winner_ctrl else None,
                    cid,
                    m.key,
                ),
            )

    def schedule_bout(self, bout_id: int, ring: int | None, order: int | None) -> dict:
        self.conn.execute("UPDATE bout SET ring=?, scheduled_order=? WHERE id=?", (ring, order, bout_id))
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM bout WHERE id=?", (bout_id,)).fetchone())

    def list_bouts(self, fights_only: bool = True) -> list[dict]:
        q = """SELECT b.*, w.label AS weight_label, ag.label AS age_label, d.code AS division_code
               FROM bout b
               JOIN category c ON c.id=b.category_id
               JOIN weight_class w ON w.id=c.weight_class_id
               JOIN age_group ag ON ag.id=c.age_group_id
               JOIN division d ON d.id=c.division_id
               WHERE b.tournament_id=?"""
        if fights_only:
            q += " AND b.is_bye=0"
        q += " ORDER BY COALESCE(b.scheduled_order, 9999), COALESCE(b.bout_no, 9999), b.id"
        rows = [dict(r) for r in self.conn.execute(q, (self.tid(),)).fetchall()]
        self._hydrate_bouts(rows)
        return rows

    def _hydrate_bouts(self, rows: list[dict]) -> None:
        def fighter(eid):
            if not eid:
                return None
            r = self.conn.execute(
                """SELECT e.id, e.control_number, p.name, p.organization, p.id AS participant_id
                   FROM category_entry e JOIN participant p ON p.id=e.participant_id WHERE e.id=?""",
                (eid,),
            ).fetchone()
            return dict(r) if r else None

        for r in rows:
            r["blue"] = fighter(r.get("blue_entry_id"))
            r["red"] = fighter(r.get("red_entry_id"))
            r["winner"] = fighter(r.get("winner_entry_id"))
            r["round_title"] = round_ru(r.get("round_code"))

    def _renumber_bouts(self) -> None:
        rows = self.conn.execute(
            """SELECT b.id FROM bout b
               JOIN category c ON c.id=b.category_id
               JOIN age_group ag ON ag.id=c.age_group_id
               JOIN division d ON d.id=c.division_id
               JOIN weight_class w ON w.id=c.weight_class_id
               WHERE b.tournament_id=? AND b.is_bye=0
               ORDER BY ag.sort_order, d.sort_order, w.limit_kg,
                        CASE b.round_code
                          WHEN '1/32' THEN 1 WHEN '1/16' THEN 2 WHEN '1/8' THEN 3
                          WHEN '1/4' THEN 4 WHEN '1/2' THEN 5
                          WHEN 'за бронзу' THEN 6 WHEN 'финал' THEN 7 ELSE 8 END,
                        b.slot, b.id""",
            (self.tid(),),
        ).fetchall()
        for i, r in enumerate(rows, start=1):
            self.conn.execute("UPDATE bout SET bout_no=?, scheduled_order=? WHERE id=?", (i, i, r["id"]))

    def _recalc_category_places(self, cid: int) -> None:
        bracket, _, _ = self._bracket_from_db(cid)
        _, two_bronzes = self._bracket_flags()
        places = placements_from_bracket(bracket, two_bronzes=two_bronzes)
        rules = self.list_point_rules()
        self.conn.execute("DELETE FROM placement WHERE category_id=?", (cid,))
        ctrl_to_pid = {
            r["control_number"]: r["participant_id"]
            for r in self.conn.execute("SELECT control_number, participant_id FROM category_entry WHERE category_id=?", (cid,))
        }
        for p, pts in apply_points(places, rules):
            pid = ctrl_to_pid.get(p.control_number)
            if pid:
                self.conn.execute(
                    "INSERT INTO placement (category_id, participant_id, place, points, tied) VALUES (?,?,?,?,?)",
                    (cid, pid, p.place, pts, 1 if p.tied else 0),
                )
