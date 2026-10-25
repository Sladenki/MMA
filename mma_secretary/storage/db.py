from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS tournament (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT '',
  date TEXT,
  city TEXT NOT NULL DEFAULT '',
  chief_referee TEXT NOT NULL DEFAULT '',
  chief_secretary TEXT NOT NULL DEFAULT '',
  rings INTEGER NOT NULL DEFAULT 1,
  bronze_bout INTEGER NOT NULL DEFAULT 0,
  two_bronzes INTEGER NOT NULL DEFAULT 1,
  award_walkover INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS age_group (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
  label TEXT NOT NULL,
  year_from INTEGER NOT NULL,
  year_to INTEGER NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS division (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
  code TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  rank_values TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS weight_class (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
  age_group_id INTEGER,
  limit_kg REAL NOT NULL,
  label TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS point_rule (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
  place_from INTEGER NOT NULL,
  place_to INTEGER NOT NULL,
  points INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS participant (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
  seq INTEGER,
  name TEXT NOT NULL,
  organization TEXT NOT NULL DEFAULT '',
  rank TEXT NOT NULL DEFAULT '',
  birth_year INTEGER,
  coach TEXT NOT NULL DEFAULT '',
  weight REAL,
  declared_weight REAL,
  status TEXT NOT NULL DEFAULT 'заявлен',
  draw_number INTEGER,
  gender TEXT NOT NULL DEFAULT 'муж',
  division_id INTEGER
);

CREATE TABLE IF NOT EXISTS weight_history (
  id INTEGER PRIMARY KEY,
  participant_id INTEGER NOT NULL REFERENCES participant(id) ON DELETE CASCADE,
  weight REAL NOT NULL,
  recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS category (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
  age_group_id INTEGER NOT NULL,
  division_id INTEGER NOT NULL,
  weight_class_id INTEGER NOT NULL,
  gender TEXT NOT NULL DEFAULT 'муж',
  bracket_kind TEXT,
  drawn_at TEXT,
  UNIQUE (tournament_id, age_group_id, division_id, weight_class_id, gender)
);

CREATE TABLE IF NOT EXISTS category_entry (
  id INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
  participant_id INTEGER NOT NULL REFERENCES participant(id) ON DELETE CASCADE,
  control_number INTEGER NOT NULL,
  UNIQUE (category_id, participant_id),
  UNIQUE (category_id, control_number)
);

CREATE TABLE IF NOT EXISTS bout (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
  category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
  match_key TEXT NOT NULL,
  bout_no INTEGER,
  round_code TEXT NOT NULL,
  slot INTEGER NOT NULL DEFAULT 0,
  blue_entry_id INTEGER,
  red_entry_id INTEGER,
  winner_entry_id INTEGER,
  method TEXT,
  ring INTEGER,
  scheduled_order INTEGER,
  is_bye INTEGER NOT NULL DEFAULT 0,
  source_blue TEXT,
  source_red TEXT,
  UNIQUE (category_id, match_key)
);

CREATE TABLE IF NOT EXISTS placement (
  id INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
  participant_id INTEGER NOT NULL REFERENCES participant(id) ON DELETE CASCADE,
  place INTEGER NOT NULL,
  points INTEGER NOT NULL,
  tied INTEGER NOT NULL DEFAULT 0,
  UNIQUE (category_id, participant_id)
);

CREATE TABLE IF NOT EXISTS draw_log (
  id INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL,
  method TEXT NOT NULL,
  seed INTEGER,
  created_at TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  undone INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS team_rep (
  id INTEGER PRIMARY KEY,
  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
  organization TEXT NOT NULL,
  representative TEXT NOT NULL DEFAULT '',
  UNIQUE (tournament_id, organization)
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self.migrate()
        self.conn.commit()

    def _columns(self, table: str) -> set[str]:
        return {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}

    def _add_column(self, table: str, name: str, decl: str) -> None:
        if name not in self._columns(table):
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    def migrate(self) -> None:
        self._add_column("participant", "gender", "TEXT NOT NULL DEFAULT 'муж'")
        self._add_column("participant", "division_id", "INTEGER")
        self._add_column("participant", "declared_weight", "REAL")
        self._add_column("category", "gender", "TEXT NOT NULL DEFAULT 'муж'")
        sql = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='category'"
        ).fetchone()
        text = (sql[0] if sql else "") or ""
        if "weight_class_id, gender" not in text.replace(" ", "") and "weight_class_id,gender" not in text.replace(" ", ""):
            self.conn.executescript(
                """
                PRAGMA foreign_keys=OFF;
                CREATE TABLE category_new (
                  id INTEGER PRIMARY KEY,
                  tournament_id INTEGER NOT NULL REFERENCES tournament(id),
                  age_group_id INTEGER NOT NULL,
                  division_id INTEGER NOT NULL,
                  weight_class_id INTEGER NOT NULL,
                  gender TEXT NOT NULL DEFAULT 'муж',
                  bracket_kind TEXT,
                  drawn_at TEXT,
                  UNIQUE (tournament_id, age_group_id, division_id, weight_class_id, gender)
                );
                INSERT INTO category_new
                  (id, tournament_id, age_group_id, division_id, weight_class_id, gender, bracket_kind, drawn_at)
                SELECT id, tournament_id, age_group_id, division_id, weight_class_id,
                       COALESCE(gender, 'муж'), bracket_kind, drawn_at
                FROM category;
                DROP TABLE category;
                ALTER TABLE category_new RENAME TO category;
                PRAGMA foreign_keys=ON;
                """
            )

    def close(self) -> None:
        self.conn.close()
