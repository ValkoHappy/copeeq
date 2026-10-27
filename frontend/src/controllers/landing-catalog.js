export class LandingCatalogController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  catalogLandingVals() {
    const st = this.store.state;
    const D = window.CQ;
    const L = st.L;

    const pick = (id) => () =>
      this.store.update({ route: "forms", param: "", formCat: id });
    return {
      outFiles: [
        [
          "DOCX",
          "#1F4EF5",
          "Word",
          "Редактируемый документ с текстом и таблицами.",
        ],
        ["XLSX", "#15803D", "Excel", "Таблицы для редактирования и расчётов."],
        ["PDF", "#C2272D", "PDF", "Для отправки и печати."],
        [
          "PDF",
          "#5B6478",
          "Чистый скан",
          "Изображение страницы для просмотра и печати.",
        ],
      ].map((f, i) => ({
        key: "f" + i,
        ext: f[0],
        bg: f[1],
        title: f[2],
        text: f[3],
        ico: this.ports.ico(["word", "excel", "pdf", "scan"][i]),
      })),
      typeTiles: D.types.map((t, i) => ({
        ...t,
        key: t.id,
        ico: this.ports.ico(
          ["templates", "forms", "word", "success", "pdf", "excel", "security"][
            i
          ] || "newdoc",
        ),
        onClick:
          t.to === "forms"
            ? pick(t.cat)
            : () => this.ports.go("examples", "", { exF: t.ex }),
      })),
      planCards: this.ports.planTiles(),
      privacy: [
        ["visibility_lock", "Без отправки файлов на распознавание"],
        ["auto_delete", "Удаление документов из списка"],
        ["dns", "Изменения сохраняются в этой вкладке"],
        ["block", "Подпись добавляется с подтверждением"],
      ].map((x, i) => ({
        key: "p" + i,
        icon: x[0],
        t: x[1],
        ico: this.ports.ico(["profile", "trash", "security", "settings"][i], {
          noBlob: true,
        }),
      })),
      lFaq: D.faq.map((q, i) => ({
        key: "q" + i,
        q: q[0],
        a: q[1],
        open: L.faq === i,
        icon: L.faq === i ? "remove" : "add",
        sh: L.faq === i ? "0 14px 34px rgba(11,16,36,.08)" : "none",
        btnBg: L.faq === i ? "#1F4EF5" : "#EEF3FF",
        btnFg: L.faq === i ? "#fff" : "#1F4EF5",
        onClick: () => this.ports.setL({ faq: L.faq === i ? -1 : i }),
      })),
    };
  }
}
