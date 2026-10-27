import { plural } from "../domain/demo-data.js";
export class LandingEconomyController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  economyLandingVals() {
    const st = this.store.state;

    const L = st.L;

    const hours = Math.round((L.calc * 15) / 60);

    return {
      counters: [
        ["За одну загрузку", "10", "страниц максимум"],
        ["На входе", "4", "формата файлов"],
        ["Для начала", "25", "бесплатных кредитов"],
        ["Оформление", "2", "режима на выбор"],
      ].map((c, i) => ({
        key: "k" + i,
        k: c[0],
        v: c[1],
        t: c[2],
        bg: i === 2 ? "#1F4EF5" : "#fff",
        fg: i === 2 ? "#fff" : "#0B1024",
        line: i === 3 ? "transparent" : "#EEF0F5",
      })),
      inFmts: [
        ["JPG", "image"],
        ["PNG", "image"],
        ["HEIC", "camera"],
        ["PDF", "pdf"],
      ].map(([t, n]) => ({
        key: t,
        t,
        ico: this.ports.ico(n, { noBlob: true }),
      })),
      outFmts: [
        ["Word", "word"],
        ["Excel", "excel"],
        ["PDF", "pdf"],
        ["Чистый скан", "scan"],
      ].map(([t, n]) => ({
        key: t,
        t,
        ico: this.ports.ico(n, { noBlob: true }),
      })),
      supIco: this.ports.ico("support"),
      onCalc: (e) => this.ports.setL({ calc: +e.target.value }),
      ecTypes: [
        ["text", "Обычный текст"],
        ["form", "Бланки и анкеты"],
        ["table", "Таблицы"],
      ].map(([id, t]) => {
        const on = (L.calcType || "form") === id;
        return {
          key: id,
          t,
          onClick: () => this.ports.setL({ calcType: id }),
          bg: on ? "#fff" : "transparent",
          fg: on ? "#0B1024" : "#C9D1E6",
          border: on ? "#fff" : "#323B5E",
        };
      }),
      ecRates: [150, 200, 250, 350].map((r) => {
        const on = (L.calcRate || 200) === r;
        return {
          key: "r" + r,
          t: r + " ₽/ч",
          onClick: () => this.ports.setL({ calcRate: r }),
          bg: on ? "#fff" : "transparent",
          fg: on ? "#0B1024" : "#C9D1E6",
          border: on ? "#fff" : "#323B5E",
        };
      }),
      ec: (() => {
        const F = {
          text: [6, "на странице текст"],
          form: [15, "клетки, галочки и линии"],
          table: [12, "ячейки и объединения"],
        };
        const f = F[L.calcType || "form"];
        const n = L.calc;
        const fmt = (m) => {
          const hh = Math.floor(m / 60),
            mm = Math.round(m % 60);
          return hh ? hh + " ч" + (mm ? " " + mm + " мин" : "") : mm + " мин";
        };
        const oldM = n * (2 + f[0]),
          newM = n * 1,
          save = oldM - newM;
        return {
          oldH: fmt(oldM),
          newH: fmt(newM),
          saveH: fmt(save),
          newPct: Math.max(3, Math.round((newM / oldM) * 100)) + "%",
          oldNote: "2 мин распознать + ~" + f[0] + " мин оформить — " + f[1],
          ...(() => {
            const rate = L.calcRate || 200;
            const cost = n <= 150 ? 490 : Math.round(n * 3.3);
            const gross = Math.round((save / 60) * rate);
            const net = Math.max(0, gross - cost);
            const rub = (x) => x.toLocaleString("ru-RU") + "\u00a0₽";
            return {
              netRub: rub(net),
              costLine:
                rub(gross) +
                " время сотрудника − " +
                rub(cost) +
                " Copeeq" +
                (n <= 150 ? "\u00a0(«Офис»)" : ""),
            };
          })(),
        };
      })(),
      calcHours: hours + " " + plural(hours, "час", "часа", "часов"),
      calcRub: (hours * 400).toLocaleString("ru-RU") + " ₽",
      calcCost:
        "Copeeq на этот объём: " +
        (L.calc <= 150
          ? "подписка «Офис» — 490 ₽ в месяц"
          : "от " +
            Math.round(L.calc * 3.3).toLocaleString("ru-RU") +
            " ₽ в месяц"),
    };
  }
}
