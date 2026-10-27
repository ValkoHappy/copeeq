import { FREE, kr } from "../domain/demo-data.js";
export class PricingController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  pricingVals() {
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
    if (r === "pricing") {
      const cards = [
        ...D.plans.map((p) => ({ ...p, kind: "pack" })),
        { ...D.sub, kind: "sub" },
      ];
      out.planCards = this.ports.planTiles();
      out.priceCards = [
        {
          id: "free",
          name: "Бесплатно",
          price: 0,
          credits: FREE,
          per: "один раз после регистрации",
          who: "Попробовать на своём документе",
          kind: "free",
        },
        ...cards,
      ].map((p) => {
        const hot = p.hot;
        const dark = p.kind === "sub";
        return {
          key: p.id,
          ico: this.ports.ico(
            p.kind === "free"
              ? "credits"
              : p.kind === "sub"
                ? "tariff"
                : "coin",
            p.kind === "pack"
              ? { bare: true }
              : hot || dark
                ? { noBlob: true }
                : {},
          ),
          name: p.name,
          priceLabel: p.price
            ? p.price.toLocaleString("ru-RU") + " ₽" + (dark ? "/мес" : "")
            : "0 ₽",
          creditsLabel:
            p.kind === "free"
              ? "5 страниц"
              : dark
                ? "750 кредитов в месяц"
                : kr(p.credits),
          per: p.per,
          who: p.who,
          tag: hot ? "Стандарт" : dark ? "Для регулярной работы" : "",
          tagBg: hot ? "#fff" : "#1F4EF5",
          tagFg: hot ? "#1F4EF5" : "#fff",
          bg: hot ? "#1F4EF5" : dark ? "#0B1024" : "#fff",
          fg: hot || dark ? "#fff" : "#0B1024",
          cta: p.kind === "free" ? "Попробовать" : dark ? "Оформить" : "Купить",
          btnBg: hot || dark ? "#fff" : "#0B1024",
          btnFg: hot || dark ? "#0B1024" : "#fff",
          btnBorder: "none",
          onClick:
            p.kind === "free"
              ? () => this.ports.go("new")
              : () => {
                  if (!st.authed) {
                    this.store.update({
                      modal: "login",
                      pend: { route: "billing" },
                      login: { step: "email", email: "", code: "", err: "" },
                    });
                    return;
                  }
                  this.store.update({
                    modal: "buy",
                    pend: null,
                    buy: {
                      need: 0,
                      pick: p.id,
                      method: "sbp",
                      paying: false,
                      sub: dark,
                    },
                  });
                },
        };
      });
      out.opsRows = D.ops.map((o, i) => ({
        key: "o" + i,
        t: o[0],
        n: o[1],
        bg: o[1] === "0" ? "#E6F6EC" : "#EEF3FF",
        fg: o[1] === "0" ? "#15803D" : "#1F4EF5",
      }));
      out.priceCalc = st.priceCalc;
      out.onPriceCalc = (e) =>
        this.store.update({ priceCalc: +e.target.value });
      const n = st.priceCalc;
      const best =
        n > 100
          ? {
              name: "Подписка «Офис»",
              note:
                "490 ₽ в месяц за ≈ 150 страниц" +
                (n > 150
                  ? " + пакет «" +
                    (n - 150 > 50 ? "Большой" : "Стандарт") +
                    "» на остаток"
                  : "") +
                ".",
            }
          : n > 10
            ? {
                name: "Пакет «" + (n > 50 ? "Большой" : "Стандарт") + "»",
                note:
                  "Кредиты действуют 12 месяцев — хватит на " +
                  Math.floor(((n > 50 ? 200 : 50) / n) * 10) / 10 +
                  " мес.",
              }
            : {
                name: "Пакет «Старт»",
                note: "99 ₽ за 100 кредитов — ≈ 20 страниц.",
              };
      out.calcBest = best;
      out.payFaqRows = faqRows(D.payFaq, "p");
    }
    return out;
  }
}
