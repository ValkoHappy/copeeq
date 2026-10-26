import { now, kr } from "../domain/demo-data.js";
export class WalletController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  total() {
    return this.ports.balance(this.store.state.credits);
  }

  spend(n) {
    return this.ports.chargeCredits(this.store.state.credits, n);
  }

  op(text, pages, delta, sum) {
    this.store.update((s) => ({
      ops: [
        {
          id: "o" + Date.now() + Math.random(),
          when: now(),
          text,
          pages,
          delta,
          sum,
        },
        ...s.ops,
      ],
    }));
  }

  payNow = () => {
    const st = this.store.state;
    if (st.buy.paying) return;
    this.store.update({ buy: { ...st.buy, paying: true } });
    this.timers.setTimeout(() => {
      const s = this.store.state;
      const D = window.CQ;
      const isSub = s.buy.pick === "office";
      const pl = isSub ? D.sub : D.plans.find((p) => p.id === s.buy.pick);
      const credits = { ...s.credits };
      if (isSub) credits.sub = pl.credits;
      else credits.pack += pl.credits;
      const text = isSub
        ? "Подписка «Офис», 750 кредитов"
        : "Пакет «" + pl.name + "», " + kr(pl.credits);
      this.store.update({
        credits,
        subOn: isSub ? true : s.subOn,
        buy: { ...s.buy, paying: false },
        receipts: [
          {
            id: "r" + Date.now(),
            when: "Сегодня",
            text,
            sum: pl.price.toLocaleString("ru-RU") + " ₽",
          },
          ...s.receipts,
        ],
      });
      this.op(text, 0, pl.credits, pl.price.toLocaleString("ru-RU") + " ₽");
      const p = s.pend;
      if (p && p.dl) {
        this.store.update({ modal: null });
        this.timers.setTimeout(() => this.ports.download(p.dl, true), 200);
      } else {
        this.store.update({ modal: null, pend: null });
        this.ports.go("payok");
      }
    }, 1300);
  };

  planTiles() {
    const st = this.store.state;
    const D = window.CQ;
    const list = [
      ...D.plans.map((p) => ({ ...p, kind: "pack" })),
      { ...D.sub, kind: "sub" },
    ];
    return list.map((p, i) => {
      const hot = !!p.hot,
        sub = p.kind === "sub",
        dark = sub;
      const cr = sub ? 750 : p.credits;
      const docs = Math.max(1, Math.floor(cr / 15));
      const dw = (n) => {
        const m = n % 10,
          c = n % 100;
        return m === 1 && c !== 11
          ? "документ"
          : m >= 2 && m <= 4 && (c < 10 || c >= 20)
            ? "документа"
            : "документов";
      };
      return {
        key: p.id,
        name: sub ? "Подписка «Офис»" : p.name,
        priceNum: p.price.toLocaleString("ru-RU"),
        isSub: sub,
        credits: cr,
        creditsNote: sub ? "в месяц" : "",
        docs: "≈ " + docs + " " + dw(docs) + (sub ? " в месяц" : ""),
        who: p.who,
        hasTag: hot || sub,
        tag: hot ? "Чаще выбирают" : "Для потока",
        tagBg: hot ? "#0B1024" : "#1F4EF5",
        bg: hot ? "#1F4EF5" : dark ? "#0B1024" : "transparent",
        fg: hot || dark ? "#fff" : "#0B1024",
        line: i === 0 || hot || dark ? "transparent" : "#DDE0EA",
        coin:
          hot || dark
            ? this.ports.ico("coin1", { white: true })
            : this.ports.ico("coin", { bare: true }),
        docIc: hot || dark ? "#BFD0FF" : "#1F4EF5",
        cta: sub ? "Оформить" : "Купить",
        btnBg: hot || dark ? "#fff" : "transparent",
        btnFg: "#0B1024",
        btnBorder: hot || dark ? "#fff" : "#0B1024",
        onBuy: () => {
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
            buy: { need: 0, pick: p.id, method: "sbp", paying: false, sub },
          });
        },
      };
    });
  }
}
