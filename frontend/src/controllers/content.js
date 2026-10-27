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
          ? "Перенесите строки и столбцы со скана в таблицу Excel. Перед расчётами проверьте числа и объединённые ячейки. Документ также доступен в Word."
          : "Загрузите документ для переноса текста и оформления в Word. Перед сохранением можно проверить таблицы, заполнить поля и исправить распознанный текст.";
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
          "Конспекты и распечатки",
          "Перенесите записи в Word, чтобы редактировать и дополнять их.",
        ],
        [
          "school",
          "Требования вуза",
          "В учебном шаблоне заданы шрифт 14 пт, интервал 1,5 и абзац 1,25 см. Проверьте, подходят ли они для вашей работы.",
        ],
        [
          "table",
          "Таблицы и рисунки",
          "Таблицы можно редактировать. Подписи к рисункам и данные стоит сверить с оригиналом.",
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
          "Файлы остаются в браузере",
          "Выбранные файлы не отправляются на сервер распознавания. Результат показан на заранее подготовленных документах.",
        ],
        [
          "auto_delete",
          "Удаление документов",
          "Документ можно убрать из списка. Настройка срока хранения показывает будущий сценарий, автоматическое удаление сейчас не выполняется.",
        ],
        [
          "dns",
          "Без отправки на распознавание",
          "Загрузка файла запускает пример обработки в браузере. Сервер распознавания к сайту не подключён.",
        ],
        [
          "block",
          "Без обращения к моделям",
          "В этой версии нет запросов к AI-моделям и передачи документов провайдерам распознавания.",
        ],
        [
          "gavel",
          "Работа с данными",
          "Сведения об обработке файлов и работе кабинета собраны в разделе «Персональные данные».",
        ],
        [
          "draw",
          "Подпись в документе",
          "Подпись добавляется после вашего подтверждения. В этой версии она хранится в состоянии страницы и сбрасывается при перезагрузке.",
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
