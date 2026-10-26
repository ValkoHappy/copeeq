import { FIELDS, SIGS, TABLES, kr, tg } from "../domain/demo-data.js";
export class ResultViewController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  resultVals() {
    const st = this.store.state;
    const cur = st.cur;
    if (!cur) return { cur: { type: "", cmd: "", sig: "" } };
    const pi = Math.min(cur.pi, cur.pages.length - 1);
    const pg = cur.pages[pi];
    const doubts = this.ports.doubtsOf(cur);
    const open = doubts.filter((d) => !cur.resolved[d.id]);
    const w = this.ui.viewW || 700;
    const fit = ((w - 56) / 595) * 0.94;
    const zoom =
      cur.zoom || Math.max(0.25, Math.min(1.1, Math.floor(fit * 20) / 20));
    const sigOn = (id) =>
      (SIGS[id] || []).some((s) => s[0] === cur.sigField) ? cur.sig : "";
    const sheet = (variant, label, chipBg, chipFg) => ({
      key: variant,
      label,
      chipBg,
      chipFg,
      variant,
      page: pg.page,
      zoom,
      src: variant === "photo" ? pg.src : "",
      resolved: cur.resolved,
      values: cur.values,
      shift: cur.shift,
      reps: cur.reps,
      sig: sigOn(pg.page),
      hl: cur.hl,
      fill: cur.fill,
      noHand: pg.hand && !cur.hand,
      num: cur.pages.length > 1 ? pi + 1 : 0,
      onPick: (id) => this.ports.patchCur({ tab: "check", hl: id }),
    });
    const editSheet = () => {
      const b = sheet("word", "Редактор", "#1F4EF5", "#fff");
      return {
        ...b,
        key: "edit",
        editable: true,
        onField: this.ports.edOnField,
      };
    };
    const withPhoto = cur.view === "both";
    const sheetsAll = [];
    cur.pages.forEach((p, i) => {
      const n = cur.pages.length > 1 ? " · стр. " + (i + 1) : "";
      if (withPhoto)
        sheetsAll.push({
          ...sheet("photo", "Фото оригинала" + n, "rgba(11,16,36,.72)", "#fff"),
          key: "p" + p.id,
          page: p.page,
          src: p.src,
          pg: String(i),
          editable: false,
        });
      sheetsAll.push({
        ...editSheet(),
        key: "e" + p.id,
        page: p.page,
        sig: sigOn(p.page),
        noHand: p.hand && !cur.hand,
        num: cur.pages.length > 1 ? i + 1 : 0,
        label: "Редактор" + n,
        pg: String(i),
      });
    });
    const photoSheets = withPhoto
      ? sheetsAll
          .filter((x) => x.variant === "photo")
          .map((x) => ({
            ...x,
            label: cur.pages.length > 1 ? "стр. " + (+x.pg + 1) : "",
          }))
      : [];
    const sheets = sheetsAll
      .filter((x) => x.variant !== "photo")
      .map((x) => ({
        ...x,
        label: withPhoto
          ? cur.pages.length > 1
            ? "стр. " + (+x.pg + 1)
            : ""
          : x.label,
      }));
    const fields = [];
    cur.pages.forEach((p, i) =>
      (FIELDS[p.page] || []).forEach(([id, label]) => {
        if (!fields.some((f) => f.id === id)) fields.push({ id, label, pi: i });
      }),
    );
    const sigLines = [];
    cur.pages.forEach((p, i) =>
      (SIGS[p.page] || []).forEach(([id, label]) =>
        sigLines.push({
          key: id,
          id,
          label: label + ", стр. " + (i + 1),
          pi: i,
        }),
      ),
    );
    const hasTables = cur.pages.some((p) => TABLES[p.page]);
    const tot = this.ports.total();
    const recent = cur.paid && cur.dlAt && Date.now() - cur.dlAt < 864e5;

    const curVal = (f) =>
      cur.values[f.id] != null ? cur.values[f.id] : this.ports.defaultVal(f.id);
    const dlInfo = cur.paid
      ? {
          icon: "verified",
          ic: "#16A34A",
          text: "Оплачено. Повторные скачивания и другие форматы — бесплатно.",
        }
      : !st.authed
        ? {
            icon: "lock_open",
            ic: "#1F4EF5",
            text:
              "Стоимость — " +
              kr(cur.cost) +
              ". Спишем при первом скачивании — бесплатные страницы.",
          }
        : tot >= cur.cost
          ? {
              icon: "toll",
              ic: "#1F4EF5",
              text:
                "Спишем " +
                kr(cur.cost) +
                " при первом скачивании · у вас " +
                tot,
            }
          : {
              icon: "toll",
              ic: "#C2551F",
              text:
                "Нужно " +
                kr(cur.cost) +
                ", у вас " +
                tot +
                ". Докупите при скачивании — документ не потеряется.",
            };
    dlInfo.img = this.ports.ico(
      dlInfo.icon === "verified" ? "success" : "coin",
      dlInfo.icon === "verified"
        ? { noBlob: true }
        : { bare: true, low: dlInfo.ic === "#C2551F" },
    );
    return {
      withPhoto,
      noPhoto: !withPhoto,
      photoSheets,
      photoRef: this.ui.photoRef,
      onScrollP: this.ports.onScrollP,
      onScrollE: this.ports.onScrollE,
      isEditView: true,
      viewDir: "column",
      viewAlign: "center",
      ...this.ports.secVals(cur, doubts, open, fields, sigLines, hasTables),
      viewerRef: this.ui.viewerRef,
      cur,
      typeOpts: [
        "Анкета соискателя",
        "Заявление о приёме на работу",
        "Акт выполненных работ",
        "Договор",
        "Справка",
        "Другой документ",
      ]
        .filter((x, i, a) => a.indexOf(x) === i)
        .concat(
          [
            "Анкета соискателя",
            "Заявление о приёме на работу",
            "Акт выполненных работ",
          ].includes(cur.type)
            ? []
            : [cur.type],
        ),
      onType: (e) => {
        const v = e.target.value;
        this.ports.patchCur({ type: v });
        this.ports.setDoc(cur.id, { type: v });
        this.ports.toast(
          "Пересобрали разметку под тип «" + v + "». Бесплатно.",
          "category",
        );
      },
      rThumbs: cur.pages.map((p, i) => ({
        key: p.id,
        n: i + 1,
        page: p.page,
        resolved: cur.resolved,
        values: cur.values,
        border: i === pi ? "#1F4EF5" : "#ECEAF0",
        warn:
          doubts.filter((d) => d.pi === i && !cur.resolved[d.id]).length || "",
        onClick: () => this.ports.scrollToPage(i),
      })),
      viewBtns: [
        ["edit", "Редактор"],
        ["both", "Редактор + фото"],
      ].map(([id, label]) => {
        const on = (cur.view === "both" ? "both" : "edit") === id;
        return {
          key: id,
          label,
          onClick: () => this.ports.patchCur({ view: id, zoom: 0 }),
          bg: on ? "#fff" : "transparent",
          fg: on ? "#0B1024" : "#5B6478",
          shadow: on ? "0 1px 2px rgba(11,16,36,.14)" : "none",
        };
      }),
      prevPage: () => this.ports.scrollToPage(Math.max(0, pi - 1)),
      nextPage: () =>
        this.ports.scrollToPage(Math.min(cur.pages.length - 1, pi + 1)),
      pageLabel: pi + 1 + " / " + cur.pages.length,
      zoomIn: () =>
        this.ports.patchCur({ zoom: Math.min(1.6, +(zoom + 0.1).toFixed(2)) }),
      zoomOut: () =>
        this.ports.patchCur({ zoom: Math.max(0.25, +(zoom - 0.1).toFixed(2)) }),
      zoomLabel: Math.round(zoom * 100) + "%",
      viewSheets: sheets,
      userNote: cur.user,
      rTabs: [
        ["check", "Проверка", open.length],
        ["edit", "Доработка", 0],
        ["sig", "Подпись", 0],
      ].map(([id, label, n]) => {
        const on = cur.tab === id;
        return {
          key: id,
          label,
          badge: n || "",
          onClick: () => this.ports.patchCur({ tab: id }),
          fg: on ? "#0B1024" : "#8A90A2",
          line: on ? "#1F4EF5" : "transparent",
        };
      }),
      tabCheck: cur.tab === "check",
      tabEdit: cur.tab === "edit",
      tabSig: cur.tab === "sig",
      noDoubts: !open.length,
      doubtsDoneTitle: doubts.length
        ? "Все места проверены"
        : "Сомнительных мест нет",
      doubtCards: doubts.map((d) => {
        const val = cur.resolved[d.id];
        const editing = cur.editing === d.id && !val;
        return {
          key: d.id,
          label: d.label,
          pn: d.pi + 1,
          value: val || d.v,
          done: !!val,
          doneLabel: val === d.v ? "✓ принято" : "✓ исправлено",
          open: !val && !editing,
          editing,
          dot: val ? "#16A34A" : "#F2B200",
          border: cur.hl === d.id ? "#1F4EF5" : "#ECEAF0",
          draft: cur.draft || "",
          onFocus: () => this.ports.patchCur({ pi: d.pi, hl: d.id }),
          onAccept: (e) => {
            e.stopPropagation();
            this.ports.patchCur((c) => ({
              resolved: { ...c.resolved, [d.id]: d.v },
              hl: d.id,
              pi: d.pi,
            }));
          },
          onFix: (e) => {
            e.stopPropagation();
            this.ports.patchCur({
              editing: d.id,
              draft: "",
              pi: d.pi,
              hl: d.id,
            });
          },
          alts: d.alts
            .filter((a) => a !== d.v)
            .map((a) => ({
              key: a,
              v: a,
              onClick: (e) => {
                e.stopPropagation();
                this.ports.patchCur((c) => ({
                  resolved: { ...c.resolved, [d.id]: a },
                  editing: "",
                }));
              },
            })),
          onDraft: (e) => this.ports.patchCur({ draft: e.target.value }),
          onSave: (e) => {
            e.stopPropagation();
            const v = (this.store.state.cur.draft || "").trim();
            if (!v) return;
            this.ports.patchCur((c) => ({
              resolved: { ...c.resolved, [d.id]: v },
              editing: "",
            }));
          },
        };
      }),
      stop: (e) => e.stopPropagation(),
      onCmd: (e) => this.ports.patchCur({ cmd: e.target.value }),
      onCmdKey: (e) => {
        if (e.key === "Enter") this.ports.applyCmd();
      },
      applyCmd: () => this.ports.applyCmd(),
      cmdHints: ["замени 2024 на 2025", "замени Северный ветер на Восток"].map(
        (t) => ({ key: t, t, onClick: () => this.ports.patchCur({ cmd: t }) }),
      ),
      repList: cur.reps.map((r, i) => ({
        key: "r" + i,
        a: r[0],
        b: r[1],
        onRemove: () =>
          this.ports.patchCur((c) => ({
            reps: c.reps.filter((x, j) => j !== i),
          })),
      })),
      yearDown: () => this.ports.patchCur((c) => ({ shift: c.shift - 1 })),
      yearUp: () => this.ports.patchCur((c) => ({ shift: c.shift + 1 })),
      shiftLabel: cur.shift > 0 ? "+" + cur.shift : String(cur.shift),
      hasFields: fields.length > 0,
      fillLabel: cur.fill ? "Подсветка пустых: вкл" : "Подсветка пустых: выкл",
      toggleFill: () => this.ports.patchCur((c) => ({ fill: !c.fill })),
      fieldRows: fields.map((f) => ({
        key: f.id,
        label: f.label,
        pn: f.pi + 1,
        v: curVal(f),
        onFocus: () => this.ports.patchCur({ pi: f.pi, hl: f.id }),
        onChange: (e) => {
          const v = e.target.value;
          this.ports.edOnField(f.id, v);
        },
      })),
      rModes: [
        ["copy", "Копия"],
        ["clean", "Чистовик"],
      ].map(([id, label]) => {
        const on = cur.mode === id;
        return {
          key: id,
          label,
          onClick: () => {
            this.ports.patchCur({ mode: id });
            this.ports.toast(
              id === "clean"
                ? "Привели к ГОСТ Р 7.0.97-2016 — бесплатно"
                : "Вернули оформление как в оригинале",
              "auto_awesome",
            );
          },
          bg: on ? "#fff" : "transparent",
          fg: on ? "#0B1024" : "#5B6478",
          shadow: on ? "0 1px 2px rgba(11,16,36,.14)" : "none",
        };
      }),
      hasSigLines: sigLines.length > 0,
      noSigLines: !sigLines.length,
      sigLines,
      noSig: !cur.sig,
      savedSig: st.savedSig,
      openSig: () =>
        this.store.update({
          modal: "sig",
          sigDraft: {
            has: false,
            consent: false,
            field: cur.sigField || (sigLines[0] && sigLines[0].id),
          },
        }),
      uploadSig: () =>
        this.ui.sigInput.current && this.ui.sigInput.current.click(),
      useSavedSig: () =>
        this.ports.patchCur({
          sig: st.savedSig,
          sigField: sigLines[0].id,
          pi: sigLines[0].pi,
        }),
      sigLineBtns: sigLines.map((l) => {
        const on = cur.sigField === l.id;
        return {
          key: l.id,
          label: l.label,
          border: on ? "#1F4EF5" : "#ECEAF0",
          dot: on ? "5px solid #1F4EF5" : "1.5px solid #C5C2CE",
          onClick: () => this.ports.patchCur({ sigField: l.id, pi: l.pi }),
        };
      }),
      removeSig: () => this.ports.patchCur({ sig: "", sigField: "" }),
      onSigField: (e) => {
        const id = e.target.value;
        const l = sigLines.find((x) => x.id === id);
        this.ports.patchCur({ sigField: id, pi: l ? l.pi : pi });
      },
      attachTg: tg(cur.attach),
      toggleAttach: () => this.ports.patchCur((c) => ({ attach: !c.attach })),
      dlInfo,
      dlDocx: () => this.ports.download("docx"),
      dlMore: [
        ["pdf", "PDF"],
        ["scan", "Чистый скан"],
        hasTables ? ["xlsx", "Excel"] : null,
      ]
        .filter(Boolean)
        .map(([k, label]) => ({
          key: k,
          label,
          onClick: () => this.ports.download(k),
        })),
      canBad: !!recent && !cur.refunded,
      openBad: () => this.store.update({ modal: "bad", bad: { reason: 0 } }),
    };
  }
}
