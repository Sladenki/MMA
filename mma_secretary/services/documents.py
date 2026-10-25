from __future__ import annotations

import base64
import mimetypes
from html import escape
from pathlib import Path

from mma_secretary.core.labels import round_ru
from mma_secretary.core.normalize import format_kg
from mma_secretary.paths import photos_dir, static_dir
from mma_secretary.services.engine import TournamentService

PHOTOS = photos_dir()
_APP_IMAGES = {"icon.png", "favicon.ico"}
_PHOTO_DATA = None


def _photo_file() -> Path | None:
    roots = [
        PHOTOS,
        static_dir(),
    ]
    preferred = ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp")
    for root in roots:
        if not root.exists():
            continue
        names = {
            f.name.lower(): f
            for f in root.iterdir()
            if f.is_file() and f.name.lower() not in _APP_IMAGES
        }
        for key in preferred:
            if key in names:
                return names[key]
        for f in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if f.name.lower() in _APP_IMAGES:
                continue
            if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                return f
    return None


def _photo_src() -> str:
    global _PHOTO_DATA
    if _PHOTO_DATA is not None:
        return _PHOTO_DATA
    path = _photo_file()
    if not path:
        _PHOTO_DATA = ""
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    _PHOTO_DATA = f"data:{mime};base64,{raw}"
    return _PHOTO_DATA


def _header(t: dict) -> str:
    src = _photo_src()
    photo = f'<img class="doc-logo" src="{escape(src)}" alt="">' if src else ""
    return f"""
    <header class="doc-head">
      <div class="doc-head-row">
        {photo}
        <div class="doc-head-text">
          <div class="doc-title">{escape(t.get("name") or "Турнир")}</div>
          <div class="doc-sub">{escape(t.get("kind") or "")}</div>
          <div class="doc-meta">{escape(str(t.get("date") or ""))} · {escape(t.get("city") or "")}</div>
        </div>
      </div>
    </header>
    """


CSS = """
@page { size: A4; margin: 12mm; }
@media screen {
  html { zoom: 1.5; }
}
@media print {
  html { zoom: 1; }
}
body { font-family: "Times New Roman", Times, serif; color: #111; }
.doc-head { text-align: center; margin-bottom: 14px; }
.doc-head-row { display: inline-flex; align-items: center; justify-content: center; gap: 14px; max-width: 100%; }
.doc-logo { position: static; height: 64px; width: auto; max-width: 140px; object-fit: contain; flex-shrink: 0; }
.doc-head-text { text-align: center; }
.doc-title { font-size: 18px; font-weight: 700; text-transform: uppercase; }
.doc-sub { font-size: 13px; }
.doc-meta { font-size: 12px; margin-top: 4px; }
h2 { font-size: 15px; text-align: center; margin: 16px 0 8px; }
table { border-collapse: collapse; width: 100%; font-size: 11px; }
th, td { border: 1px solid #222; padding: 3px 5px; }
th { background: #eee; }
.sig { margin-top: 28px; display: flex; flex-direction: column; align-items: flex-start; gap: 10px; font-size: 12px; }
.bracket-foot .sig { margin-top: 0; }
.sig-row { display: flex; align-items: flex-end; gap: 10px; }
.sig-role, .sig-name { white-space: nowrap; }
.sig-line { display: inline-block; width: 110px; border-bottom: 1px solid #111; height: 14px; }
.page-break { page-break-before: always; }
@media screen {
  .page-break { margin-top: 40px; padding-top: 28px; }
}
.blue { color: #123a8a; }
.red { color: #9b1c1c; }
.cert { text-align: center; padding: 40px 20px; border: 8px double #7a1d1d; min-height: 70vh; }
.cert h1 { letter-spacing: .3em; font-size: 28px; color: #7a1d1d; }
.bracket-foot { margin-top: 20px; margin-bottom: 12px; display: flex; align-items: flex-end; justify-content: space-between; gap: 32px; }
.prize-block { flex: 0 0 140px; font-size: 11px; }
.prize-block h3 { font-size: 12px; margin: 0 0 6px; text-align: left; font-weight: 700; }
.prize-row { margin-bottom: 8px; }
.prize-line { display: block; border-bottom: 1px solid #111; height: 12px; width: 100%; }
"""


def wrap(title: str, body: str, landscape: bool = False) -> str:
    orient = "landscape" if landscape else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
    <title>{escape(title)}</title>
    <link rel="icon" href="/favicon.ico" sizes="any">
    <style>{CSS}</style></head>
    <body class="{orient}">{body}</body></html>"""


def protocol_weigh_in(svc: TournamentService) -> str:
    t = svc.get_tournament()
    rows = "".join(
        f"<tr><td>{p['seq'] or ''}</td><td>{p['draw_number'] or ''}</td><td></td>"
        f"<td>{escape(p['name'])}</td><td>{escape(p['organization'] or '')}</td>"
        f"<td>{escape(p['rank'] or '')}</td><td>{p['birth_year'] or ''}</td>"
        f"<td>{escape(p['coach'] or '')}</td>"
        f"<td>{format_kg(p['declared_weight']) if p.get('declared_weight') is not None else ''}</td>"
        f"<td>{format_kg(p['weight']) if p['weight'] is not None else ''}</td></tr>"
        for p in svc.list_participants("team")
    )
    body = _header(t) + f"""
    <h2>Протокол взвешивания и жеребьёвки</h2>
    <table>
      <tr><th>№</th><th>Жребий</th><th>Контр.</th><th>Фамилия, имя</th>
      <th>Город, организация</th><th>Разряд</th><th>Год</th><th>Тренер</th>
      <th>Заявл.</th><th>Факт.</th></tr>
      {rows}
    </table>
    {_sigs(t)}
    """
    return wrap("Протокол взвешивания", body)


def protocol_mandate(svc: TournamentService) -> str:
    t = svc.get_tournament()
    man = svc.mandate()
    head = "".join(f"<th>{escape(w)}</th>" for w in man["weights"])
    rows = ""
    for r in man["rows"]:
        cells = "".join(f"<td>{r['cells'].get(w, 0) or ''}</td>" for w in man["weights"])
        rows += f"<tr><td>{escape(r['organization'])}</td>{cells}<td>{r['total']}</td><td>{escape(r['representative'])}</td></tr>"
    totals = "".join(f"<td>{man['col_totals'].get(w, 0)}</td>" for w in man["weights"])
    titles = "".join(f"<tr><td>{escape(k)}</td><td>{v}</td></tr>" for k, v in man["titles"].items())
    body = _header(t) + f"""
    <h2>Протокол мандатной комиссии</h2>
    <table>
      <tr><th>Организация</th>{head}<th>Итого</th><th>Представитель</th></tr>
      {rows}
      <tr><th>Итого</th>{totals}<th>{man['grand_total']}</th><th></th></tr>
    </table>
    <h2>Участники по званиям</h2>
    <table><tr><th>Звание / разряд</th><th>Число</th></tr>{titles}</table>
    {_sigs(t)}
    """
    return wrap("Мандатная комиссия", body)


def pair_list(svc: TournamentService) -> str:
    t = svc.get_tournament()
    first_rounds = {"1/32", "1/16", "1/8", "1/4", "финал", "круг"}
    rows = ""
    for b in svc.list_bouts():
        if b["is_bye"] or not b["blue"] or not b["red"]:
            continue
        if b["round_code"] not in first_rounds and b["round_code"] != "1/2":
            continue
        rows += (
            f"<tr><td>{b['bout_no'] or ''}</td>"
            f"<td class='blue'>{escape(b['blue']['name'])} ({escape(b['blue']['organization'])})</td>"
            f"<td class='red'>{escape(b['red']['name'])} ({escape(b['red']['organization'])})</td>"
            f"<td>{escape(str(b.get('weight_label') or ''))}</td><td>{escape(round_ru(b['round_code']))}</td></tr>"
        )
    body = _header(t) + f"""
    <h2>Список пар</h2>
    <table><tr><th>№ боя</th><th>Синий угол</th><th>Красный угол</th><th>Категория</th><th>Тур</th></tr>{rows}</table>
    """
    return wrap("Список пар", body)


def corner_list(svc: TournamentService) -> str:
    t = svc.get_tournament()
    rows = ""
    for b in svc.list_bouts():
        if b["is_bye"] or not b["blue"] or not b["red"]:
            continue
        rows += (
            f"<tr><td>{b['bout_no'] or ''}</td>"
            f"<td class='blue'>{escape(b['blue']['name'])}<br><small>{escape(b['blue']['organization'])}</small></td>"
            f"<td class='red'>{escape(b['red']['name'])}<br><small>{escape(b['red']['organization'])}</small></td>"
            f"<td>{escape(str(b.get('weight_label') or ''))}</td>"
            f"<td>{escape(round_ru(b['round_code']))}</td><td>{b.get('ring') or ''}</td></tr>"
        )
    body = _header(t) + f"""
    <h2>Список боёв по углам</h2>
    <table><tr><th>№</th><th>Синий угол</th><th>Красный угол</th><th>Вес</th><th>Тур</th><th>Ринг</th></tr>{rows}</table>
    """
    return wrap("Бои по углам", body)


def personal_results(svc: TournamentService) -> str:
    t = svc.get_tournament()
    rows = "".join(
        f"<tr><td>{escape(r['age_label'])} {escape(r['division_code'])} {escape(r['weight_label'])}</td>"
        f"<td>{r['place']}</td><td>{escape(r['name'])}</td><td>{r['birth_year'] or ''}</td>"
        f"<td>{escape(r['rank'] or '')}</td><td>{escape(r['organization'])}</td>"
        f"<td>{escape(r['coach'] or '')}</td><td>{r['points']}</td></tr>"
        for r in svc.placements_report()
    )
    body = _header(t) + f"""
    <h2>Протокол результатов личного первенства</h2>
    <table><tr><th>Категория</th><th>Место</th><th>Участник</th><th>Год</th><th>Разряд</th><th>Организация</th><th>Тренер</th><th>Очки</th></tr>
    {rows}</table>{_sigs(t)}
    """
    return wrap("Личное первенство", body)


def team_protocol(svc: TournamentService) -> str:
    t = svc.get_tournament()
    rows = "".join(
        f"<tr><td>{s['place']}</td><td>{escape(s['organization'])}</td><td>{s['points']}</td>"
        f"<td>{escape(s['representative'])}</td></tr>"
        for s in svc.team_report()
    )
    body = _header(t) + f"""
    <h2>Командный протокол</h2>
    <table><tr><th>Место</th><th>Организация</th><th>Очки</th><th>Представитель</th></tr>{rows}</table>
    {_sigs(t)}
    """
    return wrap("Командный протокол", body)


def medalists_html(svc: TournamentService) -> str:
    t = svc.get_tournament()
    rows = "".join(
        f"<tr><td>{escape(r['age_label'])} {escape(r['division_code'])} {escape(r['weight_label'])}</td>"
        f"<td>{r['place']}</td><td>{escape(r['name'])}</td><td>{escape(r['organization'])}</td>"
        f"<td>{escape(r['coach'] or '')}</td></tr>"
        for r in svc.medalists()
    )
    body = _header(t) + f"""
    <h2>Призёры</h2>
    <table><tr><th>Категория</th><th>Место</th><th>ФИО</th><th>Организация</th><th>Тренер</th></tr>{rows}</table>
    """
    return wrap("Призёры", body)


def certificates(svc: TournamentService) -> str:
    t = svc.get_tournament()
    pages = []
    word = {1: "первое", 2: "второе", 3: "третье"}
    for r in svc.medalists():
        pages.append(f"""
        <section class="cert page-break">
          {f'<img class="doc-logo" src="{escape(_photo_src())}" alt="" style="margin-bottom:12px">' if _photo_src() else ""}
          <div class="doc-sub">{escape(t.get("name") or "")}</div>
          <h1>ГРАМОТА</h1>
          <p>награждается</p>
          <p style="font-size:26px;font-weight:700">{escape(r["name"])}</p>
          <p>{escape(r["organization"] or "")}</p>
          <p>за {word.get(r["place"], str(r["place"]))} место</p>
          <p>{escape(r["age_label"])} · {escape(r["division_code"])} · до {escape(r["weight_label"])} кг</p>
          <p style="margin-top:40px">{escape(str(t.get("date") or ""))} · {escape(t.get("city") or "")}</p>
          <p>Главный судья ________________ {escape(t.get("chief_referee") or "")}</p>
        </section>
        """)
    if pages:
        pages[0] = pages[0].replace(" page-break", "", 1)
    return wrap("Грамоты", "".join(pages) or "<p>Нет призёров</p>")


def scorecards(svc: TournamentService) -> str:
    t = svc.get_tournament()
    cards = []
    for b in svc.list_bouts():
        if b["is_bye"] or not b["blue"] or not b["red"]:
            continue
        cards.append(f"""
        <section class="page-break">
          {_header(t)}
          <h2>Судейская записка · бой № {b["bout_no"] or "—"}</h2>
          <table>
            <tr><th>Категория</th><td>{escape(str(b.get("weight_label") or ""))}</td>
                <th>Тур</th><td>{escape(round_ru(b["round_code"]))}</td><th>Ринг</th><td>{b.get("ring") or ""}</td></tr>
          </table>
          <br>
          <table>
            <tr><th style="width:50%" class="blue">Синий угол</th><th class="red">Красный угол</th></tr>
            <tr>
              <td class="blue">{escape(b["blue"]["name"])}<br>{escape(b["blue"]["organization"])}</td>
              <td class="red">{escape(b["red"]["name"])}<br>{escape(b["red"]["organization"])}</td>
            </tr>
            <tr><td>Очки: ________</td><td>Очки: ________</td></tr>
          </table>
          <p>Победитель: {escape((b["winner"] or {}).get("name") or "________________")}</p>
          <p>Рефери ________________　　Арбитр ________________</p>
        </section>
        """)
    if cards:
        cards[0] = cards[0].replace(" page-break", "", 1)
    return wrap("Судейские записки", "".join(cards) or "<p>Нет боёв</p>")


def _prize_blanks() -> str:
    """Пустые строки для рукописного ввода призёров: 1, 2 и два 3-х места."""
    rows = "".join('<div class="prize-row"><span class="prize-line"></span></div>' for _ in range(4))
    return f'<aside class="prize-block"><h3>Призёры</h3>{rows}</aside>'


def brackets_html(svc: TournamentService) -> str:
    t = svc.get_tournament()
    parts = []
    for cat in svc.list_categories():
        if cat["n"] == 0:
            continue
        detail = svc.category_detail(cat["id"])
        svg = bracket_svg(detail)
        parts.append(
            f"<section class='page-break'>{_header(t)}"
            f"<h2>{escape(cat['age_label'])} · {escape(cat.get('gender_label') or '')} · "
            f"{escape(cat['division_code'])} · до {escape(cat['weight_label'])} кг ({cat['n']})</h2>"
            f"{svg}"
            f"<div class='bracket-foot'>{_sigs(t)}{_prize_blanks()}</div></section>"
        )
    if parts:
        parts[0] = parts[0].replace(" page-break", "", 1)
    return wrap("Сетки", "".join(parts) or "<p>Сеток ещё нет</p>", landscape=True)


def full_report(svc: TournamentService) -> str:
    chunks = [
        protocol_mandate(svc),
        team_protocol(svc),
        medalists_html(svc),
        personal_results(svc),
        brackets_html(svc),
    ]
    bodies = []
    for i, html in enumerate(chunks):
        start = html.find("<body")
        start = html.find(">", start) + 1
        end = html.rfind("</body>")
        chunk = html[start:end]
        if i:
            chunk = f"<div class='page-break'></div>{chunk}"
        bodies.append(chunk)
    t = svc.get_tournament()
    return wrap("Итоговый отчёт", "".join(bodies), landscape=False)


def _sigs(t: dict) -> str:
    return f"""
    <div class="sig">
      <div class="sig-row">
        <span class="sig-role">Главный судья</span>
        <span class="sig-line"></span>
        <span class="sig-name">{escape(t.get("chief_referee") or "")}</span>
      </div>
      <div class="sig-row">
        <span class="sig-role">Главный секретарь</span>
        <span class="sig-line"></span>
        <span class="sig-name">{escape(t.get("chief_secretary") or "")}</span>
      </div>
    </div>
    """


def bracket_svg(detail: dict) -> str:
    entries = {e["id"]: e for e in detail["entries"]}
    if detail["category"].get("bracket_kind") == "round_robin":
        return _rr_svg(detail, entries)
    return _elim_svg(detail, entries)


def _rr_svg(detail: dict, entries: dict) -> str:
    """Старые сохранения с круговой сеткой. Новые категории так больше не строятся."""
    y = 40
    lines = []
    for b in detail["bouts"]:
        if b.get("is_bye"):
            continue
        blue = _label(entries, b.get("blue_entry_id"))
        red = _label(entries, b.get("red_entry_id"))
        w = ""
        if b.get("winner_entry_id"):
            w = f" → {escape(_label(entries, b['winner_entry_id']))}"
        lines.append(
            f"<text x='20' y='{y}' font-size='14'>Бой {b.get('bout_no') or ''}: {escape(blue)} — {escape(red)}{w}</text>"
        )
        y += 28
    return f"<svg xmlns='http://www.w3.org/2000/svg' width='720' height='{y+20}'>{''.join(lines)}</svg>"


def _label(entries: dict, eid) -> str:
    if not eid:
        return "—"
    e = entries.get(eid) or {}
    return f"{e.get('control_number', '')}. {e.get('name', '')}"


def _elim_svg(detail: dict, entries: dict) -> str:
    order = ["1/32", "1/16", "1/8", "1/4", "1/2", "финал"]
    by_round: dict[str, list] = {}
    for b in detail["bouts"]:
        if b.get("round_code") in order:
            by_round.setdefault(b["round_code"], []).append(b)
    rounds = [sorted(by_round[k], key=lambda x: x.get("slot") or 0) for k in order if k in by_round]
    if not rounds:
        return "<p>Сетка ещё не собрана</p>"
    columns: list[tuple[str, list[str]]] = []
    first = rounds[0]
    start_slots = []
    for b in first:
        start_slots.append(_label(entries, b.get("blue_entry_id")))
        start_slots.append(_label(entries, b.get("red_entry_id")))
    columns.append((str(len(start_slots)), start_slots))
    for matches in rounds:
        columns.append((str(len(matches)), [_label(entries, b.get("winner_entry_id")) for b in matches]))
    col_w, slot_h = 200, 36
    first_n = len(columns[0][1]) or 4
    height = 50 + first_n * slot_h
    width = 30 + len(columns) * col_w
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' font-family='Times New Roman, serif'>"]
    for ci, (title, slots) in enumerate(columns):
        x = 16 + ci * col_w
        parts.append(f"<text x='{x}' y='18' font-size='14' font-weight='700'>{escape(title)}</text>")
        gap = (height - 28) / max(len(slots), 1)
        for i, name in enumerate(slots):
            y = int(28 + gap * i + (gap - 28) / 2)
            parts.append(f"<rect x='{x}' y='{y}' width='180' height='28' rx='3' fill='#fff' stroke='#333'/>")
            parts.append(f"<text x='{x+6}' y='{y+19}' font-size='12'>{escape(name)}</text>")
    parts.append("</svg>")
    return "".join(parts)
