import { SIGS } from "../domain/demo-data.js";
export class SignatureController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  onSigFile = (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const r = new FileReader();
    r.onload = () =>
      this.store.update({
        modal: "sig",
        sigDraft: {
          has: true,
          consent: false,
          field:
            (this.store.state.cur && this.store.state.cur.sigField) ||
            this.firstSigLine(),
          img: r.result,
        },
      });
    r.readAsDataURL(f);
  };

  sigLinesOf(cur) {
    const out = [];
    if (!cur) return out;
    cur.pages.forEach((p, i) =>
      (SIGS[p.page] || []).forEach(([id, label]) =>
        out.push({ key: id, id, label: label + ", стр. " + (i + 1), pi: i }),
      ),
    );
    return out;
  }

  firstSigLine() {
    const cur = this.store.state.cur;
    if (!cur) return "";
    for (const p of cur.pages) {
      if (SIGS[p.page]) return SIGS[p.page][0][0];
    }
    return "";
  }

  sigDown = (e) => {
    const c = this.ui.canvasRef.current;
    if (!c) return;
    c.setPointerCapture && c.setPointerCapture(e.pointerId);
    const r = c.getBoundingClientRect();
    const ctx = c.getContext("2d");
    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#1D3B97";
    ctx.beginPath();
    ctx.moveTo(
      ((e.clientX - r.left) * c.width) / r.width,
      ((e.clientY - r.top) * c.height) / r.height,
    );
    this.drawing = true;
  };

  sigMove = (e) => {
    if (!this.drawing) return;
    const c = this.ui.canvasRef.current;
    const r = c.getBoundingClientRect();
    const ctx = c.getContext("2d");
    ctx.lineTo(
      ((e.clientX - r.left) * c.width) / r.width,
      ((e.clientY - r.top) * c.height) / r.height,
    );
    ctx.stroke();
    if (!this.store.state.sigDraft.has)
      this.store.update((s) => ({ sigDraft: { ...s.sigDraft, has: true } }));
  };

  sigUp = () => {
    this.drawing = false;
  };

  sigModalVals() {
    const st = this.store.state;
    const m = st.modal || (st.route === "login" ? "login" : null);
    const out = {};
    if (m === "sig") {
      const d = st.sigDraft;
      const can = d.has && d.consent && d.field;
      out.mTitle = "Ваша подпись";
      Object.assign(out, {
        modalW: "560px",
        sigDraft: d,
        sigImg: d.img || "",
        sigDraw: !d.img,
        sigEmpty: !d.has,
        canvasRef: this.ui.canvasRef,
        sigDown: this.sigDown,
        sigMove: this.sigMove,
        sigUp: this.sigUp,
        sigClear: () => {
          const c = this.ui.canvasRef.current;
          if (c) c.getContext("2d").clearRect(0, 0, c.width, c.height);
          this.store.update((s) => ({
            sigDraft: { ...s.sigDraft, has: false, img: "" },
          }));
        },
        uploadSig: () =>
          this.ui.sigInput.current && this.ui.sigInput.current.click(),
        draftLineBtns: this.sigLinesOf(st.cur).map((l) => {
          const on = d.field === l.id;
          return {
            key: l.id,
            label: l.label,
            border: on ? "#1F4EF5" : "#ECEAF0",
            dot: on ? "5px solid #1F4EF5" : "1.5px solid #C5C2CE",
            onClick: () =>
              this.store.update((s) => ({
                sigDraft: { ...s.sigDraft, field: l.id },
              })),
          };
        }),
        toggleConsent: () =>
          this.store.update((s) => ({
            sigDraft: { ...s.sigDraft, consent: !s.sigDraft.consent },
          })),
        consentBorder: d.consent ? "#1F4EF5" : "#C5C2CE",
        consentBg: d.consent ? "#1F4EF5" : "#fff",
        consentMark: d.consent ? "check" : "",
        sigSaveOp: can ? 1 : 0.45,
        sigSave: () => {
          if (!d.has) {
            this.ports.toast("Сначала распишитесь в поле", "draw");
            return;
          }
          if (!d.consent) {
            this.ports.toast(
              "Отметьте согласие на использование подписи",
              "info",
            );
            return;
          }
          const url =
            d.img ||
            (this.ui.canvasRef.current
              ? this.ui.canvasRef.current.toDataURL("image/png")
              : "");
          const pi = this.store.state.cur.pages.findIndex((p) =>
            (SIGS[p.page] || []).some((s) => s[0] === d.field),
          );
          this.store.update({ savedSig: url, modal: null });
          this.ports.patchCur({
            sig: url,
            sigField: d.field,
            pi: pi < 0 ? this.store.state.cur.pi : pi,
            view: "word",
          });
          this.ports.toast("Подпись поставлена и сохранена в профиле", "draw");
        },
      });
    }
    return out;
  }
}
