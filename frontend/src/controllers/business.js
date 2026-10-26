export class BusinessController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  businessVals() {
    const st = this.store.state;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };

    if (r === "business") {
      const b = st.biz;
      const setB = (p) =>
        this.store.update((s) => ({ biz: { ...s.biz, ...p } }));
      Object.assign(out, {
        biz: b,
        bizSent: b.sent,
        bizForm: !b.sent,
        bizEmailBorder: b.err ? "#DC3B45" : "#E3E1EA",
        onBizName: (e) => setB({ name: e.target.value }),
        onBizEmail: (e) => setB({ email: e.target.value, err: false }),
        onBizVol: (e) => setB({ vol: e.target.value }),
        bizHint: {
          500: "Ориентир: подписка «Офис» или пакеты, от 3,3 ₽ за страницу.",
          2000: "Ориентир: от 3 ₽ за страницу, счёт на юрлицо.",
          5000: "Ориентир: от 4,5 ₽ за страницу, свой шаблон оформления.",
          10000: "Индивидуальные условия и API — обсудим.",
        }[b.vol],
        sendBiz: () => {
          if (!/^\S+@\S+\.\S+$/.test(b.email.trim())) {
            setB({ err: true });
            this.ports.toast("Укажите почту — ответим на неё", "info");
            return;
          }
          setB({ sent: true });
        },
        bizRows: [
          [
            "stacked_bar_chart",
            "Объёмы и скидки",
            "Чем больше страниц, тем ниже цена. Ориентиры — прямо в форме.",
          ],
          [
            "receipt_long",
            "Счёт на юрлицо",
            "От 5 000 ₽, с закрывающими документами.",
          ],
          [
            "palette",
            "Свой шаблон",
            "Фирменный бланк, стили и реквизиты — «Чистовик» под вашу компанию.",
          ],
          [
            "api",
            "API — позже",
            "Подключение к вашим системам документооборота.",
          ],
        ].map((x, i) => ({
          key: "b" + i,
          icon: x[0],
          t: x[1],
          d: x[2],
          ico: this.ports.ico(["pages", "topup", "clean", "convert"][i]),
        })),
      });
    }
    return out;
  }
}
