"""Отмена, резервная копия и пустой турнир."""

from __future__ import annotations

import json

from mma_secretary.core.normalize import format_kg
from mma_secretary.services.common import _now


class HistoryMixin:
    conn: object

    def _audit(self, action: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO audit_log (tournament_id, action, payload, created_at, undone) VALUES (?,?,?,?,0)",
            (self.tid(), action, json.dumps(payload, ensure_ascii=False, default=str), _now()),
        )

    def _snapshot_brackets(self) -> dict:
        return {
            "categories": [dict(r) for r in self.conn.execute("SELECT * FROM category WHERE tournament_id=?", (self.tid(),))],
            "entries": [
                dict(r)
                for r in self.conn.execute(
                    "SELECT e.* FROM category_entry e JOIN category c ON c.id=e.category_id WHERE c.tournament_id=?",
                    (self.tid(),),
                )
            ],
            "bouts": [dict(r) for r in self.conn.execute("SELECT * FROM bout WHERE tournament_id=?", (self.tid(),))],
            "placements": [
                dict(r)
                for r in self.conn.execute(
                    "SELECT pl.* FROM placement pl JOIN category c ON c.id=pl.category_id WHERE c.tournament_id=?",
                    (self.tid(),),
                )
            ],
        }

    def undo(self) -> dict:
        row = self.conn.execute(
            "SELECT * FROM audit_log WHERE tournament_id=? AND undone=0 ORDER BY id DESC LIMIT 1",
            (self.tid(),),
        ).fetchone()
        if not row:
            raise ValueError("Нечего отменять")
        payload = json.loads(row["payload"])
        action = row["action"]
        if action == "manual_order" and "before" in payload and "categories" in payload["before"]:
            self._restore_all_brackets(payload["before"])
        elif action in {"set_result", "clear_bout", "redraw", "manual_order"} and "before" in payload:
            self._restore_category(payload["before"])
        elif action == "classify" and "before" in payload:
            self._restore_all_brackets(payload["before"])
        elif action == "update_participant" and "before" in payload:
            b = payload["before"]
            self.conn.execute(
                """UPDATE participant SET name=?, organization=?, rank=?, birth_year=?, coach=?,
                   weight=?, declared_weight=?, status=?, draw_number=?, gender=?, division_id=? WHERE id=?""",
                (
                    b["name"],
                    b["organization"],
                    b["rank"],
                    b["birth_year"],
                    b["coach"],
                    b["weight"],
                    b.get("declared_weight"),
                    b["status"],
                    b["draw_number"],
                    b.get("gender") or "муж",
                    b.get("division_id"),
                    b["id"],
                ),
            )
        elif action == "weigh_in" and "before" in payload:
            b = payload["before"]
            self.conn.execute(
                "UPDATE participant SET weight=?, declared_weight=?, status=? WHERE id=?",
                (b["weight"], b.get("declared_weight"), b["status"], b["id"]),
            )
        elif action == "add_participant":
            self.conn.execute("DELETE FROM participant WHERE id=?", (payload["id"],))
        elif action == "delete_participant" and "before" in payload:
            b = payload["before"]
            self.conn.execute(
                """INSERT INTO participant
                   (id, tournament_id, seq, name, organization, rank, birth_year, coach, weight, declared_weight, status, draw_number, gender, division_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    b["id"],
                    b["tournament_id"],
                    b["seq"],
                    b["name"],
                    b["organization"],
                    b["rank"],
                    b["birth_year"],
                    b["coach"],
                    b["weight"],
                    b.get("declared_weight"),
                    b["status"],
                    b["draw_number"],
                    b.get("gender") or "муж",
                    b.get("division_id"),
                ),
            )
        else:
            raise ValueError(f"Отмена «{action}» не поддерживается")
        self.conn.execute("UPDATE audit_log SET undone=1 WHERE id=?", (row["id"],))
        self.conn.commit()
        return {"undone": action}

    def _restore_category(self, detail: dict) -> None:
        cat = detail["category"]
        cid = cat["id"]
        self.conn.execute("DELETE FROM placement WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM bout WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM category_entry WHERE category_id=?", (cid,))
        for e in detail["entries"]:
            self.conn.execute(
                "INSERT INTO category_entry (id, category_id, participant_id, control_number) VALUES (?,?,?,?)",
                (e["id"], e["category_id"], e["participant_id"], e["control_number"]),
            )
        for b in detail["bouts"]:
            self.conn.execute(
                """INSERT INTO bout
                   (id, tournament_id, category_id, match_key, bout_no, round_code, slot,
                    blue_entry_id, red_entry_id, winner_entry_id, method, ring, scheduled_order,
                    is_bye, source_blue, source_red)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    b["id"], b["tournament_id"], b["category_id"], b["match_key"], b.get("bout_no"),
                    b["round_code"], b["slot"], b.get("blue_entry_id"), b.get("red_entry_id"),
                    b.get("winner_entry_id"), b.get("method"), b.get("ring"), b.get("scheduled_order"),
                    b.get("is_bye") or 0, b.get("source_blue"), b.get("source_red"),
                ),
            )
        for p in detail["placements"]:
            self.conn.execute(
                "INSERT INTO placement (id, category_id, participant_id, place, points, tied) VALUES (?,?,?,?,?,?)",
                (p["id"], p["category_id"], p["participant_id"], p["place"], p["points"], p.get("tied") or 0),
            )

    def _restore_all_brackets(self, snap: dict) -> None:
        tid = self.tid()
        self.conn.execute("DELETE FROM placement WHERE category_id IN (SELECT id FROM category WHERE tournament_id=?)", (tid,))
        self.conn.execute("DELETE FROM bout WHERE tournament_id=?", (tid,))
        self.conn.execute("DELETE FROM category_entry WHERE category_id IN (SELECT id FROM category WHERE tournament_id=?)", (tid,))
        self.conn.execute("DELETE FROM category WHERE tournament_id=?", (tid,))
        for c in snap.get("categories", []):
            cols = [k for k in c.keys() if k != "n"]
            self.conn.execute(
                f"INSERT INTO category ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                [c[k] for k in cols],
            )
        for e in snap.get("entries", []):
            self.conn.execute(
                "INSERT INTO category_entry (id, category_id, participant_id, control_number) VALUES (?,?,?,?)",
                (e["id"], e["category_id"], e["participant_id"], e["control_number"]),
            )
        for b in snap.get("bouts", []):
            keys = [
                "id", "tournament_id", "category_id", "match_key", "bout_no", "round_code", "slot",
                "blue_entry_id", "red_entry_id", "winner_entry_id", "method", "ring", "scheduled_order",
                "is_bye", "source_blue", "source_red",
            ]
            self.conn.execute(
                f"INSERT INTO bout ({','.join(keys)}) VALUES ({','.join('?'*len(keys))})",
                [b.get(k) for k in keys],
            )
        for p in snap.get("placements", []):
            self.conn.execute(
                "INSERT INTO placement (id, category_id, participant_id, place, points, tied) VALUES (?,?,?,?,?,?)",
                (p["id"], p["category_id"], p["participant_id"], p["place"], p["points"], p.get("tied") or 0),
            )

    def export_bundle(self) -> dict:
        tid = self.tid()
        return {
            "tournament": self.get_tournament(),
            "age_groups": [dict(r) for r in self.conn.execute("SELECT * FROM age_group WHERE tournament_id=?", (tid,))],
            "divisions": [dict(r) for r in self.conn.execute("SELECT * FROM division WHERE tournament_id=?", (tid,))],
            "weights": [dict(r) for r in self.conn.execute("SELECT * FROM weight_class WHERE tournament_id=?", (tid,))],
            "point_rules": [dict(r) for r in self.conn.execute("SELECT * FROM point_rule WHERE tournament_id=?", (tid,))],
            "participants": self.list_participants(),
            "weight_history": [
                dict(r)
                for r in self.conn.execute(
                    "SELECT h.* FROM weight_history h JOIN participant p ON p.id=h.participant_id WHERE p.tournament_id=?",
                    (tid,),
                )
            ],
            "brackets": self._snapshot_brackets(),
            "team_rep": [dict(r) for r in self.conn.execute("SELECT * FROM team_rep WHERE tournament_id=?", (tid,))],
            "draw_log": [
                dict(r)
                for r in self.conn.execute(
                    "SELECT d.* FROM draw_log d JOIN category c ON c.id=d.category_id WHERE c.tournament_id=?",
                    (tid,),
                )
            ],
        }

    def import_bundle(self, data: dict) -> None:
        tid = self.tid()
        self.conn.execute("DELETE FROM placement")
        self.conn.execute("DELETE FROM bout")
        self.conn.execute("DELETE FROM category_entry")
        self.conn.execute("DELETE FROM category")
        self.conn.execute("DELETE FROM weight_history")
        self.conn.execute("DELETE FROM participant")
        self.conn.execute("DELETE FROM point_rule")
        self.conn.execute("DELETE FROM weight_class")
        self.conn.execute("DELETE FROM division")
        self.conn.execute("DELETE FROM age_group")
        self.conn.execute("DELETE FROM team_rep")
        t = data.get("tournament") or {}
        self.update_tournament({k: t[k] for k in t if k != "id"})
        id_map_ag, id_map_div, id_map_w, id_map_p, id_map_c, id_map_e = {}, {}, {}, {}, {}, {}
        for r in data.get("age_groups", []):
            cur = self.conn.execute(
                "INSERT INTO age_group (tournament_id, label, year_from, year_to, sort_order) VALUES (?,?,?,?,?)",
                (tid, r["label"], r["year_from"], r["year_to"], r.get("sort_order") or 0),
            )
            id_map_ag[r["id"]] = cur.lastrowid
        for r in data.get("divisions", []):
            cur = self.conn.execute(
                "INSERT INTO division (tournament_id, code, sort_order, rank_values) VALUES (?,?,?,?)",
                (tid, r["code"], r.get("sort_order") or 0, r.get("rank_values") or "[]"),
            )
            id_map_div[r["id"]] = cur.lastrowid
        for r in data.get("weights", []):
            cur = self.conn.execute(
                "INSERT INTO weight_class (tournament_id, age_group_id, limit_kg, label, sort_order) VALUES (?,?,?,?,?)",
                (tid, id_map_ag.get(r.get("age_group_id")), r["limit_kg"], r["label"], r.get("sort_order") or 0),
            )
            id_map_w[r["id"]] = cur.lastrowid
        for r in data.get("point_rules", []):
            self.conn.execute(
                "INSERT INTO point_rule (tournament_id, place_from, place_to, points) VALUES (?,?,?,?)",
                (tid, r["place_from"], r["place_to"], r["points"]),
            )
        for r in data.get("participants", []):
            raw_div = r.get("division_id")
            mapped_div = id_map_div.get(raw_div) if raw_div not in (None, "") else None
            # Старый JSON: одно поле weight = заявленный. Новый: weight факт, declared_weight заявка.
            if "declared_weight" in r:
                actual, declared = r.get("weight"), r.get("declared_weight")
            else:
                actual, declared = None, r.get("weight")
            cur = self.conn.execute(
                """INSERT INTO participant (tournament_id, seq, name, organization, rank, birth_year, coach, weight, declared_weight, status, draw_number, gender, division_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tid,
                    r.get("seq"),
                    r["name"],
                    r.get("organization") or "",
                    r.get("rank") or "",
                    r.get("birth_year"),
                    r.get("coach") or "",
                    actual,
                    declared,
                    r.get("status") or "заявлен",
                    r.get("draw_number"),
                    r.get("gender") or "муж",
                    mapped_div,
                ),
            )
            id_map_p[r["id"]] = cur.lastrowid
        br = data.get("brackets") or {}
        for r in br.get("categories", []):
            cur = self.conn.execute(
                """INSERT INTO category (tournament_id, age_group_id, division_id, weight_class_id, gender, bracket_kind, drawn_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (tid, id_map_ag[r["age_group_id"]], id_map_div[r["division_id"]], id_map_w[r["weight_class_id"]], r.get("gender") or "муж", r.get("bracket_kind"), r.get("drawn_at")),
            )
            id_map_c[r["id"]] = cur.lastrowid
        for r in br.get("entries", []):
            cur = self.conn.execute(
                "INSERT INTO category_entry (category_id, participant_id, control_number) VALUES (?,?,?)",
                (id_map_c[r["category_id"]], id_map_p[r["participant_id"]], r["control_number"]),
            )
            id_map_e[r["id"]] = cur.lastrowid
        for r in br.get("bouts", []):
            self.conn.execute(
                """INSERT INTO bout (tournament_id, category_id, match_key, bout_no, round_code, slot,
                    blue_entry_id, red_entry_id, winner_entry_id, method, ring, scheduled_order, is_bye, source_blue, source_red)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tid, id_map_c[r["category_id"]], r["match_key"], r.get("bout_no"), r["round_code"], r.get("slot") or 0,
                    id_map_e.get(r.get("blue_entry_id")), id_map_e.get(r.get("red_entry_id")),
                    id_map_e.get(r.get("winner_entry_id")), r.get("method"), r.get("ring"), r.get("scheduled_order"),
                    r.get("is_bye") or 0, r.get("source_blue"), r.get("source_red"),
                ),
            )
        for r in br.get("placements", []):
            self.conn.execute(
                "INSERT INTO placement (category_id, participant_id, place, points, tied) VALUES (?,?,?,?,?)",
                (id_map_c[r["category_id"]], id_map_p[r["participant_id"]], r["place"], r["points"], r.get("tied") or 0),
            )
        self.conn.commit()

    def reset_to_empty(self) -> None:
        """Пустой турнир: люди и сетки сбрасываются, справочники весов остаются."""
        self.conn.execute("DELETE FROM placement")
        self.conn.execute("DELETE FROM bout")
        self.conn.execute("DELETE FROM category_entry")
        self.conn.execute("DELETE FROM category")
        self.conn.execute("DELETE FROM weight_history")
        self.conn.execute("DELETE FROM participant")
        self.conn.execute("DELETE FROM team_rep")
        self.conn.execute("DELETE FROM draw_log")
        self.conn.execute("DELETE FROM audit_log")
        self.update_tournament(
            {
                "name": "",
                "kind": "смешанное боевое единоборство (ММА)",
                "date": "",
                "city": "",
                "chief_referee": "",
                "chief_secretary": "",
            }
        )
        self.conn.commit()

    def seed_defaults(self) -> None:
        if self.list_age_groups():
            return
        self.save_age_group({"label": "2007-2008", "year_from": 2007, "year_to": 2008, "sort_order": 0})
        for i, code in enumerate("АБВГД"):
            self.save_division({"code": code, "sort_order": i})
        for kg in (52.2, 56.7, 61.2, 65.8, 70.3, 77.1, 83.9, 93, 120.2):
            self.save_weight({"limit_kg": kg, "label": format_kg(kg)})
        self.update_tournament(
            {
                "name": "Фестиваль спортивных единоборств",
                "kind": "смешанное боевое единоборство (ММА)",
                "date": "2024-09-14",
                "city": "г. Калининград",
                "chief_referee": "Бохан Е.А.",
                "chief_secretary": "Мамонов В.",
            }
        )
