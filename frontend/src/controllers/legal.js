export class LegalController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  legalVals() {
    const st = this.store.state;
    const D = window.CQ;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };
    const chip = (on) => ({
      bg: on ? "#0B1024" : "#fff",
      fg: on ? "#fff" : "#0B1024",
      border: on ? "#0B1024" : "#DEDBE4",
    });

    if (r === "legal") {
      const k = D.legal[st.param] ? st.param : "offer";
      const L = D.legal[k];
      out.legal = L;
      out.legalSecs = L.sec.map((s, i) => ({ key: "s" + i, t: s[0], d: s[1] }));
      out.legalTabs = [
        ["offer", "Оферта"],
        ["privacy", "Персональные данные"],
        ["contacts", "Контакты и реквизиты"],
      ].map(([id, label]) => ({
        key: id,
        label,
        onClick: () => this.ports.go("legal", id),
        ...chip(k === id),
      }));
    }
    return out;
  }
}
