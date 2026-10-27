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
          500: "Для этого объёма можно сравнить подписку «Офис» и пакеты кредитов.",
          2000: "Укажите объём, чтобы обсудить пакет кредитов и оплату по счёту.",
          5000: "Для регулярной обработки можно обсудить настройки оформления и объём пакета.",
          10000:
            "Укажите объём и задачи для обсуждения индивидуальных условий.",
        }[b.vol],
        sendBiz: () => {
          if (!/^\S+@\S+\.\S+$/.test(b.email.trim())) {
            setB({ err: true });
            this.ports.toast("Введите почту в формате name@mail.ru", "info");
            return;
          }
          setB({ sent: true });
        },
        bizRows: [
          [
            "stacked_bar_chart",
            "Объём документов",
            "Выберите примерное число страниц в месяц, чтобы подобрать условия работы.",
          ],
          [
            "receipt_long",
            "Оплата для организаций",
            "Предусмотрена оплата по счёту от 5 000 ₽ с закрывающими документами.",
          ],
          [
            "palette",
            "Свой шаблон",
            "Можно обсудить настройки для фирменного бланка, стилей и реквизитов.",
          ],
          [
            "api",
            "Интеграция через API",
            "Подключение к системе документооборота пока не доступно. Требования можно обсудить отдельно.",
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
