export class FaqController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  faqVals() {
    const st = this.store.state;
    const D = window.CQ;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };

    const faqRows = (list, key) =>
      list.map((q, i) => ({
        key: key + i,
        q: q[0],
        a: q[1],
        open: st.faqOpen === key + i,
        icon: st.faqOpen === key + i ? "remove" : "add",
        onClick: () =>
          this.store.update((s) => ({
            faqOpen: s.faqOpen === key + i ? -1 : key + i,
          })),
      }));
    if (r === "faq")
      out.allFaq = faqRows([...D.faq, ...D.payFaq.slice(1)], "f");
    return out;
  }
}
