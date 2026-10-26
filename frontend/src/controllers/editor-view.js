import { SIGS, plural } from "../domain/demo-data.js";
export class EditorViewController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  editorVals() {
    const st = this.store.state;
    const cur = st.cur;
    if (!cur) return {};
    const w = this.ui.viewW || 700;
    const zoom = Math.max(
      0.5,
      Math.min(1.2, Math.floor(((w - 48) / 595) * 20) / 20),
    );
    const sigOn = (id) =>
      (SIGS[id] || []).some((s) => s[0] === cur.sigField) ? cur.sig : "";
    const onField = this.ports.edOnField;
    const exec = (c) => () => {
      document.execCommand(c, false, null);
    };
    const undo = this.ports.undo;
    const redo = this.ports.redo;
    const dn = this.ports
      .doubtsOf(cur)
      .filter((d) => !cur.resolved[d.id]).length;
    return {
      hasReps: cur.reps.length > 0,
      edSheets: cur.pages.map((p, i) => ({
        key: p.id,
        page: p.page,
        zoom,
        onField,
        resolved: cur.resolved,
        values: cur.values,
        shift: cur.shift,
        reps: cur.reps,
        sig: sigOn(p.page),
        noHand: p.hand && !cur.hand,
        num: cur.pages.length > 1 ? i + 1 : 0,
      })),
      keepFocus: (e) => e.preventDefault(),
      tbGroups: [
        [
          ["undo", "Отменить", undo],
          ["redo", "Повторить", redo],
        ],
        [
          ["format_bold", "Жирный", exec("bold")],
          ["format_italic", "Курсив", exec("italic")],
          ["format_underlined", "Подчёркнутый", exec("underline")],
        ],
        [
          ["format_align_left", "По левому краю", exec("justifyLeft")],
          ["format_align_center", "По центру", exec("justifyCenter")],
          ["format_align_right", "По правому краю", exec("justifyRight")],
          ["format_align_justify", "По ширине", exec("justifyFull")],
        ],
      ].map((g, gi) => ({
        key: "g" + gi,
        items: g.map(([icon, title, fn]) => ({
          key: icon,
          icon,
          title,
          onClick: fn,
        })),
      })),
      edFind: st.edFind,
      edRepl: st.edRepl,
      onEdFind: (e) => this.store.update({ edFind: e.target.value }),
      onEdRepl: (e) => this.store.update({ edRepl: e.target.value }),
      edReplaceAll: () => {
        const a = st.edFind.trim();
        if (!a) {
          this.ports.toast("Впишите, что найти", "search");
          return;
        }
        this.ports.patchCur((c) => ({ reps: [...c.reps, [a, st.edRepl]] }));
        this.store.update({ edFind: "", edRepl: "" });
        this.ports.toast(
          "Заменили «" + a + "» во всём документе",
          "find_replace",
        );
      },
      edSave: st.edSaving
        ? { t: "Сохраняем…", icon: "sync", fg: "#5B6478" }
        : { t: "Все изменения сохранены", icon: "cloud_done", fg: "#15803D" },
      edOpenDoubts: dn
        ? "Не проверено " + dn + " " + plural(dn, "место", "места", "мест")
        : "",
      goResultCheck: () => {
        this.ports.patchCur({ tab: "check" });
        this.ports.go("result");
      },
      edSig: () =>
        this.store.update({
          modal: "sig",
          sigDraft: {
            has: false,
            consent: false,
            field: cur.sigField || this.ports.firstSigLine(),
          },
        }),
      edSigLabel: cur.sig ? "Заменить подпись" : "Поставить подпись",
    };
  }
}
