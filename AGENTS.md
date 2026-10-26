# Контекст проекта для AI (не пользовательская документация)

Читай этот файл в начале сессии вместо полного обхода репозитория. Пользовательский README — `README.md`. Этот файл — для агента: архитектура, где что лежит, правила домена, куда править.

Обновляй этот файл при существенных изменениях архитектуры или правил турнира.

---

## Что это

**Секретарь ММА** — локальная программа секретаря турнира (замена Excel «MMA_2024 программа взвешивания»). Offline: FastAPI + SQLite + один SPA в браузере. Интернет не нужен.

- Версия: `mma_secretary.__version__` (= `1.0.0`)
- UI: http://127.0.0.1:8765
- Язык UI и домена: русский
- Стек: Python 3, FastAPI, uvicorn, openpyxl, vanilla JS (`app.js` / `app.css`), pytest

---

## Запуск и сборка

| Что | Как |
|-----|-----|
| Dev | `python run.py` или `start.bat` (`run.py` убивает процесс на порту 8765 и стартует сервер) |
| Модуль | `python -m mma_secretary` |
| Тесты | `pytest` |
| Exe | `build.bat` + PyInstaller `secretary.spec` → «Секретарь ММА.exe» |

Данные:

- Dev: `data/tournament.db` (+ `data/saves/` JSON-архивы)
- Frozen exe: `%Documents%/Секретарь ММА/` (миграция со старого `data` рядом с exe)
- Переопределение: env `MMA_DATA_DIR`
- Фото: `photos/` (dev) или `data/photos` (exe)
- Статика: `mma_secretary/web/static/`

---

## Архитектура слоёв

```
run.py / __main__.py
  → web/server.py (uvicorn, авто-браузер)
    → web/app.py (FastAPI + StaticFiles + routers)
      → web/deps.py  ← синглтоны: Database, TournamentService, Archives
        → services/* (mixins → TournamentService)
          → core/*   (чистые правила, без БД)
          → storage/db.py (SQLite schema + migrate)
```

**Жёсткое правило:** правила турнира живут в `core/` и не знают про SQLite. Новый кусок продукта = mixin в `services/` + роутер в `web/routes/`. Фасад: `services/engine.py` → `TournamentService`.

UI — не React: один `index.html`, навигация по `data-view`, рендер в `views` внутри `app.js`. Печать — HTML с `/print/...` (PDF из браузера).

---

## Дерево (важное)

```
mma_secretary/
  paths.py              # project_dir, data_dir, photos_dir, frozen/exe
  core/
    models.py           # dataclass: AgeGroup, Division, WeightClass, Participant, Bracket, …
    normalize.py        # имя, разряд, орг, вес, пол, parse_age_bounds
    grouping.py         # classify → CategoryKey | Unplaced
    draw.py             # жребий, control numbers, разведение клубов
    bracket.py          # single-elim сетка до 64, bye, propagate, bronze
    placements.py       # места из сетки + очки
    team.py             # командный зачёт
    labels.py           # подписи
  services/
    engine.py           # TournamentService = mixins
    catalog.py          # реквизиты, возраст/дивизион/вес/очки, seed_defaults
    participants.py     # CRUD, weigh, demo
    brackets.py         # classify, сетки, бои, результаты
    reports.py          # placements, teams, mandate, medalists
    history.py          # audit_log, undo, snapshot/restore, export/import JSON, new tournament
    import_export.py    # XLSX in/out
    documents.py        # HTML протоколы / SVG сеток
    archives.py         # JSON-сейвы в data/saves
    common.py           # _now, _row
  storage/db.py         # SCHEMA + migrate (gender, division_id, UNIQUE category+gender)
  web/
    deps.py, errors.py, server.py, app.py
    routes/             # pages, catalog, participants, competition, reports, system, print
    static/             # index.html, about.html, app.js, app.css, icon
tests/                  # unit + gold_2024 fixture
tools/make_icon.py
```

---

## UI-экраны (`app.js` → `views`)

| view | Смысл |
|------|--------|
| archives | сейвы JSON, новый турнир |
| setup | реквизиты + справочники + очки |
| people | участники, импорт XLSX |
| weigh | взвешивание + история веса |
| cats | разбить на категории, redraw |
| brackets | сетка категории |
| bouts | список боёв, ринг/порядок |
| results | места, команды, мандат |
| docs | ссылки на печать и Excel |

Глобально: Отменить (`POST /api/undo`), резервная копия JSON, импорт JSON, инструкция `.docx`.

---

## API (кратко)

- **Catalog:** `GET /api/bootstrap`, `PUT /api/tournament`, age-groups / divisions / weights CRUD, `PUT /api/points`
- **People:** participants CRUD, `POST …/weigh`, `…/weights`, `POST /api/participants/import`, `POST /api/demo`
- **Competition:** `POST /api/classify`, categories, redraw, order, bouts result/clear/schedule
- **Reports:** placements, teams (+rep), mandate, medalists
- **System:** undo, export/import JSON, saves CRUD, `POST /api/tournament/new`, xlsx exports
- **Print:** `/print/weigh-in|mandate|pairs|corners|brackets|personal|scorecards|teams|medals|certificates|report`

Ошибки домена → `web/errors.py` (ValueError и т.п. в HTTP).

---

## Доменные правила (критично при правках)

1. **Возраст:** label вида `2007-2008` → `year_from`/`year_to` через `parse_age_bounds`. Попадание: год рождения в диапазоне.
2. **Дивизион:** явный `participant.division_id`, иначе код разряда в справочнике, иначе **первый** дивизион в списке. (Старый README про «нераспознанный → не размещены» частично устарел относительно текущего `division_for`.)
3. **Вес:** `weight` = фактический (для категорий/сеток), `declared_weight` = заявленный. Классификация только по фактическому. Старый JSON с одним `weight` → это заявленный (`declared_weight`), факт = null. Миграция БД `legacy_weight_to_declared` один раз переносит старые `weight` → `declared_weight`.
4. **Пол:** `муж` / `жен`; категория уникальна по (age, division, weight, gender).
5. **Статусы:** в т.ч. `заявлен`, `взвешен`, `снят`, `не явился` — снятые/неявки не в сетку.
6. **Жребий:** control numbers, журнал `draw_log` с seed. «Состав сетки» (`manual_order`) задаёт кто в категории и в каком порядке — можно взять человека из другой категории или из тех, кто ещё не в сетке. Undo этого действия откатывает все затронутые сетки.
7. **Сетка:** single elimination, size 4…64; n>64 — ошибка. Bye auto-propagate. Опции турнира: `two_bronzes` (по умолчанию 1 — оба полуфинальных лузера = 3), `bronze_bout` (бой за 3–4).
8. **Очки по умолчанию:** 1→10, 2→8, 3→6, 5–8→2, 9–16→1, 17–64→0.
9. **Undo:** `audit_log` со снимками; не все действия откатываются — смотри `HistoryMixin.undo`.
10. **Эталон:** `tests/fixtures/gold_2024.json` — 14 человек с турнира 14.09.2024; тесты grouping/draw не ломать без причины.

---

## SQLite (основные таблицы)

`tournament` (один турнир в БД) → `age_group`, `division`, `weight_class`, `point_rule`, `participant`, `weight_history`, `category`, `category_entry` (control_number), `bout`, `placement`, `draw_log`, `audit_log`, `team_rep`.

WAL, foreign_keys ON. Миграции — в `Database.migrate()` (ALTER / rebuild category UNIQUE).

---

## Как править безопасно

| Задача | Куда |
|--------|------|
| Формула сетки / bye / бронза | `core/bracket.py`, `core/placements.py` |
| Разбиение по категориям | `core/grouping.py`, `normalize.py` |
| Жребий | `core/draw.py` |
| Командный зачёт | `core/team.py` |
| Persist + API поведение | соответствующий mixin в `services/` |
| HTTP | тонкий роутер в `web/routes/` |
| UI экран | `web/static/app.js` (+ css/html) |
| Печать | `services/documents.py` + `routes/print.py` |
| Пути данных / exe | `paths.py`, `secretary.spec` |

После доменных правок — `pytest`. Cache-bust в HTML: query `?v=` у `app.js` / `app.css`.

Не коммить `data/*.db*` (gitignore). Не раздувать README пользовательскими деталями для AI — обновляй **этот** файл.

---

## Стиль кода в репо

- Русские docstring/комментарии там, где объясняют домен.
- Mixins собирают сервис; роутеры тонкие.
- Без лишних абстракций: dataclasses в core, sqlite3 напрямую.
- Сообщения ошибок пользователю — на русском.

---

## Типичный workflow секретаря

Реквизиты → участники (ручные/XLSX/демо) → взвешивание → «Разбить на категории» → сетки/бои → итоги → печать/XLSX/JSON-бэкап. Автосохранение в SQLite после действий; Undo — последнее из audit.
