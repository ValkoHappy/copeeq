import { DOUBTS, CYCLE } from "../domain/demo-data.js";
export class DocumentsController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  patchCur(patch) {
    this.store.update((s) => ({
      cur: {
        ...s.cur,
        ...(typeof patch === "function" ? patch(s.cur) : patch),
      },
    }));
  }

  setDoc(id, patch) {
    this.store.update((s) => ({
      docs: s.docs.map((d) => (d.id === id ? { ...d, ...patch } : d)),
    }));
  }

  doubtsOf(cur) {
    if (!cur) return [];
    const out = [];
    cur.pages.forEach((p, pi) => {
      if (p.hand && !cur.hand) return;
      (DOUBTS[p.page] || []).forEach((d) => out.push({ ...d, pi }));
    });
    return out;
  }

  openDocsDoc = (d) => () => {
    if (d.status === "error") {
      this.ports.toast(
        d.reason + ". Кредиты не списаны.",
        "error",
        "Переснять",
        () => this.ports.go("new"),
      );
      return;
    }
    if (d.status === "processing") {
      this.ports.go("processing");
      return;
    }
    if (this.store.state.cur && this.store.state.cur.id === d.id) {
      this.ports.go("result");
      return;
    }
    const pages = Array.from({ length: d.pages }, (_, i) => ({
      id: d.id + i,
      page: d.pages === 1 ? d.page : CYCLE[i % 3],
      name: "стр. " + (i + 1),
      hand: false,
      blur: false,
      rot: 0,
      src: "",
    }));
    const cur = {
      ...this.ports.newDoc(d.type, pages, this.store.state.up),
      id: d.id,
      status: "ready",
      paid: !!d.paid,
      date: d.date,
    };
    this.store.update({ cur });
    this.ports.go("result");
  };

  defaultVal(id) {
    const M = {
      z_from: "Соколовой Марии Андреевны",
      z_pos: "менеджера по продажам",
      z_start: "01.04.2024",
      z_date: "28.03.2024",
      a_tel: "+7 913 555-12-40",
      a_mail: "m.sokolova@mail.ru",
      a_pos: "менеджер по продажам",
      a_go: "с 1 апреля 2024 г.",
      a_date: "28.03.2024",
    };
    return M[id] || "";
  }
}
