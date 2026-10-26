import { kr } from "../domain/demo-data.js";
export class RefundController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  badModalVals() {
    const st = this.store.state;
    const m = st.modal || (st.route === "login" ? "login" : null);
    const out = {};
    if (m === "bad") {
      const cur = st.cur;
      out.mTitle = "Получилось плохо?";
      out.mSub =
        "Вернём " +
        kr(cur.cost) +
        " на баланс. Расскажите, что не так — так мы быстрее исправим.";
      Object.assign(out, {
        badReasons: [
          "Текст распознан с ошибками",
          "Таблица или поля съехали",
          "Пропала часть страницы",
          "Другое",
        ].map((t, i) => {
          const on = st.bad.reason === i;
          return {
            key: "b" + i,
            t,
            onClick: () => this.store.update({ bad: { reason: i } }),
            border: on ? "#1F4EF5" : "#ECEAF0",
            bg: on ? "#F3F6FF" : "#fff",
            dot: on ? "6px solid #1F4EF5" : "1.5px solid #C5C2CE",
          };
        }),
        refundLabel: "Вернуть " + kr(cur.cost),
        refund: () => {
          const today = new Date().toDateString();
          if (st.lastRefund === today) {
            this.store.update({ modal: null });
            this.ports.toast(
              "Автовозврат доступен раз в сутки. Напишите в поддержку — вернём вручную.",
              "support_agent",
            );
            return;
          }
          this.store.update((s) => ({
            credits: { ...s.credits, pack: s.credits.pack + cur.cost },
            cur: { ...s.cur, paid: false, refunded: true },
            lastRefund: today,
            modal: null,
          }));
          this.ports.setDoc(cur.id, { paid: false });
          this.ports.op("Возврат: " + cur.type, cur.pages.length, cur.cost);
          this.ports.toast(
            "Вернули " + kr(cur.cost) + ". Спасибо — разберём этот документ.",
            "undo",
          );
        },
      });
    }
    return out;
  }
}
