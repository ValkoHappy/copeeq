import { plural, kr } from "../domain/demo-data.js";
export class DashboardController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  dashVals() {
    const st = this.store.state;
    const cur = st.cur;
    const tot = this.ports.total();
    const c = st.credits;
    const h = new Date().getHours();
    const SU = {
      ready: ["Готов", "#E6F6EC", "#15803D"],
      processing: ["Идёт", "#EEF3FF", "#1F4EF5"],
      error: ["Ошибка", "#FDECEC", "#C2272D"],
    };
    const dn = cur
      ? this.ports.doubtsOf(cur).filter((d) => !cur.resolved[d.id]).length
      : 0;
    return {
      dashHello:
        h < 12 ? "Доброе утро" : h < 18 ? "Добрый день" : "Добрый вечер",
      dashSub: st.docs.length
        ? "Документов: " + st.docs.length + " · на балансе " + kr(tot)
        : "Загрузите первый документ — посмотрите результат до оплаты.",
      dashBal: {
        label: "Баланс",
        value: kr(tot),
        note:
          (c.sub ? "Подписочные " + c.sub + " · " : "") +
          "пакетные " +
          c.pack +
          (c.free ? " · бесплатные " + c.free : ""),
        cta: "Пополнить",
        go: () => this.ports.go("billing"),
      },
      dashCur:
        cur && cur.status === "ready"
          ? {
              type: cur.type,
              page: cur.pages[0].page,
              values: cur.values,
              resolved: cur.resolved,
              meta:
                cur.pages.length +
                " стр. · " +
                (cur.paid ? "оплачен" : kr(cur.cost)) +
                (dn
                  ? " · проверить " +
                    dn +
                    " " +
                    plural(dn, "место", "места", "мест")
                  : ""),
              goResult: () => this.ports.go("result"),
              goEditor: () => this.ports.goEditor(),
            }
          : null,
      dashDocs: st.docs.slice(0, 8).map((d) => {
        const su = SU[d.status];
        return {
          key: d.id,
          type: d.type,
          page: d.page,
          variant: d.status === "error" ? "photo" : "word",
          blur: d.status === "error",
          st: su[0],
          stBg: su[1],
          stFg: su[2],
          meta: d.date + " · " + d.pages + " стр.",
          go:
            d.status === "error"
              ? () => this.ports.go("new")
              : this.ports.openDocsDoc(d),
        };
      }),
      dashEmpty: !st.docs.length,
      dashTiles: [
        ["forms", "Бланки", "Пустые формы в Word", "forms"],
        ["compare", "Примеры", "Оригинал → наш Word", "examples"],
        ["clean", "Чистовик", "Оформление по ГОСТу", "chistovik"],
        ["business", "Для бизнеса", "Счёт и свой шаблон", "business"],
      ].map((t) => ({
        key: t[3],
        ico: this.ports.ico(
          t[0] === "auto_awesome"
            ? "clean"
            : t[0] === "business"
              ? "business"
              : t[0],
        ),
        t: t[1],
        d: t[2],
        go: () => this.ports.go(t[3]),
      })),
    };
  }
}
