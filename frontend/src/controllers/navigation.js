import { PRIVATE } from "../domain/demo-data.js";
export class NavigationController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  go(route, param, extra) {
    if (PRIVATE.includes(route) && !this.store.state.authed) {
      this.store.update({
        modal: "login",
        pend: { route, param },
        login: {
          step: "email",
          email: this.store.state.login.email,
          code: "",
          err: "",
        },
      });
      return;
    }
    const autoSide =
      ["result", "editor"].includes(route) && window.innerWidth < 1360
        ? { side: false }
        : ["dash", "docs", "billing", "account", "new"].includes(route) &&
            !["dash", "docs", "billing", "account", "new"].includes(
              this.store.state.route,
            )
          ? { side: true }
          : {};
    this.store.update({
      route,
      param: param || "",
      modal: null,
      ...autoSide,
      ...(extra || {}),
    });
    window.scrollTo(0, 0);
  }

  closeModal = () =>
    this.store.update({
      modal: null,
      buy: { ...this.store.state.buy, paying: false },
    });

  goEditor() {
    const cur = this.store.state.cur;
    if (cur && cur.status === "ready") {
      this.store.update((s) => ({ cur: { ...s.cur, view: "edit", zoom: 0 } }));
      this.go("result");
      return;
    }
    this.ports.toast(
      "Сначала откройте документ — затем его можно править в редакторе.",
      "edit_document",
      "Мои документы",
      () => this.go("docs"),
    );
  }
}
