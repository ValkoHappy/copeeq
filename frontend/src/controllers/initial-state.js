import { SAMPLES, PRIVATE } from "../domain/demo-data.js";
export class InitialStateController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  makeState(p) {
    const start = p.startScreen || "landing";
    const authed = !!p.signedIn || PRIVATE.includes(start);
    const D = window.CQ || {};
    const s = {
      route: start,
      param:
        start === "seo"
          ? "foto-v-word"
          : start === "legal"
            ? "offer"
            : start === "form"
              ? "zayavlenie-o-prieme"
              : "",
      authed,
      email: authed ? "m.sokolova@mail.ru" : "",
      everAuthed: authed,
      credits: authed
        ? { free: 1, sub: 0, pack: p.balance != null ? +p.balance : 10 }
        : { free: 0, sub: 0, pack: 0 },
      subOn: false,
      docs: authed ? (D.initialDocs || []).map((d) => ({ ...d })) : [],
      ops: authed ? (D.initialOps || []).map((o) => ({ ...o })) : [],
      receipts: authed
        ? [
            {
              id: "r1",
              when: "12 окт 2026",
              text: "Пакет «Старт», 100 кредитов",
              sum: "99 ₽",
            },
          ]
        : [],
      up: {
        pages: [],
        pdf: null,
        mode: "copy",
        std: "gost",
        fill: true,
        hand: true,
        check: true,
        drag: -1,
        over: false,
      },
      proc: { t0: 0, t: 0, err: null, done: false },
      cur: null,
      modal: null,
      pend: null,
      login: { step: "email", email: "", code: "", err: "" },
      buy: { need: 0, pick: "start", method: "sbp", paying: false, sub: false },
      sigDraft: { has: false, consent: false, field: "" },
      savedSig: "",
      bad: { reason: 0 },
      lastRefund: "",
      delId: null,
      L: {
        tab: "zayav",
        slider: 52,
        calc: 120,
        faq: 0,
        demo: {
          fio: "Соколова Мария Андреевна",
          date: "28.03.2024",
          checks: [0, 1],
        },
        hd: {},
        hx: "zayav",
        hm: "copy",
        hf: { excel: false, pdf: true, scan: false },
      },
      priceCalc: 60,
      exF: "all",
      formCat: "all",
      formQ: "",
      docsQ: "",
      faqOpen: 0,
      biz: { name: "", email: "", vol: "500", sent: false },
      prefs: { mode: "copy", std: "gost", keep: 30 },
      toast: null,
      bal: { n: 0, d: 0 },
      side: true,
      edFind: "",
      edRepl: "",
      edSaving: false,
    };
    if (["processing", "result", "editor"].includes(start)) {
      s.up.pages = this.ports.samplePages(SAMPLES[0]);
      s.cur = this.ports.newDoc(SAMPLES[0].type, s.up.pages, s.up);
      if (start !== "processing") {
        s.cur.status = "ready";
      }
    }
    return s;
  }
}
