import { SAMPLES, CYCLE, plural, kr, tg } from "../domain/demo-data.js";
export class UploadController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  pickFile = () => {
    if (this.ports.needAuth({ route: "new", pick: true })) return;
    if (this.ui.fileInput.current) this.ui.fileInput.current.click();
  };

  addFiles(files) {
    const st = this.store.state;
    const pages = st.up.pages.slice();
    let pdf = st.up.pdf;
    let bad = 0;
    Array.from(files || []).forEach((f) => {
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      if (ext === "pdf") {
        pdf = { name: f.name, total: 6, from: 1, to: 3 };
        return;
      }
      if (
        !["jpg", "jpeg", "png", "heic"].includes(ext) &&
        !(f.type || "").startsWith("image/")
      ) {
        bad++;
        return;
      }
      if (pages.length >= 10) {
        bad++;
        return;
      }
      const src = ext === "heic" ? "" : URL.createObjectURL(f);
      pages.push({
        id: "p" + Date.now() + Math.random(),
        page: CYCLE[pages.length % CYCLE.length],
        name: f.name || "Вставка из буфера.png",
        hand: false,
        blur: false,
        rot: 0,
        src,
      });
    });
    this.store.update({ up: { ...st.up, pages, pdf } });
    if (bad)
      this.ports.toast(
        "Подходят JPG, PNG, HEIC и PDF — до 10 страниц за раз.",
        "info",
      );
    if (st.route !== "new") this.ports.go("new");
  }

  onFile = (e) => {
    const f = e.target.files;
    this.addFiles(f);
    e.target.value = "";
  };

  handlePaste(e) {
    if (!["new", "landing", "seo", "notfound"].includes(this.store.state.route))
      return;
    const items = Array.from(
      (e.clipboardData && e.clipboardData.items) || [],
    ).filter((i) => i.type.startsWith("image/"));
    if (!items.length) return;
    this.addFiles(items.map((i) => i.getAsFile()).filter(Boolean));
    this.ports.toast("Картинка вставлена из буфера", "content_paste");
  }

  useSample = (sm) => () => {
    if (!this.store.state.authed) {
      this.store.update((s) => ({
        up: {
          ...s.up,
          pages: this.ports.samplePages(sm),
          pdf: null,
          sample: sm.id,
        },
      }));
      this.ports.needAuth({ route: "new" });
      return;
    }
    this.store.update((s) => ({
      up: {
        ...s.up,
        pages: this.ports.samplePages(sm),
        pdf: null,
        sample: sm.id,
      },
    }));
    if (this.store.state.route !== "new") this.ports.go("new");
  };

  allPages() {
    const up = this.store.state.up;
    const out = up.pages.slice();
    if (up.pdf)
      for (let n = up.pdf.from; n <= up.pdf.to; n++)
        out.push({
          id: "pdf" + n,
          page: CYCLE[(n - 1) % CYCLE.length],
          name: up.pdf.name + ", стр. " + n,
          hand: false,
          blur: false,
          rot: 0,
          src: "",
        });
    return out.slice(0, 10);
  }

  setUp(patch) {
    this.store.update((s) => ({ up: { ...s.up, ...patch } }));
  }

  newVals() {
    const st = this.store.state;
    const up = st.up;
    const D = window.CQ;
    const tot = this.ports.total();
    const pages = this.allPages();
    const cost = this.ports.costOf(pages, up);
    const hands = pages.filter((p) => p.hand && up.hand).length;
    const move = (from, to) => {
      if (from < 0 || from === to) return;
      const a = up.pages.slice();
      const [x] = a.splice(from, 1);
      a.splice(to, 0, x);
      this.setUp({ pages: a, drag: -1 });
    };
    const out = {
      nBal: st.authed
        ? {
            t: "Доступно " + kr(tot),
            bg: tot ? "#EEF3FF" : "#FFF1E8",
            fg: tot ? "#1F4EF5" : "#C2551F",
          }
        : {
            t: "25 кредитов бесплатно после регистрации",
            bg: "#E6F6EC",
            fg: "#15803D",
          },
      dzPad: pages.length ? "18px 20px" : "44px 28px",
      dzTitle: pages.length
        ? "Добавить ещё страницы"
        : "Перетащите фото или PDF",
      camera: (e) => {
        e.stopPropagation();
        this.ports.toast(
          "На телефоне откроется камера. Здесь — выберите фото с компьютера.",
          "photo_camera",
        );
      },
      hasPages: up.pages.length > 0,
      pagesTitle:
        up.pages.length +
        " " +
        plural(up.pages.length, "страница", "страницы", "страниц"),
      clearPages: () => this.setUp({ pages: [], sample: null }),
      thumbs: up.pages.map((p, i) => ({
        key: p.id,
        n: i + 1,
        name: p.name,
        page: p.page,
        src: p.src,
        noSrc: !p.src,
        blur: p.blur,
        rot: p.rot + "deg",
        filter: "none",
        cost:
          p.hand && up.hand
            ? "от руки · 10 кредитов"
            : up.mode === "clean"
              ? "8 кредитов"
              : "5 кредитов",
        costFg: p.hand && up.hand ? "#9A5B00" : "#5B6478",
        border: up.drag === i ? "#1F4EF5" : "transparent",
        onDragStart: (e) => {
          e.dataTransfer.effectAllowed = "move";
          this.setUp({ drag: i });
        },
        onDragOver: (e) => e.preventDefault(),
        onDrop: (e) => {
          e.preventDefault();
          move(this.store.state.up.drag, i);
        },
        onRotate: () =>
          this.setUp({
            pages: up.pages.map((x, j) =>
              j === i ? { ...x, rot: (x.rot + 90) % 360 } : x,
            ),
          }),
        onDelete: () =>
          this.setUp({ pages: up.pages.filter((x, j) => j !== i) }),
      })),
      pdf: up.pdf,
      onPdfFrom: (e) => {
        const v = Math.max(1, Math.min(+e.target.value || 1, up.pdf.to));
        this.setUp({ pdf: { ...up.pdf, from: v } });
      },
      onPdfTo: (e) => {
        const v = Math.min(
          up.pdf.total,
          Math.max(+e.target.value || 1, up.pdf.from),
        );
        this.setUp({ pdf: { ...up.pdf, to: v } });
      },
      dropPdf: () => this.setUp({ pdf: null }),
      samples: SAMPLES.map((s) => ({
        ...s,
        key: s.id,
        border: up.sample === s.id && up.pages.length ? "#1F4EF5" : "#ECEAF0",
        onClick: this.useSample(s),
      })),
      modeOpts: [
        ["copy", "Копия", "С оформлением оригинала", "content_copy"],
        ["clean", "Чистовик", "По выбранному стандарту", "auto_awesome"],
      ].map(([id, label, sub, icon]) => {
        const on = up.mode === id;
        return {
          key: id,
          label,
          sub,
          icon,
          ico: this.ports.ico(
            id === "copy" ? "compare" : "clean",
            on ? {} : { gray: true },
          ),
          onClick: () => this.setUp({ mode: id }),
          border: on ? "#1F4EF5" : "#ECEAF0",
          bg: on ? "#F3F6FF" : "#fff",
          ic: on ? "#1F4EF5" : "#8A90A2",
        };
      }),
      isClean: up.mode === "clean",
      stdOpts: D.standards.map((o) => {
        const on = up.std === o.id;
        return {
          ...o,
          key: o.id,
          biz: !!o.biz,
          op: o.biz ? 0.6 : 1,
          border: on ? "#1F4EF5" : "#ECEAF0",
          bg: on ? "#F3F6FF" : "#fff",
          dot: on ? "5px solid #1F4EF5" : "1.5px solid #C5C2CE",
          onClick: o.biz
            ? () =>
                this.ports.toast(
                  "Свой шаблон компании настраиваем для бизнеса.",
                  "business",
                  "Подробнее",
                  () => this.ports.go("business"),
                )
            : () => this.setUp({ std: o.id }),
        };
      }),
      optRows: [
        ["fill", "Удобно заполнять", "Пустые поля готовы для ввода"],
        [
          "hand",
          "Распознать рукописное",
          "Страница с записями от руки — 10 кредитов",
        ],
        [
          "check",
          "Проверить перед скачиванием",
          "Напомним о сомнительных местах",
        ],
      ].map(([k, t, s]) => ({
        key: k,
        t,
        s,
        tg: tg(up[k]),
        onClick: () => this.setUp({ [k]: !up[k] }),
      })),
      costLine: pages.length
        ? (hands
            ? pages.length -
              hands +
              " × " +
              (up.mode === "clean" ? 8 : 5) +
              " + " +
              hands +
              " × 10 = " +
              kr(cost)
            : pages.length +
              " " +
              plural(pages.length, "страница", "страницы", "страниц") +
              " × " +
              (up.mode === "clean" ? 8 : 5) +
              " кредитов = " +
              kr(cost)) + (st.authed ? " · у вас " + tot : "")
        : "Добавьте страницы — посчитаем стоимость",
      costNote: !pages.length
        ? "Цена видна до запуска."
        : !st.authed
          ? "Спишем при скачивании."
          : tot >= cost
            ? "Спишем при первом скачивании. После — останется " +
              (tot - cost) +
              "."
            : "Не хватает " +
              (cost - tot) +
              " кредитов. Посмотреть результат можно сейчас, пополнить баланс перед скачиванием.",
      costNoteFg:
        st.authed && pages.length && tot < cost ? "#C2551F" : "#5B6478",
      ctaOp: pages.length ? 1 : 0.5,
      startProc: this.ports.startProc,
    };
    return out;
  }
}
