import { plural } from "../domain/demo-data.js";
export class ReviewPanelController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  secVals(cur, doubts, open, fields, sigLines, hasTables) {
    const so = cur.secs || {
      check: open.length > 0,
      edit: !open.length,
      sig: false,
    };
    const tog = (k) => () =>
      this.ports.patchCur((c) => {
        const s = c.secs || so;
        return { secs: { ...s, [k]: !s[k] } };
      });
    const mk = (k, ico, status, fg) => ({
      open: !!so[k],
      toggle: tog(k),
      ico: this.ports.ico(ico, { noBlob: true }),
      status,
      fg,
      chev: so[k] ? "expand_less" : "expand_more",
    });
    const edits =
      Object.keys(cur.values).length + cur.reps.length + (cur.shift ? 1 : 0);
    const view = cur.view;
    const q = (id, label, ico, on, fn) => ({
      key: id,
      label,
      ico: this.ports.ico(ico, { noBlob: true }),
      onClick: fn,
      border: on ? "#1F4EF5" : "#ECEAF0",
      bg: on ? "#F3F6FF" : "#fff",
    });
    return {
      sCheck: mk(
        "check",
        open.length ? "pending" : "success",
        open.length
          ? "Проверить: " +
              open.length +
              " " +
              plural(open.length, "место", "места", "мест")
          : doubts.length
            ? "Все места проверены"
            : "Сомнительных мест нет",
        open.length ? "#B76E00" : "#15803D",
      ),
      sEdit: mk(
        "edit",
        "editor",
        edits ? "Изменений: " + edits : "Поля, замены, годы, режим",
        edits ? "#1F4EF5" : "#8A90A2",
      ),
      sSig: mk(
        "sig",
        "profile",
        cur.sig
          ? "Подпись поставлена"
          : sigLines.length
            ? "Можно поставить подпись"
            : "Нет линии для подписи",
        cur.sig ? "#15803D" : "#8A90A2",
      ),
      quick: [
        q(
          "photo",
          view === "both" ? "Скрыть фото" : "Показать фото",
          "image",
          view === "both",
          () =>
            this.ports.patchCur({
              view: view === "both" ? "edit" : "both",
              zoom: 0,
            }),
        ),
        q("find", "Найти", "search", false, () => {
          const el = document.querySelector('input[placeholder="Найти"]');
          if (el) el.focus();
        }),
        q("sig", cur.sig ? "Подпись ✓" : "Подпись", "success", !!cur.sig, () =>
          sigLines.length
            ? this.store.update({
                modal: "sig",
                sigDraft: {
                  has: false,
                  consent: false,
                  field: cur.sigField || sigLines[0].id,
                },
              })
            : this.ports.toast(
                "В этом документе нет линии для подписи",
                "info",
              ),
        ),
        hasTables
          ? q("xlsx", "Excel", "excel", false, () =>
              this.ports.download("xlsx"),
            )
          : q("pdf", "PDF", "pdf", false, () => this.ports.download("pdf")),
      ],
    };
  }
}
