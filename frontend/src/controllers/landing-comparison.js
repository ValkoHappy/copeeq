export class LandingComparisonController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  comparisonLandingVals() {
    const st = this.store.state;
    const D = window.CQ;
    const L = st.L;
    const tab = D.tabs.find((t) => t.id === L.tab) || D.tabs[0];

    return {
      lTabs: D.tabs.map((t) => {
        const on = t.id === tab.id;
        const ic =
          {
            zayav: "contract_edit",
            ank: "check_box",
            table: "table_chart",
            complex: "view_quilt",
            hand: "draw",
          }[t.id] || "description";
        return {
          key: t.id,
          label: t.label,
          icon: ic,
          onClick: () => this.ports.setL({ tab: t.id }),
          bg: on ? "#fff" : "rgba(255,255,255,.14)",
          fg: on ? "#0B1024" : "#fff",
          hoverBg: on ? "#fff" : "rgba(255,255,255,.24)",
          icBg: on ? "#EEF2FF" : "rgba(255,255,255,.16)",
          icFg: on ? "#1F4EF5" : "#fff",
        };
      }),
      how: (() => {
        const EX = {
          zayav: [
            "Заявление",
            "Заявление с блоком адресата и строками для даты и подписи.",
            false,
          ],
          ank1: [
            "Анкета",
            "Анкета с клетками для букв и полями для отметок.",
            false,
          ],
          akt: [
            "Акт",
            "Акт с таблицей в Word и отдельной таблицей Excel.",
            true,
          ],
        };
        const ex = EX[L.hx] || EX.zayav;
        const hf = L.hf;
        const n = 1 + ["excel", "pdf", "scan"].filter((k) => hf[k]).length;
        const chist = L.hm === "clean";
        return {
          page: L.hx,
          wordVariant: chist && L.hx === "akt" ? "word" : "word",
          mainLabel: chist ? "Word · чистовик" : "Word · копия",
          note: ex[1],
          cost:
            n === 1
              ? "Только Word · от 5 кредитов за страницу"
              : "Файлов: " +
                n +
                " · от 5 кредитов за страницу, все форматы включены",
          modes: [
            ["copy", "Копия"],
            ["clean", "Чистовик"],
          ].map(([id, t]) => {
            const on = L.hm === id;
            return {
              key: id,
              t,
              onClick: () => this.ports.setL({ hm: id }),
              bg: on ? "#1F4EF5" : "#fff",
              fg: on ? "#fff" : "#0B1024",
              border: on ? "#1F4EF5" : "#DCE2EE",
            };
          }),
          fmts: [
            ["word", "Word"],
            ["excel", "Excel"],
            ["pdf", "PDF"],
            ["scan", "Чистый скан"],
          ].map(([id, t]) => {
            const lock = id === "word";
            const on = lock || !!hf[id];
            return {
              key: id,
              t,
              on,
              cur: lock ? "default" : "pointer",
              bs: on ? "solid" : "dashed",
              onClick: lock
                ? () => {}
                : () => this.ports.setL({ hf: { ...hf, [id]: !hf[id] } }),
              bg: on ? (lock ? "#0B1024" : "#EEF3FF") : "#fff",
              fg: on ? (lock ? "#fff" : "#1F4EF5") : "#4A5368",
              border: on ? (lock ? "#0B1024" : "#1F4EF5") : "#C9D1E3",
            };
          }),
          tiles: [
            ["word", "Word", "DOCX", "#1F4EF5", "word"],
            ["excel", "Excel", "XLSX", "#15803D", ""],
            ["pdf", "PDF", "PDF", "#D93A3A", "word"],
            ["scan", "Чистый скан", "JPG", "#5B6478", "photo"],
          ].map(([id, label, tag, c, variant]) => {
            const on = id === "word" || !!hf[id];
            return {
              key: id,
              label,
              tag,
              tagBg: c,
              variant,
              isSheet: !!variant,
              isXls: !variant,
              op: on ? 1 : 0.28,
              ring: on ? c : "transparent",
            };
          }),
          exs: Object.keys(EX).map((id) => {
            const on = L.hx === id;
            return {
              key: id,
              t: EX[id][0],
              onClick: () => this.ports.setL({ hx: id }),
              bg: on ? "#1F4EF5" : "transparent",
              fg: on ? "#fff" : "#C9D1E6",
            };
          }),
        };
      })(),
      xlsCells: Array.from({ length: 28 }, (_, i) => ({
        key: "x" + i,
        bg: i < 4 ? "#D7EEDF" : i % 4 === 0 ? "#F1F8F3" : "#fff",
      })),
      lMeta: (() => {
        const M = {
          zayav: [
            "IMG_2041.jpg",
            "Заявление.docx",
            "1",
            "9 сек",
            "5",
            "печатный",
          ],
          ank: [
            "scan_anketa.pdf",
            "Анкета.docx",
            "2",
            "18 сек",
            "10",
            "печатный",
          ],
          table: [
            "IMG_3317.heic",
            "Таблица.docx + .xlsx",
            "1",
            "12 сек",
            "5",
            "печатный",
          ],
          complex: [
            "blank_scan.pdf",
            "Бланк.docx",
            "2",
            "21 сек",
            "10",
            "печатный",
          ],
          hand: [
            "IMG_2098.jpg",
            "Анкета.docx",
            "1",
            "14 сек",
            "10",
            "рукописный",
          ],
        };
        const m = M[tab.id] || M.zayav;
        return {
          from: m[0],
          to: m[1],
          stats: [
            { key: "p", v: m[2], l: m[2] === "1" ? "страница" : "страницы" },
            { key: "t", v: m[3], l: "в примере" },
            {
              key: "c",
              v: m[4],
              l:
                m[5] === "рукописный"
                  ? "кредитов · от руки"
                  : m[4] === "1"
                    ? "кредит"
                    : "кредитов",
            },
          ],
        };
      })(),
      lCopy: (() => {
        const C = {
          zayav: [
            "Заявления и письма",
            "Заявление с полями для заполнения",
            "В примере сохранены блок адресата, строки для даты и подписи. Заполните свои данные и проверьте документ перед печатью.",
            [
              "Линии с подписями под ними",
              "Шапка «кому / от кого» справа",
              "Абзацные отступы как в оригинале",
              "Рукописные записи в печатном виде",
            ],
            "Сделать своё заявление",
          ],
          ank: [
            "Анкеты и бланки",
            "Анкета с редактируемыми полями",
            "Буквы размещаются в отдельных клетках, ответы отмечаются галочками. Поля анкеты можно заполнить в редакторе или в Word.",
            [
              "Клетки по одной букве",
              "Галочки нажимаются в Word",
              "Варианты ответа в одну строку",
              "Поля на нескольких страницах",
            ],
            "Перевести свою анкету",
          ],
          table: [
            "Таблицы и ведомости",
            "Одна таблица в Word и Excel",
            "В примере показаны заголовки, объединённые ячейки и строка итогов. Версия для Excel позволяет работать с данными в таблице.",
            [
              "Объединённые ячейки сохранены",
              "Числовые значения в ячейках",
              "Excel-файл вместе с Word",
              "Шапка повторяется на страницах",
            ],
            "Загрузить свою таблицу",
          ],
          complex: [
            "Сложные бланки",
            "Бланк с таблицами и отметками",
            "Посмотрите, как в Word размещены несколько таблиц, даты, поля для отметок и подписи. Сравните результат с фотографией.",
            [
              "Вложенные таблицы",
              "Периоды «с / по» в ячейках",
              "Галочки рядом с текстом",
              "Поля и отступы как в оригинале",
            ],
            "Попробовать свой бланк",
          ],
          hand: [
            "Рукописный текст",
            "Записи от руки в полях документа",
            "Рукописные записи перенесены в печатный текст. Подсвеченные слова нужно сверить с фотографией и при необходимости исправить.",
            [
              "Почерк → печатный текст",
              "Слова для проверки подсвечены",
              "Подпись остаётся картинкой",
              "Даты и номера распознаются",
            ],
            "Распознать свой почерк",
          ],
        };
        const c = C[tab.id] || C.zayav;
        return {
          kicker: c[0],
          title: c[1],
          text: c[2],
          points: c[3].map((t, i) => ({ key: "p" + i, t })),
          cta: c[4],
        };
      })(),
      lTab: tab,
      L,
      sliderPct: L.slider + "%",
      onSlider: (e) => this.ports.setL({ slider: +e.target.value }),
      dlSampleWord: () =>
        this.ports.toast(
          "Скачивание: Пример_" + tab.label.replace(/\s+/g, "_") + ".docx",
          "download",
        ),
      dlSampleXlsx: () =>
        this.ports.toast(
          "Пример таблицы Excel. Скачивание в этой версии не подключено.",
          "table_view",
        ),
    };
  }
}
