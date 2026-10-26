// Single-page client for the foto2word API. No build step, no dependencies.

const FIELD_NAMES = {
  date: "Дата", money: "Сумма", inn: "ИНН", passport: "Паспорт", phone: "Телефон",
  email: "E-mail", person_name: "ФИО", address: "Адрес", number: "Число",
};
const POLL_MS = 1500;

const $ = (selector) => document.querySelector(selector);
const state = { files: [], session: null, catalog: [], pending: null, previewVersion: 0 };

// ---------- helpers -------------------------------------------------------------------------

function show(screen) {
  for (const el of document.querySelectorAll(".screen")) el.hidden = el.id !== `screen-${screen}`;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) node.append(child instanceof Node ? child : String(child));
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Ошибка ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

function fail(error) {
  $("#error-text").textContent = error.message || String(error);
  show("error");
}

// ---------- upload --------------------------------------------------------------------------

function addFiles(list) {
  for (const file of list) if (file.type.startsWith("image/") || file.type === "application/pdf") state.files.push(file);
  renderThumbs();
}

function renderThumbs() {
  const thumbs = $("#thumbs");
  thumbs.replaceChildren(
    ...state.files.map((file, index) => {
      const url = URL.createObjectURL(file);
      return el("li", {},
        el("img", { src: url, alt: `Страница ${index + 1}` }),
        el("button", {
          title: "Убрать", "aria-label": "Убрать",
          onclick: () => { state.files.splice(index, 1); renderThumbs(); },
        }, "×"));
    }));
  $("#start").disabled = state.files.length === 0;
}

async function start() {
  const form = new FormData();
  for (const file of state.files) form.append("photos", file);
  form.append("review", $("#review-toggle").checked ? "true" : "false");
  show("progress");
  try {
    state.session = await api("/api/sessions", { method: "POST", body: form });
    location.hash = `s=${state.session.id}`;
    await poll();
  } catch (error) {
    fail(error);
  }
}

async function poll() {
  while (state.session.status === "analyzing") {
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    state.session = await api(`/api/sessions/${state.session.id}`);
  }
  if (state.session.status === "failed") throw new Error(state.session.error);
  state.previewVersion += 1;
  renderResult();
  show("result");
}

// ---------- result --------------------------------------------------------------------------

function renderResult() {
  const s = state.session;
  $("#type-guess").textContent =
    `Похоже, это «${s.document_type.title}» (${Math.round(s.document_type.confidence * 100)}%).`;
  const select = $("#type-select");
  select.replaceChildren(...state.catalog.map((t) =>
    el("option", { value: t.id, selected: t.id === s.chosen_type }, t.title)));

  for (const radio of document.querySelectorAll('input[name="mode"]')) {
    radio.checked = radio.value === s.mode;
  }

  $("#card-corrections").hidden = s.corrections.length === 0;
  $("#corrections").replaceChildren(...s.corrections.map((c) =>
    el("label", { class: "check change" },
      el("input", { type: "checkbox", checked: c.accepted, "data-correction": c.id, onchange: decide }),
      el("span", {}, el("del", {}, c.before), " → ", el("ins", {}, c.after || "(удалить)")))));

  $("#card-suggestions").hidden = s.suggestions.length === 0;
  $("#suggestions").replaceChildren(...s.suggestions.map((g) =>
    el("label", { class: "check change", title: g.reason },
      el("input", { type: "checkbox", checked: g.accepted, "data-suggestion": g.index, onchange: decide }),
      el("span", {}, el("del", {}, g.text), " → ", el("ins", {}, g.proposal),
        el("br"), el("small", { class: "muted" }, g.reason)))));

  const flagged = new Map(s.flags.filter((f) => f.value).map((f) => [f.value, f.message]));
  $("#card-fields").hidden = s.fields.length === 0 && s.flags.length === 0;
  $("#fields").replaceChildren(...s.fields.map((f) =>
    el("label", { class: `field-edit ${flagged.has(f.value) ? "flagged" : ""}`, title: flagged.get(f.value) || "" },
      el("span", {}, FIELD_NAMES[f.kind] || f.kind),
      el("input", { value: f.current, "data-field": f.index, "data-original": f.value, onchange: decide }))));
  $("#flags").replaceChildren(...s.flags.filter((f) => !f.value).map((f) => el("li", { class: "flagged" }, f.message)));

  $("#shift-years").value = String(s.shift_years);
  $("#date-changes").replaceChildren(...s.date_changes.map((c) =>
    el("li", { class: "change" }, el("del", {}, c.before), " → ", el("ins", {}, c.after))));

  $("#card-signature").hidden = s.signature_lines.length === 0;
  for (const radio of document.querySelectorAll('input[name="signature"]')) radio.checked = radio.value === s.signature_mode;
  $("#own-signature").hidden = s.signature_mode !== "own";
  $("#signature-lines").replaceChildren(...s.signature_lines.map((line) =>
    el("label", { class: "check" },
      el("input", { type: "checkbox", checked: s.signed_blocks.includes(line.id), "data-sign": line.id,
        disabled: !s.has_signature, onchange: decide }),
      `${line.label} ${line.name}`.trim())));
  $("#attach-scan").checked = s.attach_scan;
  $("#editable").checked = s.editable;

  $("#blocks").replaceChildren(...s.blocks.filter((b) => b.editable).map((b) =>
    el("label", { class: "block-edit" },
      el("span", {}, b.id),
      el("textarea", { "data-block": b.id }, b.text))));

  $("#download").href = `/api/sessions/${s.id}/document.docx`;
  $("#download-pdf").href = `/api/sessions/${s.id}/document.pdf`;
  $("#download-pdf").hidden = !s.pdf_available;
  $("#download-scan").href = `/api/sessions/${s.id}/scan.pdf`;
  $("#download-xlsx").href = `/api/sessions/${s.id}/tables.xlsx`;
  $("#download-xlsx").hidden = !s.has_tables;
  const parts = [s.model && `Модель: ${s.model}`, s.review_rounds != null && `самопроверка: ${s.review_rounds} раунд(а)`];
  $("#status-line").textContent = parts.filter(Boolean).join(" · ");
  renderViewer();
}

function renderViewer() {
  const s = state.session;
  const version = state.previewVersion;
  const preview = $("#viewer-preview");
  if (s.previews > 0) {
    preview.replaceChildren(...Array.from({ length: s.previews }, (_, i) =>
      el("img", { src: `/api/sessions/${s.id}/preview/${i + 1}?v=${version}`, alt: `Страница ${i + 1}` })));
  } else {
    preview.replaceChildren(sheet(s.blocks));
  }
  $("#viewer-photo").replaceChildren(...Array.from({ length: s.photos }, (_, i) =>
    el("img", { src: `/api/sessions/${s.id}/photo/${i + 1}`, alt: `Фото ${i + 1}` })));
}

// Rough HTML view of the document when the server has no word processor for real previews.
function sheet(blocks) {
  const view = el("div", { class: "sheet" });
  for (const b of blocks) {
    if (b.kind === "heading") view.append(el("p", { class: "heading" }, b.text));
    else if (b.kind === "requisites") view.append(el("div", { class: "requisites" }, b.text));
    else if (b.kind === "list_item") view.append(el("p", { class: "list" }, b.text));
    else if (b.kind === "table") view.append(el("div", { class: "table" }, b.text));
    else if (b.kind === "spacer") view.append(el("div", { class: "spacer" }));
    else if (["two_column_line", "labeled_line", "signature_line"].includes(b.kind)) {
      view.append(el("div", { class: "line" }, ...b.text.split("\t").map((t) => el("span", {}, t))));
    } else view.append(el("p", { class: "para" }, b.text));
  }
  return view;
}

function collectDecisions() {
  const s = state.session;
  const rejected = [...document.querySelectorAll("[data-correction]")]
    .filter((box) => !box.checked).map((box) => box.dataset.correction);
  const accepted = [...document.querySelectorAll("[data-suggestion]")]
    .filter((box) => box.checked).map((box) => Number(box.dataset.suggestion));
  const edits = {};
  for (const area of document.querySelectorAll("[data-block]")) {
    const original = s.blocks.find((b) => b.id === area.dataset.block);
    if (original && area.value !== original.text) edits[area.dataset.block] = area.value;
  }
  for (const id of s.edited_blocks) {
    if (!(id in edits)) edits[id] = document.querySelector(`[data-block="${id}"]`)?.value;
  }
  const fieldValues = {};
  for (const input of document.querySelectorAll("[data-field]")) {
    if (input.value !== input.dataset.original) fieldValues[input.dataset.field] = input.value;
  }
  return {
    field_values: fieldValues,
    shift_years: Number($("#shift-years").value),
    signature_mode: document.querySelector('input[name="signature"]:checked')?.value || "blank",
    signed_blocks: [...document.querySelectorAll("[data-sign]")].filter((b) => b.checked).map((b) => b.dataset.sign),
    attach_scan: $("#attach-scan").checked,
    editable: $("#editable").checked,
    document_type_id: $("#type-select").value,
    mode: document.querySelector('input[name="mode"]:checked')?.value || "faithful",
    rejected_corrections: rejected,
    accepted_suggestions: accepted,
    block_edits: Object.fromEntries(Object.entries(edits).filter(([, v]) => v != null)),
  };
}

async function decide() {
  const body = JSON.stringify(collectDecisions());
  $("#status-line").textContent = "Пересобираем документ…";
  const request = api(`/api/sessions/${state.session.id}/decisions`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body,
  });
  state.pending = request;
  try {
    const session = await request;
    if (state.pending !== request) return; // a newer decision is on its way
    state.session = session;
    state.previewVersion += 1;
    renderResult();
  } catch (error) {
    $("#status-line").textContent = error.message;
  }
}

async function instruct() {
  const text = $("#instruction").value.trim();
  if (text.length < 3) return;
  $("#instruction-result").textContent = "Вносим изменения…";
  try {
    state.session = await api(`/api/sessions/${state.session.id}/instruction`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    });
    const result = state.session.instruction_result;
    state.previewVersion += 1;
    renderResult();
    $("#instruction-result").textContent = result.applied.length
      ? `Сделано: ${result.applied.join("; ")}`
      : "Не нашли, что изменить по этой просьбе.";
    $("#instruction").value = "";
  } catch (error) {
    $("#instruction-result").textContent = error.message;
  }
}

async function restart() {
  if (state.session) api(`/api/sessions/${state.session.id}`, { method: "DELETE" }).catch(() => {});
  state.files = [];
  state.session = null;
  history.replaceState(null, "", location.pathname);
  renderThumbs();
  show("upload");
}

// Reloading the page keeps the current document: its session id lives in the URL hash.
async function resume() {
  const id = new URLSearchParams(location.hash.slice(1)).get("s");
  if (!id) return;
  try {
    state.session = await api(`/api/sessions/${id}`);
    show("progress");
    await poll();
  } catch (error) {
    console.error("Cannot resume session", error);
    history.replaceState(null, "", location.pathname);
    show("upload");
  }
}

// ---------- own signature -----------------------------------------------------------------

const pad = { drawing: false, empty: true, file: null };

function setupSignaturePad() {
  const canvas = $("#signature-pad");
  const ctx = canvas.getContext("2d");
  ctx.lineWidth = 4;
  ctx.lineCap = "round";
  ctx.strokeStyle = "#14287a";
  const point = (e) => {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) * (canvas.width / r.width), (e.clientY - r.top) * (canvas.height / r.height)];
  };
  canvas.addEventListener("pointerdown", (e) => {
    pad.drawing = true;
    pad.empty = false;
    pad.file = null;
    canvas.setPointerCapture(e.pointerId);
    ctx.beginPath();
    ctx.moveTo(...point(e));
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!pad.drawing) return;
    ctx.lineTo(...point(e));
    ctx.stroke();
  });
  canvas.addEventListener("pointerup", () => { pad.drawing = false; });
  $("#signature-clear").addEventListener("click", () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    pad.empty = true;
    pad.file = null;
  });
  $("#signature-file").addEventListener("change", (e) => { pad.file = e.target.files[0] || null; });
  $("#signature-save").addEventListener("click", saveSignature);
}

async function saveSignature() {
  if (!$("#signature-consent").checked) {
    $("#status-line").textContent = "Отметьте, что это ваша собственная подпись.";
    return;
  }
  const blob = pad.file || (pad.empty ? null : await new Promise((resolve) => $("#signature-pad").toBlob(resolve, "image/png")));
  if (!blob) {
    $("#status-line").textContent = "Нарисуйте подпись или загрузите её фото.";
    return;
  }
  const form = new FormData();
  form.append("image", blob, "signature.png");
  form.append("own_signature", "true");
  try {
    state.session = await api(`/api/sessions/${state.session.id}/signature`, { method: "POST", body: form });
    renderResult();
    $("#status-line").textContent = "Подпись сохранена. Отметьте строки, где её поставить.";
  } catch (error) {
    $("#status-line").textContent = error.message;
  }
}

// ---------- wiring --------------------------------------------------------------------------

function wire() {
  const dropzone = $("#dropzone");
  $("#file-input").addEventListener("change", (e) => addFiles(e.target.files));
  $("#camera-input").addEventListener("change", (e) => addFiles(e.target.files));
  dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter") $("#file-input").click(); });
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("over"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("over"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("over");
    addFiles(e.dataTransfer.files);
  });
  $("#start").addEventListener("click", start);
  $("#type-select").addEventListener("change", decide);
  for (const radio of document.querySelectorAll('input[name="mode"]')) radio.addEventListener("change", decide);
  $("#save-edits").addEventListener("click", decide);
  $("#shift-years").addEventListener("change", decide);
  $("#instruction-send").addEventListener("click", instruct);
  $("#attach-scan").addEventListener("change", decide);
  $("#editable").addEventListener("change", decide);
  for (const radio of document.querySelectorAll('input[name="signature"]')) radio.addEventListener("change", decide);
  setupSignaturePad();
  for (const button of document.querySelectorAll('[data-action="restart"]')) button.addEventListener("click", restart);
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      for (const t of document.querySelectorAll(".tab")) t.classList.toggle("active", t === tab);
      $("#viewer-preview").hidden = tab.dataset.tab !== "preview";
      $("#viewer-photo").hidden = tab.dataset.tab !== "photo";
    });
  }
}

wire();
window.addEventListener("hashchange", () => {
  if (!state.session || !location.hash.includes(state.session.id)) resume();
});
api("/api/catalog")
  .then((catalog) => { state.catalog = catalog; })
  .then(resume)
  .catch(fail);
