export class EditorController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  ensureHistory() {
    const id = this.store.state.cur?.id;
    if (this.documentId !== id) {
      this.documentId = id;
      this.hist = [];
      this.fut = [];
      this.lastPush = 0;
    }
  }
  edOnField = (id, v) => {
    this.ensureHistory();
    const now = Date.now();
    this.hist = this.hist || [];
    this.fut = [];
    if (!this.lastPush || now - this.lastPush > 700) {
      this.hist.push(this.store.state.cur.values);
      this.lastPush = now;
    }
    this.ports.patchCur((c) => ({ values: { ...c.values, [id]: v } }));
    this.store.update({ edSaving: true });
    this.timers.clearTimeout(this.saveT);
    this.saveT = this.timers.setTimeout(
      () => this.store.update({ edSaving: false }),
      800,
    );
  };

  applyCmd() {
    const cur = this.store.state.cur;
    const m = (cur.cmd || "")
      .trim()
      .match(/^замени(?:ть)?\s+[«"]?(.+?)[»"]?\s+на\s+[«"]?(.*?)[»"]?$/i);
    if (!m) {
      this.ports.toast(
        "Введите замену в формате «замени 2024 на 2025».",
        "info",
      );
      return;
    }
    this.ports.patchCur((c) => ({ reps: [...c.reps, [m[1], m[2]]], cmd: "" }));
    this.ports.toast(
      "Заменили «" + m[1] + "» на «" + m[2] + "» во всём документе.",
      "find_replace",
    );
  }

  undo() {
    this.ensureHistory();
    if (!this.hist || !this.hist.length) {
      this.ports.toast("Пока нет изменений для отмены", "undo");
      return;
    }
    this.fut = this.fut || [];
    this.fut.push(this.store.state.cur.values);
    this.ports.patchCur({ values: this.hist.pop() });
  }

  redo() {
    this.ensureHistory();
    if (!this.fut || !this.fut.length) return;
    this.hist.push(this.store.state.cur.values);
    this.ports.patchCur({ values: this.fut.pop() });
  }
}
