export class DocumentFactory {
  constructor(ports) {
    this.ports = ports;
  }
  samplePages(sm) {
    return sm.pages.map((x, i) => ({
      id: "p" + Date.now() + i + Math.random(),
      page: x[0],
      name: x[1],
      hand: !!x[2],
      blur: !!x[3],
      rot: 0,
      src: "",
    }));
  }

  newDoc(type, pages, up) {
    return {
      id: "c" + Date.now(),
      type,
      page: pages[0] ? pages[0].page : "ank1",
      pages: pages.map((p) => ({ ...p })),
      cost: this.ports.costOf(pages, up),
      mode: up.mode,
      std: up.std,
      fill: up.fill,
      hand: up.hand,
      check: up.check,
      paid: false,
      dlAt: 0,
      refunded: false,
      resolved: {},
      values: {},
      shift: 0,
      reps: [],
      sig: "",
      sigField: "",
      view: "edit",
      pi: 0,
      hl: "",
      tab: "check",
      cmd: "",
      zoom: 0,
      date: "Сегодня",
      status: "processing",
      attach: false,
      user: pages.some((p) => p.src),
    };
  }
}
