export class LandingHandwritingController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  handwritingLandingVals() {
    const st = this.store.state;
    const D = window.CQ;
    const L = st.L;

    const hdV = L.hd.d3;

    return {
      hdDot: hdV ? "#16A34A" : "#F2B200",
      hdValue: hdV || "категория В, стаж 6 лет",
      hdOpts: [
        ["Принять", "категория В, стаж 6 лет"],
        ["Исправить на «8 лет»", "категория В, стаж 8 лет"],
      ].map(([label, v], i) => {
        const on = hdV === v;
        return {
          key: "h" + i,
          label: on ? "✓ " + label : label,
          onClick: () => this.ports.setL({ hd: { d3: v } }),
          bg: on ? "#1F4EF5" : "#fff",
          fg: on ? "#fff" : "#0B1024",
          border: on ? "#1F4EF5" : "#DEDBE4",
        };
      }),
      badList: D.bad.map((b, i) => ({
        ...b,
        key: "b" + i,
        ico: this.ports.ico(["camera", "search", "editor", "image"][i]),
      })),
    };
  }
}
