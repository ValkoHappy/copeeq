export class LandingEditorDemoController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  editorDemoLandingVals() {
    const st = this.store.state;

    const L = st.L;

    return {
      onDemoFio: (e) =>
        this.ports.setL({ demo: { ...L.demo, fio: e.target.value } }),
      onDemoDate: (e) =>
        this.ports.setL({ demo: { ...L.demo, date: e.target.value } }),
      demoChecks: ["основной", "дополнительный"].map((t, i) => ({
        key: "c" + i,
        t,
        mark: L.demo.checks[i] ? "✓" : "",
        onClick: () => {
          const c = L.demo.checks.slice();
          c[i] = c[i] ? 0 : 1;
          this.ports.setL({ demo: { ...L.demo, checks: c } });
        },
      })),
      demoSaved: "Сохранено",
      keep: (e) => e.preventDefault(),
      demoSigText: L.demo.sig ? "М. Соколова" : "",
      demoSigLabel: L.demo.sig ? "Убрать подпись" : "Поставить подпись",
      demoSig: () => this.ports.setL({ demo: { ...L.demo, sig: !L.demo.sig } }),
      demoShift: () => {
        const d = String(L.demo.date).replace(/(\d{4})(?!.*\d{4})/, (y) =>
          String(+y + 1),
        );
        this.ports.setL({ demo: { ...L.demo, date: d } });
        this.ports.toast("Все годы в документе сдвинуты на +1", "event_repeat");
      },
      demoDl: () => this.ports.toast("Скачивание: Заявление.docx", "download"),
      demoFeats: [
        ["edit_document", "Текст правится прямо на листе"],
        ["check_box", "Галочки ставятся кликом"],
        ["signature", "Подпись — нарисовать или загрузить"],
        ["compare", "Сверка с фото оригинала"],
        ["find_replace", "Найти и заменить"],
      ].map(([i, t]) => ({ key: i, i, t })),
    };
  }
}
