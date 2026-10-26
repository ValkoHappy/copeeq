import { kr } from "../domain/demo-data.js";
export class PaymentResultController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  paymentResultVals() {
    const st = this.store.state;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };

    if (out.isPayResult) {
      const ok = r === "payok";
      const back = st.cur && st.cur.status === "ready";
      out.payRes = ok
        ? {
            ico: this.ports.ico("done", { anim: true }),
            icon: "check",
            bg: "#E6F6EC",
            fg: "#15803D",
            title: "Оплата прошла",
            text:
              "Кредиты уже на балансе: " +
              kr(this.ports.total()) +
              ". Чек отправили на почту.",
            primaryLabel: back ? "Вернуться к документу" : "Загрузить документ",
            primary: () => this.ports.go(back ? "result" : "new"),
          }
        : {
            ico: this.ports.ico("error", { anim: true }),
            icon: "close",
            bg: "#FDECEC",
            fg: "#C2272D",
            title: "Оплата не прошла",
            text: "Деньги не списаны. Попробуйте другую карту или СБП — документ сохранён и ждёт вас.",
            primaryLabel: "Попробовать снова",
            primary: () =>
              this.store.update({
                modal: "buy",
                pend: null,
                buy: {
                  need: 0,
                  pick: "start",
                  method: "sbp",
                  paying: false,
                  sub: false,
                },
              }),
          };
    }
    return out;
  }
}
