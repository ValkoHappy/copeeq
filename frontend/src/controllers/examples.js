export class ExamplesController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  examplesVals() {
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

    if (r === "examples") {
      const types = [
        "all",
        ...D.examples
          .map((x) => x.type)
          .filter((t, i, a) => a.indexOf(t) === i),
      ];
      const f =
        st.exF === "all"
          ? "all"
          : (D.examples.find((x) => x.id === st.exF) || {}).type || st.exF;
      out.exChips = types.map((t) => ({
        key: t,
        label: t === "all" ? "Все" : t,
        onClick: () => this.store.update({ exF: t }),
        ...chip(f === t),
      }));
      out.exCards = D.examples
        .filter((x) => f === "all" || x.type === f)
        .map((x) => ({
          ...x,
          key: x.id,
          onDl: () =>
            this.ports.toast(
              "Скачивание: Пример_" + x.title.replace(/\s+/g, "_") + ".docx",
              "download",
            ),
        }));
    }
    return out;
  }
}
