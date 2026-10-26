export class ContentController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  seoVals() {
    const st = this.store.state;
    const D = window.CQ;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };

    if (r === "seo") {
      const s = D.seo[st.param] || D.seo["foto-v-word"];
      out.seo = s;
      out.seoPage =
        st.param === "skan-v-excel"
          ? "akt"
          : st.param === "pdf-v-word"
            ? "ank2"
            : "zayav";
      out.seoLead =
        s.to === "Excel"
          ? "Сфотографируйте таблицу — получите Excel, где числа остаются числами, а объединённые ячейки — объединёнными. И Word в придачу."
          : "Не просто текст, а оформленный документ: поля, шрифты, отступы, таблицы и линии для подписи — на своих местах.";
    }
    return out;
  }

  chistovikVals() {
    const st = this.store.state;
    const D = window.CQ;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };

    if (r === "chistovik")
      out.stdCards = D.standards.map((s) => ({
        ...s,
        key: s.id,
        state: s.biz ? "Для бизнеса — по заявке" : "Доступно",
        fg: s.biz ? "#5B6478" : "#15803D",
      }));
    return out;
  }

  studentsVals() {
    const st = this.store.state;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };

    if (r === "students")
      out.stuCards = [
        [
          "menu_book",
          "Конспект → реферат",
          "Фото лекций и распечаток — в Word с заголовками и содержанием.",
        ],
        [
          "school",
          "Требования вуза",
          "Поля, шрифт 14 пт, интервал 1,5, абзац 1,25 см, нумерация — в режиме «Чистовик».",
        ],
        [
          "table",
          "Таблицы и рисунки",
          "Таблицы — редактируемые, подписи — на своих местах.",
        ],
      ].map((c, i) => ({
        key: "c" + i,
        icon: c[0],
        t: c[1],
        d: c[2],
        ico: this.ports.ico(["newdoc", "clean", "excel"][i]),
      }));
    return out;
  }

  securityVals() {
    const st = this.store.state;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };

    if (r === "security")
      out.secCards = [
        [
          "visibility_lock",
          "Видите только вы",
          "Документы доступны только владельцу аккаунта. Сотрудники не открывают файлы без вашего запроса в поддержку.",
        ],
        [
          "auto_delete",
          "Автоудаление",
          "Через 1, 7 или 30 дней — на ваш выбор в профиле. Удалить сразу — одна кнопка.",
        ],
        [
          "dns",
          "Серверы в России",
          "Храним и обрабатываем данные на территории РФ.",
        ],
        [
          "block",
          "Не обучаем модели",
          "Ваши документы не используются для обучения.",
        ],
        [
          "gavel",
          "152-ФЗ",
          "Работаем по закону о персональных данных. Подробности — в разделе «Персональные данные».",
        ],
        [
          "draw",
          "Подпись — с согласия",
          "Ставим только после вашего явного согласия, удаляется в профиле.",
        ],
      ].map((c, i) => ({
        key: "s" + i,
        icon: c[0],
        t: c[1],
        d: c[2],
        ico: this.ports.ico(
          ["profile", "trash", "docs", "settings", "security", "editor"][i],
        ),
      }));
    return out;
  }
}
