export class LandingFeaturesController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  featuresLandingVals() {
    const st = this.store.state;
    const D = window.CQ;
    const L = st.L;

    return {
      cmpCols: [
        {
          key: "o",
          variant: "photo",
          title: "Оригинал",
          tag: "фото бланка",
          tagBg: "#EDEBE6",
          tagFg: "#3A4156",
          bg: "#EDEBE6",
        },
        {
          key: "p",
          variant: "plain",
          title: "Текст без оформления",
          tag: "оформление нужно восстановить",
          tagBg: "#FDECEC",
          tagFg: "#C2272D",
          bg: "#fff",
        },
        {
          key: "c",
          variant: "word",
          title: "Copeeq",
          tag: "результат в Word",
          tagBg: "#E6F6EC",
          tagFg: "#15803D",
          bg: "#EEF3FF",
        },
      ],
      steps3: [
        [
          "upload",
          "Загрузите фото или PDF",
          "Можно несколько страниц сразу, с телефона — камерой.",
        ],
        [
          "tune",
          "Выберите «Копию» или «Чистовик»",
          "«Копия» сохраняет исходное оформление. «Чистовик» применяет выбранные настройки.",
        ],
        [
          "download",
          "Скачайте .docx",
          "Плюс Excel для таблиц, PDF и чистый скан.",
        ],
      ].map((s, i) => ({
        key: "s" + i,
        icon: s[0],
        t: s[1],
        d: s[2],
        num: "0" + (i + 1),
        ico: this.ports.ico(["upload", "clean", "download"][i]),
        icoW: this.ports.ico(["upload", "clean", "download"][i], {
          onDark: true,
        }),
      })),
      pres: D.preserved,
      ...(() => {
        const pi = L.pres || 0;
        const ICONS = [
          "horizontal_rule",
          "check_box",
          "table",
          "format_bold",
          "format_list_numbered",
          "shield",
        ];
        const LOSS = [
          ["линии и подписи под ними пропали", "линии и подписи на месте"],
          ["клетки и галочки пропали", "клетки и галочки на месте"],
          ["таблица рассыпалась в строки", "объединения и границы на месте"],
          ["всё одним шрифтом", "жирный, курсив, кегль — как было"],
          [
            "сноска и номер страницы ушли в текст",
            "сноска внизу, номер — полем Word",
          ],
          ["картинка потерялась", "герб на прежнем месте"],
        ];
        const P = D.preserved || [];
        return {
          presIs: [0, 1, 2, 3, 4, 5].map((i) => i === pi),
          presCur: {
            title: (P[pi] || {}).title,
            text: (P[pi] || {}).text,
            loss: LOSS[pi][0],
            ok: LOSS[pi][1],
          },
          presTabs: P.slice(0, 6).map((p, i) => {
            const on = i === pi;
            return {
              key: "pt" + i,
              title: p.title,
              icon: ICONS[i],
              onClick: () => this.ports.setL({ pres: i }),
              bg: on ? "#fff" : "transparent",
              fg: on ? "#0B1024" : "#D7DCEA",
              ic: on ? "#1F4EF5" : "#8FA0C8",
              border: "",
            };
          }),
        };
      })(),
      goChistovik: () => this.ports.go("chistovik"),
      goPricing: () => this.ports.go("pricing"),
      goSecurity: () => this.ports.go("security"),
      noop: () => {},
      stdNotes: [
        ["crop_free", "Поля 20 / 10 / 20 / 20 мм"],
        ["font_download", "Times New Roman, 14 пт"],
        ["format_line_spacing", "Интервал 1,5, абзац 1,25 см"],
        ["title", "Заголовки — стилями Word"],
        ["table", "Таблица с шапкой и итогом"],
        ["tag", "Автоматические номера страниц"],
      ].map((n, i) => ({ key: "n" + i, icon: n[0], t: n[1] })),
    };
  }
}
