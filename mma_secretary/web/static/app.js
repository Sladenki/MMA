const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];

const state = { view: "archives", boot: null, sort: "seq", catId: null, dirty: false, formBaseline: "" };

const titles = {
  archives: ["Турниры", "Сохраните текущие данные, начните пустой турнир или откройте другую копию."],
  setup: ["Реквизиты", "Название турнира, судьи, возрасты (например 2018-2019), дивизионы и веса"],
  people: ["Участники", ""],
  weigh: ["Взвешивание", ""],
  cats: ["Категории", "Разбейте список по возрасту, дивизиону и весу. Кто не попал — будет в жёлтом списке, а не пропадёт."],
  brackets: ["Сетки", "Выберите категорию и нажмите на пару, чтобы записать победителя. Он сам пойдёт дальше."],
  bouts: ["Бои", "Все пары турнира по порядку. Здесь же можно поставить номер ринга."],
  results: ["Итоги", "Места, очки команд и мандатная комиссия считаются автоматически."],
  docs: ["Документы", "Откройте форму и в браузере нажмите Ctrl+P — так получается PDF."],
};

const KIND_RU = {
  empty: "пусто",
  walkover: "без боя",
  final: "финал",
  round_robin: "круговая",
  single_elim: "олимпийская",
};
const ROUND_RU = {
  "1/32": "1/32 финала",
  "1/16": "1/16 финала",
  "1/8": "1/8 финала",
  "1/4": "1/4 финала",
  "1/2": "1/2 финала",
  "финал": "финал",
  "за бронзу": "за бронзу",
  "круг": "круг",
};

function kindRu(v) { return KIND_RU[v] || v || "—"; }
function roundRu(v) { return ROUND_RU[v] || v || "—"; }
function statusClass(s) {
  if (s === "допущен" || s === "взвешен") return "ok";
  if (s === "снят" || s === "не явился") return "bad";
  if (s === "заявлен") return "warn";
  return "";
}

function formSignature(root = $("#view")) {
  if (!root) return "";
  return [...root.querySelectorAll("input, select, textarea")]
    .filter((el) => {
      if (el.type === "file" || el.type === "hidden") return false;
      if (el.classList.contains("dd-native") || el.closest(".dd-menu")) return false;
      if (el.id === "q" || el.id === "sort" || el.id === "cat-sel" || el.id === "save-name") return false;
      if (el.closest(".search-box")) return false;
      return true;
    })
    .map((el) => `${el.id}|${el.name}|${el.dataset.w || ""}|${el.dataset.dw || ""}|${el.dataset.st || ""}|${el.dataset.pp || ""}|${el.dataset.draw || ""}|${el.dataset.ring || ""}|${el.dataset.org || ""}|${el.dataset.mid || ""}=${el.value}`)
    .join("\n");
}

function setSaveState(mode) {
  const el = $("#save-dot");
  if (!el) return;
  const effective = mode === "busy" ? "busy" : (state.dirty ? "dirty" : "saved");
  el.className = "save-ind " + effective;
  const label = $(".save-label", el);
  if (label) {
    label.textContent = effective === "busy"
      ? "сохранение…"
      : effective === "dirty"
        ? "не сохранено"
        : "сохранено";
  }
}

function markClean() {
  state.formBaseline = formSignature();
  state.dirty = false;
  setSaveState("saved");
}

function checkDirty() {
  const dirty = formSignature() !== state.formBaseline;
  if (dirty === state.dirty) return;
  state.dirty = dirty;
  setSaveState(dirty ? "dirty" : "saved");
}

function watchDirty(root = $("#view")) {
  if (!root) return;
  root.addEventListener("input", checkDirty);
  root.addEventListener("change", checkDirty);
}

function confirmLeaveUnsaved() {
  if (!state.dirty) return true;
  return confirm("Есть несохранённые данные. Уйти и потерять их?");
}

async function api(path, opts={}) {
  setSaveState("busy");
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers||{}) },
    ...opts,
    body: opts.body && typeof opts.body !== "string" && !(opts.body instanceof FormData)
      ? JSON.stringify(opts.body) : opts.body,
  });
  setSaveState(state.dirty ? "dirty" : "saved");
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("json")) return res.json();
  return res;
}

function toast(msg, kind="ok") {
  const n = document.createElement("div");
  n.textContent = msg;
  n.style.cssText = `position:fixed;right:18px;bottom:18px;background:${kind==="ok"?"#16324f":"#c0122a"};color:#fff;padding:12px 16px;border-radius:8px;z-index:50;font-weight:600`;
  document.body.appendChild(n);
  setTimeout(() => n.remove(), 2800);
}

function formatWhen(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso || "");
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatKg(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return String(n).replace(".", ",");
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function closeAllDd(except) {
  $$(".dd.open").forEach(el => { if (el !== except) el.classList.remove("open"); });
}

function placeDdMenu(wrap) {
  const btn = $(".dd-btn", wrap);
  const menu = $(".dd-menu", wrap);
  const r = btn.getBoundingClientRect();
  const width = Math.max(r.width, wrap.classList.contains("dd-wide") ? 360 : r.width);
  menu.style.minWidth = r.width + "px";
  menu.style.width = Math.min(width, window.innerWidth - 24) + "px";
  menu.style.left = Math.min(r.left, window.innerWidth - width - 12) + "px";
  const spaceBelow = window.innerHeight - r.bottom;
  if (spaceBelow < 220 && r.top > spaceBelow) {
    menu.style.top = "auto";
    menu.style.bottom = (window.innerHeight - r.top + 4) + "px";
    menu.style.maxHeight = Math.min(280, r.top - 12) + "px";
  } else {
    menu.style.bottom = "auto";
    menu.style.top = (r.bottom + 4) + "px";
    menu.style.maxHeight = Math.min(280, spaceBelow - 12) + "px";
  }
}

function wrapSelect(sel) {
  if (sel.closest(".dd")) return;
  const wrap = document.createElement("div");
  wrap.className = "dd";
  if (sel.closest("td")) wrap.classList.add("dd-compact");
  if (sel.id === "cat-sel") wrap.classList.add("dd-wide");
  sel.parentNode.insertBefore(wrap, sel);
  sel.classList.add("dd-native");
  sel.tabIndex = -1;
  wrap.appendChild(sel);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "dd-btn";
  btn.setAttribute("aria-haspopup", "listbox");
  btn.innerHTML = `<span class="dd-label"></span><svg class="dd-caret" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>`;
  wrap.appendChild(btn);

  const menu = document.createElement("div");
  menu.className = "dd-menu";
  menu.setAttribute("role", "listbox");
  wrap.appendChild(menu);

  const syncLabel = () => {
    const opt = sel.selectedOptions[0];
    $(".dd-label", btn).textContent = opt ? opt.textContent : "—";
    btn.setAttribute("aria-expanded", wrap.classList.contains("open") ? "true" : "false");
  };

  const fillMenu = () => {
    menu.innerHTML = [...sel.options].map((o, i) =>
      `<button type="button" role="option" class="dd-item${o.selected ? " selected active" : ""}" data-i="${i}">${esc(o.textContent)}</button>`
    ).join("");
  };

  const pick = (i) => {
    if (i < 0 || i >= sel.options.length) return;
    sel.selectedIndex = i;
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    syncLabel();
    closeAllDd();
  };

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const willOpen = !wrap.classList.contains("open");
    closeAllDd();
    if (willOpen) {
      fillMenu();
      wrap.classList.add("open");
      placeDdMenu(wrap);
      syncLabel();
    }
  });

  menu.addEventListener("click", (e) => {
    const item = e.target.closest(".dd-item");
    if (!item) return;
    e.stopPropagation();
    pick(+item.dataset.i);
  });

  wrap.addEventListener("keydown", (e) => {
    if (!wrap.classList.contains("open")) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        btn.click();
      }
      return;
    }
    const items = $$(".dd-item", menu);
    let idx = items.findIndex(x => x.classList.contains("active"));
    if (idx < 0) idx = items.findIndex(x => x.classList.contains("selected"));
    if (e.key === "Escape") { e.preventDefault(); closeAllDd(); return; }
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      pick(idx >= 0 ? +items[idx].dataset.i : sel.selectedIndex);
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!items.length) return;
      items[idx]?.classList.remove("active");
      idx = e.key === "ArrowDown"
        ? (idx + 1) % items.length
        : (idx <= 0 ? items.length - 1 : idx - 1);
      items[idx].classList.add("active");
      items[idx].scrollIntoView({ block: "nearest" });
    }
  });

  sel.addEventListener("change", syncLabel);
  syncLabel();
}

function enhanceSelects(root = document) {
  $$("select", root).forEach(wrapSelect);
}

document.addEventListener("click", (e) => { if (!e.target.closest(".dd")) closeAllDd(); });
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if ($(".dd.open")) { closeAllDd(); return; }
  if (!$("#modal").classList.contains("hidden")) closeModal();
});
window.addEventListener("scroll", (e) => {
  const open = $(".dd.open");
  if (!open) return;
  // Скролл внутри списка опций не закрывает меню
  if (e.target instanceof Element && open.contains(e.target)) return;
  closeAllDd();
}, true);
window.addEventListener("resize", () => closeAllDd());

function openModal(title, html, extraClass = "") {
  const card = $(".modal-card");
  card.className = "modal-card" + (extraClass ? " " + extraClass : "");
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html;
  $("#modal").classList.remove("hidden");
}
function closeModal() {
  $("#modal").classList.add("hidden");
  $(".modal-card").className = "modal-card";
}
$("#modal-close").onclick = closeModal;
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });

$$("#nav button").forEach(b => b.onclick = () => show(b.dataset.view));
$("#btn-undo").onclick = async () => {
  if (!confirmLeaveUnsaved()) return;
  try { const r = await api("/api/undo", { method: "POST", body: {} }); toast("Отменено"); state.dirty = false; show(state.view); }
  catch (e) { toast(e.message, "err"); }
};
$("#btn-backup").onclick = () => {
  if (!confirmLeaveUnsaved()) return;
  location.href = "/api/export";
};
$("#file-import").onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return;
  if (!confirmLeaveUnsaved()) { e.target.value = ""; return; }
  const fd = new FormData(); fd.append("file", f);
  await fetch("/api/import", { method: "POST", body: fd });
  toast("Турнир загружен");
  state.dirty = false;
  await boot(); show(state.view);
};
window.addEventListener("beforeunload", (e) => {
  if (!state.dirty) return;
  e.preventDefault();
  e.returnValue = "";
});

async function boot() {
  state.boot = await api("/api/bootstrap");
  $("#brand-sub").textContent = state.boot.tournament.name || "турнир";
}

async function show(view) {
  if (view !== state.view && !confirmLeaveUnsaved()) return;
  state.dirty = false;
  state.view = view;
  $$("#nav button").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  $("#page-title").textContent = titles[view][0];
  $("#page-hint").textContent = titles[view][1];
  $("#page-hint").hidden = !titles[view][1];
  $("#view").innerHTML = "<p>Загрузка…</p>";
  try {
    await views[view]();
    enhanceSelects($("#view"));
    markClean();
    watchDirty($("#view"));
  } catch (e) {
    $("#view").innerHTML = `<div class="warn-box">${esc(e.message)}</div>`;
    markClean();
  }
}

function resultForm(b, onDone) {
  if (!b.blue || !b.red) return;
  openModal("Кто победил" + (b.bout_no ? ` · бой № ${b.bout_no}` : ""), `
    <p>${esc(roundRu(b.round_title || b.round_code))}</p>
    <div class="pick">
      <button class="btn blue wide" id="pick-blue" type="button"><span class="pick-corner">Синий угол</span><span class="pick-name">${esc(b.blue.name)}</span></button>
      <button class="btn red wide" id="pick-red" type="button"><span class="pick-corner">Красный угол</span><span class="pick-name">${esc(b.red.name)}</span></button>
    </div>
    ${b.winner_entry_id || b.winner ? `<button class="btn sec" id="w-clr" type="button">Сбросить результат</button>` : ""}
  `);
  const send = async (entryId) => {
    await api(`/api/bouts/${b.id}/result`, { method:"POST", body:{ winner_entry_id: entryId }});
    closeModal(); onDone();
  };
  $("#pick-blue").onclick = () => send(b.blue.id);
  $("#pick-red").onclick = () => send(b.red.id);
  const clr = $("#w-clr");
  if (clr) clr.onclick = async () => { await api(`/api/bouts/${b.id}/clear`, { method:"POST", body:{} }); closeModal(); onDone(); };
}

async function renderArchives() {
  const t = state.boot.tournament;
  let saves = [];
  let apiOk = true;
  try { saves = await api("/api/saves"); } catch { apiOk = false; }
  $("#view").innerHTML = `
    <div class="card">
      ${state.boot.keeps_documents ? `<p class="hint-inline">Турнир хранится в Документах, в папке «Секретарь ММА». Если удалить программу из Загрузок, данные останутся.</p>` : ""}
      ${apiOk ? "" : `<div class="warn-box">Сервер старый и не умеет копии. Закройте чёрное окно, запустите start.bat заново, затем обновите страницу.</div>`}
      <div class="add-row" style="margin-bottom:12px">
        <input id="save-name" placeholder="Название копии, например Калининград 14.09.2024">
        <button class="btn" id="save-now" type="button">Сохранить этот турнир</button>
        <button class="btn sec" id="new-now" type="button">Начать с нуля</button>
      </div>
      ${saves.length ? `<table class="data"><thead><tr><th>Название</th><th>Когда сохранили</th><th>Участников</th><th></th></tr></thead>
      <tbody>${saves.map(s => `<tr class="${s.active ? "is-current" : ""}">
        <td>
          <b>${esc(s.name)}</b>
          ${s.active ? `<span class="badge ok">открыт</span>` : ""}
        </td>
        <td>${esc(formatWhen(s.saved_at) || "—")}</td>
        <td>${s.participants}</td>
        <td class="actions">
            ${s.active
              ? `<span class="archive-open-mark">Сейчас открыт</span>`
              : `<button class="btn sm" data-load="${esc(s.id)}" type="button">Открыть</button>`}
            <button class="btn sm danger" data-forget="${esc(s.id)}" type="button">Удалить</button>
        </td>
      </tr>`).join("")}</tbody></table>` : `<p style="color:#5c6570;margin:0">Сохранённых копий пока нет. Нажмите «Сохранить этот турнир», чтобы оставить учебный список с Excel.</p>`}
    </div>`;
  $("#save-name").value = t.name || "";
  $("#save-now").onclick = async () => {
    try {
      const r = await api("/api/saves", { method: "POST", body: { name: $("#save-name").value } });
      toast("Сохранено: " + r.name);
      await boot();
      show("archives");
    } catch (e) { toast(e.message, "err"); }
  };
  $("#new-now").onclick = async () => {
    if (!confirm("Начать с нуля? Текущий список и сетки пропадут. Справочник весов останется. Если нужно — сначала нажмите «Сохранить этот турнир».")) return;
    await api("/api/tournament/new", { method: "POST", body: {} });
    toast("Пустой турнир");
    await boot();
    show("archives");
  };
  $("#view").onclick = async (e) => {
    if (e.target.dataset.load) {
      if (!confirm("Открыть эту копию? То, что сейчас на экране, заменится. Сначала сохраните, если оно ещё нужно.")) return;
      await api("/api/saves/" + encodeURIComponent(e.target.dataset.load) + "/load", { method: "POST", body: {} });
      toast("Турнир открыт");
      await boot();
      show("archives");
    }
    if (e.target.dataset.forget && confirm("Удалить только сохранённую копию? Открытый турнир не тронется.")) {
      await api("/api/saves/" + encodeURIComponent(e.target.dataset.forget), { method: "DELETE" });
      show("archives");
    }
  };
}

const views = {
  async archives() { await renderArchives(); },
  async setup() {
    const t = state.boot.tournament;
    $("#view").innerHTML = `
      <div class="card">
        <h2>О турнире</h2>
        <div class="catalogs">
          <label class="field">Название<input id="t-name" value="${esc(t.name)}"></label>
          <label class="field">Вид спорта<input id="t-kind" value="${esc(t.kind)}"></label>
          <label class="field">Город<input id="t-city" value="${esc(t.city)}"></label>
          <label class="field">Дата<input id="t-date" type="date" value="${esc(t.date||"")}"></label>
          <label class="field">Главный судья<input id="t-ref" value="${esc(t.chief_referee)}"></label>
          <label class="field">Главный секретарь<input id="t-sec" value="${esc(t.chief_secretary)}"></label>
          <label class="field">Сколько рингов<input id="t-rings" type="number" min="1" value="${t.rings||1}"></label>
        </div>
        <button class="btn" id="t-save" type="button">Сохранить реквизиты</button>
      </div>
      <div class="card">
        <h2>Справочники</h2>
        <div class="catalogs">
          <div>
            <h3>Возрастные группы</h3>
            <div id="ages"></div>
            <div class="add-row" style="margin-top:10px"><input id="age-label" placeholder="2018-2019"><button class="btn sec" id="age-add" type="button">Добавить</button></div>
          </div>
          <div>
            <h3>Дивизионы</h3>
            <div id="divs"></div>
            <div class="add-row" style="margin-top:10px"><input id="div-code" placeholder="А"><button class="btn sec" id="div-add" type="button">Добавить</button></div>
          </div>
          <div>
            <h3>Весовые категории, кг</h3>
            <div id="wts"></div>
            <div class="add-row" style="margin-top:10px"><input id="wt-kg" placeholder="52,2"><button class="btn sec" id="wt-add" type="button">Добавить</button></div>
          </div>
        </div>
      </div>
      <div class="card">
        <h2>Очки за места</h2>
        <p class="hint-inline">Сколько очков команда получает за это место. Обычно правят только числа справа.</p>
        <div id="pts"></div>
        <button class="btn" id="pts-save" type="button">Сохранить очки</button>
      </div>`;
    $("#t-save").onclick = async () => {
      state.boot.tournament = await api("/api/tournament", { method: "PUT", body: {
        name: $("#t-name").value, kind: $("#t-kind").value, date: $("#t-date").value,
        city: $("#t-city").value, chief_referee: $("#t-ref").value, chief_secretary: $("#t-sec").value,
        rings: +$("#t-rings").value, bronze_bout: 0, two_bronzes: 1, award_walkover: 1,
      }});
      $("#brand-sub").textContent = state.boot.tournament.name;
      markClean();
      toast("Сохранено");
    };
    renderCatalogs();
    $("#age-add").onclick = async () => { await api("/api/age-groups", { method: "POST", body: { label: $("#age-label").value } }); await boot(); renderCatalogs(); markClean(); };
    $("#div-add").onclick = async () => { await api("/api/divisions", { method: "POST", body: { code: $("#div-code").value } }); await boot(); renderCatalogs(); markClean(); };
    $("#wt-add").onclick = async () => { await api("/api/weights", { method: "POST", body: { limit_kg: $("#wt-kg").value } }); await boot(); renderCatalogs(); markClean(); };
    $("#pts-save").onclick = savePoints;
  },

  async people() {
    const list = await api("/api/participants?sort=" + state.sort);
    $("#view").innerHTML = `
      <div class="people-bar">
        <div class="people-tools">
          <div class="stat"><b>${list.length}</b><span>в списке</span></div>
          <label class="search-box">
            <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
            <input id="q" placeholder="Найти по фамилии или клубу">
          </label>
          <select id="sort">
            <option value="seq">по номеру</option>
            <option value="team">команда → год → жребий</option>
            <option value="weight">по весу</option>
            <option value="year_weight">год → вес</option>
            <option value="alpha">по алфавиту</option>
            <option value="draw">по жребию</option>
          </select>
        </div>
        <div class="people-actions">
          <button class="btn" id="p-add" type="button"><svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> Добавить</button>
          <label class="btn sec"><svg viewBox="0 0 24 24"><path d="M12 15V4M8 8l4-4 4 4"/><path d="M5 20h14"/></svg> Загрузить Excel<input type="file" id="p-imp" accept=".xlsx,.xlsm,.csv" hidden></label>
          <a class="btn sec" href="/api/export/participants.xlsx"><svg viewBox="0 0 24 24"><path d="M12 4v11M8 11l4 4 4-4"/><path d="M5 20h14"/></svg> Скачать список</a>
        </div>
      </div>
      <div class="table-wrap">
        <table class="data" id="ptable">
          <thead><tr><th>№</th><th>Жребий</th><th>ФИО</th><th>Пол</th><th>Организация</th><th>Разряд</th><th>Год</th><th>Тренер</th><th>Заявл.</th><th>Факт.</th><th>Статус</th><th></th></tr></thead>
          <tbody></tbody>
        </table>
      </div>`;
    $("#sort").value = state.sort;
    $("#sort").onchange = () => { state.sort = $("#sort").value; show("people"); };
    const tbody = $("#ptable tbody");
    const draw = (items) => {
      tbody.innerHTML = items.map(p => `<tr>
        <td>${p.seq??""}</td><td><input data-draw="${p.id}" value="${p.draw_number??""}" inputmode="numeric" style="width:72px;text-align:center"></td>
        <td><b>${esc(p.name)}</b></td><td>${p.gender==="жен"?"жен":"муж"}</td><td>${esc(p.organization)}</td>
        <td>${esc(p.rank)}</td><td>${p.birth_year??""}</td><td>${esc(p.coach)}</td>
        <td>${p.declared_weight ?? "—"}</td><td>${p.weight ?? "—"}</td>
        <td><span class="badge ${statusClass(p.status)}">${esc(p.status)}</span></td>
        <td class="actions">
          <button class="btn sm sec" data-edit="${p.id}" type="button"><svg viewBox="0 0 24 24"><path d="M4 20h4l10-10-4-4L4 16v4z"/><path d="M13 7l4 4"/></svg> Изменить</button>
          <button class="btn sm danger" data-del="${p.id}" type="button"><svg viewBox="0 0 24 24"><path d="M5 7h14M10 7V5h4v2M8 7l1 12h6l1-12"/></svg> Удалить</button>
        </td>
      </tr>`).join("") || `<tr><td colspan="12">Список пуст. Добавьте человека или загрузите Excel.</td></tr>`;
    };
    draw(list);
    $("#q").oninput = () => {
      const q = $("#q").value.toLowerCase();
      draw(list.filter(p => `${p.name} ${p.organization} ${p.coach}`.toLowerCase().includes(q)));
    };
    tbody.onchange = async (e) => {
      if (!e.target.dataset.draw) return;
      try {
        await api("/api/participants/"+e.target.dataset.draw, { method:"PUT", body:{ draw_number: e.target.value } });
        markClean();
        toast("Жребий записан");
      } catch (err) { toast(err.message, "err"); }
    };
    tbody.onclick = async (e) => {
      const hit = e.target.closest("[data-del],[data-edit]");
      if (!hit) return;
      const del = hit.dataset.del, ed = hit.dataset.edit;
      if (del && confirm("Удалить участника?")) { await api("/api/participants/"+del, { method:"DELETE" }); show("people"); }
      if (ed) personForm(list.find(p => p.id == ed));
    };
    $("#p-add").onclick = () => personForm(null);
    $("#p-imp").onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      const fd = new FormData(); fd.append("file", f);
      const r = await fetch("/api/participants/import", { method:"POST", body: fd }).then(x=>x.json());
      toast(`Загружено: ${r.added}`); show("people");
    };
  },

  async weigh() {
    const list = await api("/api/participants?sort=alpha");
    const left = list.filter(p => p.weight == null).length;
    $("#view").innerHTML = `
      <div class="toolbar">
        <div class="stat"><b>${left}</b><span>ещё без фактического</span></div>
        <div class="stat"><b>${list.length - left}</b><span>уже взвешены</span></div>
      </div>
      <div class="table-wrap">
        <table class="data">
          <thead><tr><th>ФИО</th><th>Организация</th><th>Год</th><th>Заявленный, кг</th><th>Фактический, кг</th><th>Статус</th><th></th></tr></thead>
          <tbody>${list.map(p => `<tr>
            <td><b>${esc(p.name)}</b></td><td>${esc(p.organization)}</td><td>${p.birth_year??""}</td>
            <td><input data-dw="${p.id}" value="${p.declared_weight ?? ""}" inputmode="decimal" style="width:110px"></td>
            <td><input data-w="${p.id}" value="${p.weight ?? ""}" inputmode="decimal" style="width:110px"></td>
            <td><select data-st="${p.id}">
              ${["заявлен","взвешен","допущен","снят","не явился"].map(s => `<option ${s===p.status?"selected":""}>${s}</option>`).join("")}
            </select></td>
            <td class="actions"><button class="btn sm" data-save="${p.id}" type="button">Сохранить</button>
                <button class="btn sm sec" data-hist="${p.id}" type="button">История</button></td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
    $("#view").onclick = async (e) => {
      const id = e.target.dataset.save || e.target.dataset.hist;
      if (e.target.dataset.save) {
        const dw = $(`input[data-dw="${id}"]`).value;
        const w = $(`input[data-w="${id}"]`).value;
        const st = $(`select[data-st="${id}"]`).value;
        try {
          await api(`/api/participants/${id}/weigh`, {
            method: "POST",
            body: { weight: w, declared_weight: dw, status: st },
          });
          markClean();
          toast("Вес записан");
        }
        catch (err) { toast(err.message, "err"); }
      }
      if (e.target.dataset.hist) {
        const person = list.find(p => String(p.id) === String(id));
        const h = await api(`/api/participants/${id}/weights`);
        const declared = person?.declared_weight != null
          ? `<p class="hist-note">Заявленный вес: <b>${formatKg(person.declared_weight)} кг</b></p>`
          : `<p class="hist-note">Заявленный вес не указан</p>`;
        openModal(
          "История фактического веса",
          declared + (h.length
            ? `<ul class="hist-list">${h.map(x => `<li><span class="hist-when">${esc(formatWhen(x.recorded_at))}</span><span class="hist-kg">факт. ${formatKg(x.weight)} кг</span></li>`).join("")}</ul>`
            : "<p>Записей фактического веса ещё нет</p>")
        );
      }
    };
  },

  async cats() {
    const cats = await api("/api/categories");
    $("#view").innerHTML = `
      <div class="toolbar">
        <button class="btn" id="do-class" type="button">Разбить на категории</button>
        <span>После взвешивания нажмите эту кнопку. Старые сетки и результаты боёв соберутся заново.</span>
      </div>
      <div id="unplaced"></div>
      ${cats.length ? `<div class="table-wrap"><table class="data">
        <thead><tr><th>Возраст</th><th>Пол</th><th>Дивизион</th><th>Вес</th><th>Человек</th><th>Вид сетки</th><th></th></tr></thead>
        <tbody>${cats.map(c => `<tr>
          <td>${esc(c.age_label)}</td><td>${esc(c.gender_label || (c.gender==="жен"?"женщины":"мужчины"))}</td><td>${esc(c.division_code)}</td>
          <td>до ${esc(c.weight_label)} кг</td><td><b>${c.n}</b></td>
          <td>${esc(c.bracket_title || kindRu(c.bracket_kind))}</td>
          <td class="actions">
            <button class="btn sm" data-open="${c.id}" type="button">Открыть сетку</button>
            <button class="btn sm sec" data-redraw="${c.id}" type="button">Новый жребий</button>
          </td>
        </tr>`).join("")}</tbody>
      </table></div>` : `<div class="empty">Категорий ещё нет. Сначала загрузите участников и нажмите «Разбить на категории».</div>`}`;
    $("#do-class").onclick = async () => {
      if (cats.length && !confirm("Собрать категории заново? Результаты боёв сбросятся.")) return;
      const r = await api("/api/classify", { method:"POST", body:{} });
      const box = $("#unplaced");
      if (r.unplaced.length) {
        box.innerHTML = `<div class="warn-box"><b>Не удалось разместить: ${r.unplaced.length}</b><ul>${
          r.unplaced.map(u => `<li>${esc(u.participant.name)} — ${esc(u.reason)}</li>`).join("")
        }</ul></div>`;
      } else {
        toast("Категории собраны: " + r.categories.length);
        show("cats");
      }
    };
    $("#view").onclick = async (e) => {
      if (e.target.dataset.open) { state.catId = +e.target.dataset.open; show("brackets"); }
      if (e.target.dataset.redraw && confirm("Пережеребить только эту категорию?")) {
        await api(`/api/categories/${e.target.dataset.redraw}/redraw`, { method:"POST", body:{} });
        toast("Жребий обновлён");
        show("cats");
      }
    };
  },

  async brackets() {
    const cats = await api("/api/categories");
    if (!cats.length) {
      $("#view").innerHTML = `<div class="empty">Сначала откройте «Категории» и нажмите «Разбить на категории».</div>`;
      return;
    }
    if (!state.catId) state.catId = cats[0].id;
    const d = await api("/api/categories/" + state.catId);
    const title = d.category.bracket_title || kindRu(d.category.bracket_kind);
    $("#view").innerHTML = `
      <div class="toolbar">
        <select id="cat-sel" style="max-width:420px">${cats.map(c =>
          `<option value="${c.id}" ${c.id===state.catId?"selected":""}>до ${esc(c.weight_label)} кг · ${esc(c.age_label)} · ${esc(c.gender_label || "")} · ${esc(c.division_code)} · ${c.n} чел. · ${esc(c.bracket_title || kindRu(c.bracket_kind))}</option>`
        ).join("")}</select>
        <button class="btn sec" id="br-redraw" type="button">Новый жребий</button>
        <button class="btn sec" id="br-manual" type="button">Кто в сетке</button>
      </div>
      <div class="card">
        <h2>${esc(d.category.age_label)} · ${esc(d.category.gender_label || "")} · дивизион ${esc(d.category.division_code)} · до ${esc(d.category.weight_label)} кг · ${esc(title)}</h2>
        <div class="chips">${d.entries.map(e =>
          `<span class="chip"><b>${e.control_number}.</b> ${esc(e.name)} <span style="color:#5c6570">${esc(e.organization)}</span></span>`
        ).join("")}</div>
        <div class="bracket-wrap" id="br"></div>
      </div>`;
    $("#cat-sel").onchange = () => { state.catId = +$("#cat-sel").value; show("brackets"); };
    $("#br-redraw").onclick = async () => {
      if (!confirm("Пережеребить эту категорию? Результаты боёв сбросятся.")) return;
      await api(`/api/categories/${state.catId}/redraw`, { method:"POST", body:{} });
      show("brackets");
    };
    $("#br-manual").onclick = () => manualDrawForm(d);
    renderBracket($("#br"), d);
  },

  async bouts() {
    const list = await api("/api/bouts");
    $("#view").innerHTML = list.length ? `
      <div class="table-wrap"><table class="data">
        <thead><tr><th>№</th><th>Категория</th><th>Тур</th><th>Синий угол</th><th>Красный угол</th><th>Победитель</th><th>Ринг</th><th></th></tr></thead>
        <tbody>${list.map(b => `<tr>
          <td><b>${b.bout_no??""}</b></td>
          <td>до ${esc(b.weight_label)} · ${esc(b.division_code)}</td>
          <td>${esc(b.round_title || roundRu(b.round_code))}</td>
          <td class="blue">${b.blue?esc(b.blue.name):"—"}</td>
          <td class="red">${b.red?esc(b.red.name):"—"}</td>
          <td>${b.winner?esc(b.winner.name):(b.blue&&b.red?"ещё не записан":"ждём пару")}</td>
          <td><input data-ring="${b.id}" value="${b.ring??""}" style="width:64px"></td>
          <td class="actions">${b.blue&&b.red?`<button class="btn sm" data-res="${b.id}" type="button">${b.winner?"Исправить":"Записать"}</button>`:""}</td>
        </tr>`).join("")}</tbody>
      </table></div>` : `<div class="empty">Боёв нет. Сначала соберите категории.</div>`;
    $("#view").onclick = (e) => {
      if (!e.target.dataset.res) return;
      const b = list.find(x => x.id == e.target.dataset.res);
      resultForm(b, () => show("bouts"));
    };
    $$("input[data-ring]").forEach(inp => inp.onchange = async () => {
      await api(`/api/bouts/${inp.dataset.ring}/schedule`, { method:"POST", body:{ ring: inp.value? +inp.value: null }});
      markClean();
    });
  },

  async results() {
    const [places, teams, man] = await Promise.all([api("/api/placements"), api("/api/teams"), api("/api/mandate")]);
    const whead = man.weights.map(w => `<th>${esc(w)}</th>`).join("");
    $("#view").innerHTML = `
      <div class="grid two">
        <div class="card" style="padding:0;overflow:auto">
          <h2 style="padding:16px 16px 0">Личные места</h2>
          <table class="data"><thead><tr><th>Категория</th><th>Место</th><th>ФИО</th><th>Организация</th><th>Очки</th></tr></thead>
          <tbody>${places.map(p => `<tr><td>до ${esc(p.weight_label)} · ${esc(p.division_code)}</td>
            <td><b>${p.place}</b></td><td>${esc(p.name)}</td><td>${esc(p.organization)}</td><td>${p.points}</td></tr>`).join("")
            || `<tr><td colspan="5">Мест ещё нет — запишите результаты боёв.</td></tr>`}</tbody></table>
        </div>
        <div class="card" style="padding:0;overflow:auto">
          <h2 style="padding:16px 16px 0">Командный зачёт</h2>
          <table class="data"><thead><tr><th>Место</th><th>Организация</th><th>Очки</th><th>Представитель</th></tr></thead>
          <tbody>${teams.map(s => `<tr><td><b>${s.place}</b></td><td>${esc(s.organization)}</td><td>${s.points}</td>
            <td><input data-org="${esc(s.organization)}" value="${esc(s.representative)}" placeholder="ФИО"></td></tr>`).join("")
            || `<tr><td colspan="4">Пока пусто.</td></tr>`}</tbody></table>
        </div>
      </div>
      <div class="card" style="overflow:auto">
        <h2>Мандатная комиссия</h2>
        <table class="data">
          <thead><tr><th>Организация</th>${whead}<th>Итого</th></tr></thead>
          <tbody>${man.rows.map(r => `<tr><td>${esc(r.organization)}</td>${man.weights.map(w=>`<td>${r.cells[w]||""}</td>`).join("")}<td><b>${r.total}</b></td></tr>`).join("")}
          <tr><th>Итого</th>${man.weights.map(w=>`<th>${man.col_totals[w]||0}</th>`).join("")}<th>${man.grand_total}</th></tr></tbody>
        </table>
        <p style="color:#5c6570;margin:12px 0 0">${Object.entries(man.titles).map(([k,v])=>`${esc(k)}: ${v}`).join(" · ")}</p>
      </div>`;
    $$("input[data-org]").forEach(inp => inp.onchange = async () => {
      await api("/api/teams/rep", { method:"POST", body:{ organization: inp.dataset.org, representative: inp.value }});
      markClean();
    });
  },

  async docs() {
    const items = [
      ["/print/weigh-in", "Протокол взвешивания", "Список с весом и жребием"],
      ["/print/mandate", "Мандатная комиссия", "Клубы по весовым категориям"],
      ["/print/pairs", "Список пар", "Кто с кем в первом круге"],
      ["/print/corners", "Бои по углам", "Синий и красный угол, ринг"],
      ["/print/brackets", "Сетки", "Все категории"],
      ["/print/personal", "Личное первенство", "Места и очки"],
      ["/print/scorecards", "Судейские записки", "По одному листу на бой"],
      ["/print/teams", "Командный протокол", "Сумма очков клубов"],
      ["/print/medals", "Призёры", "1–3 места"],
      ["/print/certificates", "Грамоты", "Печать пачкой"],
      ["/print/report", "Итоговый отчёт", "Всё сразу"],
      ["/api/export/report.xlsx", "Файл Excel", "Мандат, команды, места"],
    ];
    $("#view").innerHTML = `
      <div class="docs">${items.map(([h,t,s]) => `<a href="${h}" target="_blank">${esc(t)}<small>${esc(s)}</small></a>`).join("")}</div>
      <p style="margin-top:16px;color:#5c6570">Резервная копия всего турнира — кнопка «Сохранить копию» слева внизу.</p>`;
  },
};

function placeLabel(from, to) {
  from = Number(from); to = Number(to);
  if (from === to) {
    if (from === 1) return "1-е место";
    if (from === 2) return "2-е место";
    if (from === 3) return "3-е место";
    return from + "-е место";
  }
  if (to >= 32) return from + "-е и ниже";
  return from + "–" + to + " места";
}

function renderCatalogs() {
  const b = state.boot;
  const chips = (items, html) => items.length
    ? `<div class="chip-list">${items.map(html).join("")}</div>`
    : `<p style="color:#5c6570;margin:0">пока нет</p>`;
  $("#ages").innerHTML = chips(b.age_groups, g =>
    `<span class="chip">${esc(g.label)} <button type="button" data-del-age="${g.id}" aria-label="Удалить">×</button></span>`);
  $("#divs").innerHTML = chips(b.divisions, d =>
    `<span class="chip">${esc(d.code)} <button type="button" data-del-div="${d.id}" aria-label="Удалить">×</button></span>`);
  $("#wts").innerHTML = chips(b.weights, w =>
    `<span class="chip">до ${esc(w.label)} <button type="button" data-del-wt="${w.id}" aria-label="Удалить">×</button></span>`);
  $("#pts").innerHTML = `<table class="data pts-table">
    <thead><tr><th>Место</th><th>Очки</th></tr></thead>
    <tbody>${b.point_rules.map((p,i) => `<tr>
      <td>${esc(placeLabel(p.place_from, p.place_to))}</td>
      <td>
        <input class="pts-num" data-pp="${i}" value="${p.points}" inputmode="numeric">
        <input type="hidden" data-pf="${i}" value="${p.place_from}">
        <input type="hidden" data-pt="${i}" value="${p.place_to}">
      </td>
    </tr>`).join("")}</tbody>
  </table>`;
  $("#ages").onclick = async (e) => { if (e.target.dataset.delAge) { await api("/api/age-groups/"+e.target.dataset.delAge,{method:"DELETE"}); await boot(); renderCatalogs(); markClean(); } };
  $("#divs").onclick = async (e) => { if (e.target.dataset.delDiv) { await api("/api/divisions/"+e.target.dataset.delDiv,{method:"DELETE"}); await boot(); renderCatalogs(); markClean(); } };
  $("#wts").onclick = async (e) => { if (e.target.dataset.delWt) { await api("/api/weights/"+e.target.dataset.delWt,{method:"DELETE"}); await boot(); renderCatalogs(); markClean(); } };
}

async function savePoints() {
  const n = state.boot.point_rules.length;
  const rules = [];
  for (let i=0;i<n;i++) rules.push({
    place_from: +$(`input[data-pf="${i}"]`).value,
    place_to: +$(`input[data-pt="${i}"]`).value,
    points: +$(`input[data-pp="${i}"]`).value,
  });
  state.boot.point_rules = await api("/api/points", { method:"PUT", body: rules });
  markClean();
  toast("Очки обновлены");
}

function foldName(s) {
  return String(s || "").replace(/ё/gi, "е").toLocaleLowerCase("ru").replace(/\s+/g, " ").trim();
}

function nameMatches(person, query) {
  const q = foldName(query);
  if (!q) return false;
  const hay = foldName(`${person.name || ""} ${person.organization || ""}`);
  return q.split(" ").every(part => hay.includes(part));
}

async function manualDrawForm(d) {
  let everyone = [];
  try { everyone = await api("/api/participants?sort=alpha"); } catch { everyone = []; }
  const whereById = new Map((d.pool || []).map(p => [p.id, p]));
  const chosen = d.entries
    .slice()
    .sort((a, b) => a.control_number - b.control_number)
    .map(e => ({
      id: e.participant_id,
      name: e.name,
      organization: e.organization || "",
      where: "",
      other_category_id: null,
    }));
  const chosenIds = () => new Set(chosen.map(p => p.id));
  const pool = [];
  const seen = chosenIds();
  for (const p of everyone) {
    if (seen.has(p.id)) continue;
    seen.add(p.id);
    const extra = whereById.get(p.id);
    pool.push({
      id: p.id,
      name: p.name,
      organization: p.organization || "",
      where: extra?.where || "не в сетке",
      status: p.status || "",
      other_category_id: extra?.other_category_id || null,
    });
  }
  for (const p of (d.pool || [])) {
    if (seen.has(p.id)) continue;
    seen.add(p.id);
    pool.push(p);
  }
  let query = "";
  let focusSearch = true;
  openModal("Кто в сетке", `<div id="roster"></div>`, "sheet");

  const personLine = (p) => `<b>${esc(p.name)}</b>${p.organization ? " · " + esc(p.organization) : ""}`;

  const paint = () => {
    const q = query.trim();
    const hits = q ? pool.filter(p => nameMatches(p, q)).slice(0, 8) : [];
    const already = q ? chosen.filter(p => nameMatches(p, q)) : [];
    let hitsHtml = "";
    if (q && hits.length) {
      hitsHtml = `<div class="roster-hits">${hits.map(p => `
          <button type="button" class="roster-hit" data-add="${p.id}">
            ${personLine(p)}
            <small>${esc(p.where || "не в сетке")}</small>
          </button>`).join("")}</div>`;
    } else if (q && already.length) {
      hitsHtml = `<div class="roster-hits"><p class="archive-empty" style="padding:10px 12px">Уже в списке ниже</p></div>`;
    } else if (q) {
      hitsHtml = `<div class="roster-hits"><p class="archive-empty" style="padding:10px 12px">В турнире такой фамилии нет</p></div>`;
    }
    $("#roster").innerHTML = `
      <label class="field roster-find">Добавить человека
        <input id="roster-q" placeholder="Фамилия" value="${esc(query)}" autocomplete="off">
        ${hitsHtml}
      </label>
      <div class="roster-list">
        ${chosen.length ? chosen.map((p, i) => `
          <div class="roster-row">
            <span class="roster-num">${i + 1}</span>
            <span class="roster-who">${personLine(p)}</span>
            <span class="roster-move">
              <button type="button" data-up="${i}" ${i ? "" : "disabled"}>выше</button>
              <button type="button" data-down="${i}" ${i < chosen.length - 1 ? "" : "disabled"}>ниже</button>
              <button type="button" data-out="${i}">убрать</button>
            </span>
          </div>`).join("") : `<p class="archive-empty" style="padding:12px">В сетке никого</p>`}
      </div>
      <div class="form-actions">
        <button class="btn sec" id="m-cancel" type="button">Отмена</button>
        <button class="btn" id="m-ok" type="button">Сохранить</button>
      </div>`;
    const qEl = $("#roster-q");
    if (focusSearch) {
      qEl.focus();
      qEl.setSelectionRange(query.length, query.length);
      focusSearch = false;
    }
    qEl.oninput = () => { query = qEl.value; focusSearch = true; paint(); };
    $("#m-cancel").onclick = closeModal;
    $("#m-ok").onclick = saveRoster;
    $("#roster").onclick = (e) => {
      const up = e.target.dataset.up;
      const down = e.target.dataset.down;
      const out = e.target.dataset.out;
      const add = e.target.closest("[data-add]");
      if (up != null && +up > 0) {
        const i = +up;
        [chosen[i - 1], chosen[i]] = [chosen[i], chosen[i - 1]];
        paint();
      }
      if (down != null && +down < chosen.length - 1) {
        const i = +down;
        [chosen[i + 1], chosen[i]] = [chosen[i], chosen[i + 1]];
        paint();
      }
      if (out != null) {
        const [p] = chosen.splice(+out, 1);
        pool.push({
          id: p.id,
          name: p.name,
          organization: p.organization,
          where: p.where || "не в сетке",
          status: p.status || "",
          other_category_id: p.other_category_id,
        });
        pool.sort((a, b) => a.name.localeCompare(b.name, "ru"));
        paint();
      }
      if (add) {
        const id = +add.dataset.add;
        const idx = pool.findIndex(p => p.id === id);
        if (idx < 0) return;
        if (chosen.length >= 64) { toast("В сетке не больше 64 человек", "err"); return; }
        chosen.push(pool.splice(idx, 1)[0]);
        query = "";
        focusSearch = true;
        paint();
      }
    };
  };

  const saveRoster = async () => {
    const moved = chosen.filter(p => p.other_category_id);
    if (moved.length) {
      const names = moved.map(p => p.name).join(", ");
      if (!confirm(`Эти люди уйдут из своих сеток и встанут сюда: ${names}`)) return;
    }
    try {
      await api(`/api/categories/${state.catId}/order`, {
        method: "POST",
        body: { participant_ids: chosen.map(p => p.id) },
      });
      closeModal();
      toast("Сетка обновлена");
      show("brackets");
    } catch (err) { toast(err.message, "err"); }
  };

  paint();
}

function bindChoice(root, initial) {
  const set = (val) => {
    root.dataset.value = val;
    $$("button[data-v]", root).forEach(b => b.classList.toggle("on", b.dataset.v === val));
  };
  root.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (b) set(b.dataset.v);
  });
  set(initial);
}

function personForm(p) {
  const v = (k, d="") => p ? (p[k] ?? d) : d;
  const gender = v("gender", "муж") === "жен" ? "жен" : "муж";
  const status = v("status", "заявлен") || "заявлен";
  const statuses = ["заявлен", "взвешен", "допущен", "снят", "не явился"];
  const title = p ? (p.seq != null ? `Участник № ${p.seq}` : "Изменить участника") : "Новый участник";
  openModal(title, `
    <div class="form-sec">
      <h4>Кто</h4>
      <label class="field">Фамилия и имя
        <input id="f-name" value="${esc(v("name"))}" autocomplete="off" placeholder="Иванов Иван">
      </label>
      <div class="grid two">
        <label class="field">Город, организация
          <input id="f-org" value="${esc(v("organization"))}" autocomplete="off" placeholder="Калининград, клуб">
        </label>
        <label class="field">Тренер
          <input id="f-coach" value="${esc(v("coach"))}" autocomplete="off">
        </label>
      </div>
    </div>
    <div class="form-sec">
      <h4>Категория</h4>
      <div class="grid two">
        <label class="field">Пол
          <div class="seg" id="f-gender">
            <button type="button" data-v="муж">Мужской</button>
            <button type="button" data-v="жен">Женский</button>
          </div>
        </label>
        <label class="field">Год рождения
          <input id="f-year" value="${esc(v("birth_year"))}" inputmode="numeric" placeholder="2008">
        </label>
      </div>
      <div class="grid two">
        <label class="field">Дивизион
          <select id="f-div">
            <option value="">не указан</option>
            ${(state.boot.divisions||[]).map(d => `<option value="${d.id}" ${String(v("division_id"))===String(d.id)?"selected":""}>${esc(d.code)}</option>`).join("")}
          </select>
        </label>
        <label class="field">Разряд
          <input id="f-rank" value="${esc(v("rank"))}" list="f-ranks" placeholder="КМС, 1, б/р" autocomplete="off">
          <datalist id="f-ranks">
            <option value="ЗМС"><option value="МСМК"><option value="МС"><option value="КМС">
            <option value="1"><option value="2"><option value="3"><option value="б/р">
          </datalist>
        </label>
      </div>
    </div>
    <div class="form-sec">
      <h4>На турнире</h4>
      <div class="grid two">
        <label class="field">Заявленный вес, кг
          <input id="f-dw" value="${esc(v("declared_weight"))}" inputmode="decimal" placeholder="65,8">
        </label>
        <label class="field">Фактический вес, кг
          <input id="f-w" value="${esc(v("weight"))}" inputmode="decimal" placeholder="после взвешивания">
        </label>
      </div>
      <label class="field">Жребий
        <input id="f-draw" value="${esc(v("draw_number"))}" inputmode="numeric" placeholder="вручную или после жеребьёвки">
      </label>
      <label class="field">Статус
        <div class="pills" id="f-status">
          ${statuses.map(s => `<button type="button" data-v="${s}">${s}</button>`).join("")}
        </div>
      </label>
    </div>
    <div class="form-actions">
      <button class="btn sec" id="f-cancel" type="button"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg> Отмена</button>
      <button class="btn" id="f-ok" type="button"><svg viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg> Сохранить</button>
    </div>
  `, "wide");
  enhanceSelects($("#modal-body"));
  bindChoice($("#f-gender"), gender);
  bindChoice($("#f-status"), status);
  const nameEl = $("#f-name");
  nameEl.focus();
  nameEl.select?.();
  const save = async () => {
    const name = nameEl.value.trim();
    if (!name) { toast("Укажите фамилию и имя", "err"); nameEl.focus(); return; }
    const body = {
      name,
      organization: $("#f-org").value,
      rank: $("#f-rank").value,
      birth_year: $("#f-year").value,
      coach: $("#f-coach").value,
      declared_weight: $("#f-dw").value,
      weight: $("#f-w").value,
      draw_number: $("#f-draw").value,
      gender: $("#f-gender").dataset.value || "муж",
      division_id: $("#f-div").value,
      status: $("#f-status").dataset.value || "заявлен",
    };
    const r = p ? await api("/api/participants/"+p.id, { method:"PUT", body }) : await api("/api/participants", { method:"POST", body });
    if (r.duplicate_warning) toast("Похожий участник уже есть", "err");
    closeModal(); show("people");
  };
  $("#f-ok").onclick = save;
  $("#f-cancel").onclick = closeModal;
  $("#modal-body").onkeydown = (e) => {
    if (e.key === "Enter" && e.target.tagName !== "TEXTAREA" && !e.target.closest(".dd")) {
      e.preventDefault();
      save();
    }
  };
}

function renderBracket(el, d) {
  const byRound = {};
  d.bouts.forEach(b => { (byRound[b.round_code] ||= []).push(b); });
  const order = ["1/32","1/16","1/8","1/4","1/2","финал"];
  let rounds = order.filter(k => byRound[k]).map(k =>
    byRound[k].slice().sort((a,b) => (a.slot||0) - (b.slot||0))
  );
  const who = (eid) => d.entries.find(e => e.id === eid);
  const nameOf = (e) => e ? `${e.control_number}. ${e.name}` : "—";
  const slotCls = (b, eid, color) => {
    const parts = [color];
    if (!eid) parts.push("empty");
    if (b && b.winner_entry_id && eid) parts.push(eid === b.winner_entry_id ? "win" : "lose");
    if (b && b.blue_entry_id && b.red_entry_id && !b.is_bye) parts.push("clickable");
    return parts.join(" ");
  };
  const slotHtml = (b, eid, color) => `
    <div class="tree-slot ${slotCls(b, eid, color)}" ${b && b.blue_entry_id && b.red_entry_id && !b.is_bye ? `data-bout="${b.id}"` : ""}>
      <span>${esc(nameOf(who(eid)))}</span>
      <span class="corner">${color==="blue"?"СИНИЙ": color==="red"?"КРАСНЫЙ":""}</span>
    </div>`;

  let columns = [];
  if (!rounds.length && d.entries.length) {
    const first = d.entries[0];
    const fake = { blue_entry_id: first.id, red_entry_id: null, winner_entry_id: first.id, is_bye: true };
    rounds = [[fake, { blue_entry_id: null, red_entry_id: null, winner_entry_id: null, is_bye: true }], [{ blue_entry_id: first.id, red_entry_id: null, winner_entry_id: first.id, is_bye: true }]];
  }
  if (rounds.length) {
    const first = rounds[0];
    columns.push({
      title: String(first.length * 2),
      html: first.map(b => `<div class="tree-pair">${slotHtml(b, b.blue_entry_id, "blue")}${slotHtml(b, b.red_entry_id, "red")}</div>`).join(""),
    });
    rounds.forEach((matches) => {
      columns.push({
        title: String(matches.length),
        html: matches.map(b => {
          const win = b.winner_entry_id || null;
          const ready = b.blue_entry_id && b.red_entry_id && !b.is_bye;
          return `<div class="tree-pair"><div class="tree-slot ${win?"win":""} ${ready?"clickable":""} ${win?"":"empty"}" ${ready?`data-bout="${b.id}"`:""}><span>${esc(nameOf(who(win)))}</span></div></div>`;
        }).join(""),
      });
    });
  }
  el.innerHTML = columns.length
    ? `<div class="tree">${columns.map(c => `<div class="tree-col"><div class="col-title">${esc(c.title)}</div><div class="tree-slots">${c.html}</div></div>`).join("")}</div>`
    : `<div class="empty">Сетка ещё не собрана</div>`;
  el.onclick = (e) => {
    const node = e.target.closest("[data-bout]");
    if (!node) return;
    const b = d.bouts.find(x => x.id == node.dataset.bout);
    if (!b || !b.blue_entry_id || !b.red_entry_id) return;
    resultForm({
      ...b,
      blue: who(b.blue_entry_id),
      red: who(b.red_entry_id),
    }, () => show("brackets"));
  };
}

boot().then(() => show("archives"));
