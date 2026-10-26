import { kr } from "../domain/demo-data.js";
export class BillingController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  billingVals() {
    const st = this.store.state;
    const D = window.CQ;
    const r = st.route;
    const out = {};
    if (r === "billing") {
      const c = st.credits;
      Object.assign(out, {
        balTotal: kr(this.ports.total()),
        buckets: [
          ["Подписочные", c.sub, st.subOn ? "до 30 ноября" : "—", "#8FB0FF"],
          ["Бесплатные", c.free, "без срока", "#16A34A"],
          ["Пакетные", c.pack, c.pack ? "до 12 окт 2027" : "—", "#1F4EF5"],
        ].map((b, i) => ({
          key: "b" + i,
          label: b[0],
          n: b[1],
          exp: b[2],
          c: b[3],
        })),
        subOn: st.subOn,
        subOff: !st.subOn,
        subChip: st.subOn
          ? { t: "Активна", bg: "#E6F6EC", fg: "#15803D" }
          : { t: "Не оформлена", bg: "#F1F0F4", fg: "#5B6478" },
        cancelSub: () => {
          this.store.update({ subOn: false });
          this.ports.toast(
            "Подписка отменена. Кредиты этого месяца остаются до 30 ноября.",
            "event_busy",
          );
        },
        buySub: () =>
          this.store.update({
            modal: "buy",
            pend: null,
            buy: {
              need: 0,
              pick: "office",
              method: "sbp",
              paying: false,
              sub: true,
            },
          }),
        buyCards: D.plans.map((p) => ({
          ...p,
          key: p.id,
          priceLabel: p.price.toLocaleString("ru-RU") + " ₽",
          creditsLabel: kr(p.credits),
          border: p.hot ? "#1F4EF5" : "transparent",
          btnBg: p.hot ? "#1F4EF5" : "#0B1024",
          btnFg: "#fff",
          onBuy: () =>
            this.store.update({
              modal: "buy",
              pend: null,
              buy: {
                need: 0,
                pick: p.id,
                method: "sbp",
                paying: false,
                sub: false,
              },
            }),
        })),
        opRows: st.ops.map((o) => ({
          key: o.id,
          text: o.text,
          when: o.when,
          pagesLabel: o.pages ? " · " + o.pages + " стр." : "",
          deltaLabel:
            o.delta > 0 ? "+" + o.delta : o.delta < 0 ? String(o.delta) : "0",
          fg: o.delta > 0 ? "#15803D" : o.delta < 0 ? "#0B1024" : "#8A90A2",
        })),
        receiptRows: st.receipts.map((x) => ({
          ...x,
          key: x.id,
          onClick: () =>
            this.ports.toast(
              "Скачивание: чек_" + x.when.replace(/\s+/g, "_") + ".pdf",
              "receipt_long",
            ),
        })),
        noReceipts: !st.receipts.length,
      });
    }
    return out;
  }

  buyModalVals() {
    const st = this.store.state;
    const D = window.CQ;
    const m = st.modal || (st.route === "login" ? "login" : null);
    const out = {};
    if (m === "buy") {
      const b = st.buy;
      const have = this.ports.total();
      const short = Math.max(0, b.need - have);
      const opts = [
        ...D.plans.map((p) => ({ ...p, sub: kr(p.credits) + " · " + p.per })),
        { ...D.sub, sub: "750 кредитов в месяц · " + D.sub.per },
      ];
      const pl = opts.find((o) => o.id === b.pick) || opts[0];
      out.mTitle = b.need
        ? "Не хватает кредитов"
        : b.pick === "office"
          ? "Подписка «Офис»"
          : "Покупка кредитов";
      out.mSub = b.need
        ? "Документ сохранён. После оплаты скачивание начнётся сразу."
        : "Кредиты появятся на балансе сразу после оплаты.";
      Object.assign(out, {
        modalW: "520px",
        buyNeed: b.need > 0,
        needBoxes: [
          ["Нужно", b.need, "#F6F5F8", "#0B1024", "#5B6478"],
          ["У вас", have, "#F6F5F8", "#0B1024", "#5B6478"],
          ["Не хватает", short, "#FFF1E8", "#C2551F", "#C2551F"],
        ].map((x, i) => ({
          key: "n" + i,
          label: x[0],
          v: x[1],
          bg: x[2],
          fg: x[3],
          lf: x[4],
        })),
        buyOpts: (b.sub ? opts.filter((o) => o.id === "office") : opts).map(
          (o) => {
            const on = o.id === b.pick;
            return {
              key: o.id,
              ico: this.ports.ico(o.id === "office" ? "tariff" : "coin", {
                bare: o.id !== "office",
              }),
              name: o.name,
              sub: o.sub,
              price:
                o.price.toLocaleString("ru-RU") +
                " ₽" +
                (o.id === "office" ? "/мес" : ""),
              fits: b.need > 0 && o.credits >= short,
              onClick: () =>
                this.store.update((s) => ({ buy: { ...s.buy, pick: o.id } })),
              border: on ? "#1F4EF5" : "#ECEAF0",
              bg: on ? "#F3F6FF" : "#fff",
              dot: on ? "6px solid #1F4EF5" : "1.5px solid #C5C2CE",
            };
          },
        ),
        payMethods: [
          ["sbp", "СБП"],
          ["card", "Карта"],
          ["sber", "SberPay"],
        ].map(([id, label]) => {
          const on = b.method === id;
          return {
            key: id,
            label,
            onClick: () =>
              this.store.update((s) => ({ buy: { ...s.buy, method: id } })),
            bg: on ? "#fff" : "transparent",
            fg: on ? "#0B1024" : "#5B6478",
            shadow: on ? "0 1px 2px rgba(11,16,36,.14)" : "none",
          };
        }),
        buyPaying: b.paying,
        payLabel: b.paying
          ? "Оплачиваем…"
          : "Оплатить " +
            pl.price.toLocaleString("ru-RU") +
            " ₽" +
            (b.need ? " и скачать" : ""),
        payNow: this.ports.payNow,
        payNote:
          "Оплата через ЮKassa, чек по 54-ФЗ придёт на почту. " +
          (pl.id === "office"
            ? "Отменить подписку можно в любой момент."
            : "Пакетные кредиты живут 12 месяцев."),
      });
    }
    return out;
  }
}
