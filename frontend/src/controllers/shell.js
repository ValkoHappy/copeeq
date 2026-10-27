import { APP, TOAST_ICO, kr } from "../domain/demo-data.js";
export class ShellController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  shellVals(isApp) {
    const st = this.store.state;
    const r = st.route;
    const cur = st.cur;
    const tot = this.ports.total();
    const wide = st.side && window.innerWidth > 700;
    const act = {
      dash: "dash",
      new: "new",
      processing: "cur",
      result: st.cur && st.cur.view === "edit" ? "ed" : "cur",
      editor: "ed",
      docs: "docs",
      billing: "billing",
      account: "account",
    }[r];
    const ICO = {
      dash: "dashboard",
      docs: "docs",
      ed: "editor",
      billing: "credits",
      account: "profile",
      forms: "forms",
      examples: "compare",
      pricing: "tariff",
      faq: "support",
    };
    const item = (id, icon, label, go, extra) => {
      const on = act === id || (id === "ed" && r === "editor");
      return {
        key: id,
        icon,
        label,
        go,
        ico: this.ico(ICO[id], on ? {} : { noBlob: true }),
        icoFilter: "none",
        bg: on ? "#EEF3FF" : "transparent",
        fg: on ? "#1F4EF5" : "#3A4156",
        fill: on ? 1 : 0,
        op: 1,
        count: "",
        cBg: "#F1F0F4",
        cFg: "#5B6478",
        ...(extra || {}),
      };
    };

    const groups = [
      {
        key: "g1",
        title: "Работа",
        items: [
          item("dash", "space_dashboard", "Обзор", () => this.ports.go("dash")),
          item(
            "docs",
            "folder_open",
            "Мои документы",
            () => this.ports.go("docs"),
            {
              count: st.authed && st.docs.length ? String(st.docs.length) : "",
            },
          ),
          item(
            "ed",
            "edit_document",
            "Редактор",
            () => this.ports.goEditor(),
            cur
              ? {}
              : {
                  op: 0.55,
                  ico: this.ico("editor", { gray: true, noBlob: true }),
                },
          ),
        ],
      },
      {
        key: "g2",
        title: "Аккаунт",
        items: [
          item("billing", "toll", "Баланс", () => this.ports.go("billing"), {
            count: st.authed ? String(tot) : "",
            cBg: tot < 3 ? "#FFF1E8" : "#EEF3FF",
            cFg: tot < 3 ? "#C2551F" : "#1F4EF5",
          }),
          item("account", "person", "Профиль", () => this.ports.go("account")),
        ],
      },
      {
        key: "g3",
        title: "Сервис",
        items: [
          item("forms", "description", "Бланки", () => this.ports.go("forms")),
          item("examples", "collections", "Примеры", () =>
            this.ports.go("examples"),
          ),
          item("faq", "help", "Помощь", () => this.ports.go("faq")),
        ],
      },
    ].map((g) => ({ ...g, showTitle: wide }));
    const dn = cur
      ? this.ports.doubtsOf(cur).filter((d) => !cur.resolved[d.id]).length
      : 0;
    const sideCur =
      cur && ["ready", "processing"].includes(cur.status) && wide
        ? {
            type: cur.type,
            meta:
              cur.status === "processing"
                ? "Обрабатывается…"
                : cur.paid
                  ? "Оплачен · скачивание бесплатно"
                  : dn
                    ? "Проверить: " + dn
                    : "Готов к скачиванию",
            links: [
              ["result", "edit_document", "Редактор"],
              ["editor", "image", "С фото"],
            ].map(([id, icon, label]) => {
              return {
                key: id,
                icon,
                label,
                go: () => {
                  this.store.update((s) => ({
                    cur: { ...s.cur, view: id === "editor" ? "both" : "edit" },
                  }));
                  this.ports.go(
                    cur.status === "processing" ? "processing" : "result",
                  );
                },
                bg:
                  r === "result" && (id === "editor") === (cur.view === "both")
                    ? "#1F4EF5"
                    : "#fff",
                fg:
                  r === "result" && (id === "editor") === (cur.view === "both")
                    ? "#fff"
                    : "#0B1024",
              };
            }),
          }
        : null;
    const SD = { ready: "#16A34A", processing: "#1F4EF5", error: "#DC3B45" };
    const recent = st.docs
      .filter((d) => !cur || d.id !== cur.id)
      .slice(0, 4)
      .map((d) => ({
        key: d.id,
        type: d.type,
        date: d.date,
        dot: SD[d.status],
        go: this.ports.openDocsDoc(d),
      }));
    const titles = {
      dash: "Обзор",
      new: "Новый документ",
      processing: "Обработка",
      docs: "Мои документы",
      billing: "Баланс",
      account: "Профиль",
      forms: "Бланки",
      examples: "Примеры",
      faq: "Помощь",
    };
    const crumbs = [
      { label: "Кабинет", go: () => this.ports.go(st.authed ? "dash" : "new") },
    ];
    if (r === "result" || r === "editor") {
      crumbs.push(
        { label: "Мои документы", go: () => this.ports.go("docs") },
        { label: cur ? cur.type : "", go: () => this.ports.go("result") },
      );
      if (r === "editor" || (cur && cur.view === "edit"))
        crumbs.push({ label: "Редактор", go: () => {} });
    } else if (r === "form")
      crumbs.push(
        { label: "Бланки", go: () => this.ports.go("forms") },
        { label: "Бланк", go: () => {} },
      );
    else if (r !== "dash")
      crumbs.push({ label: titles[r] || "", go: () => {} });
    const vh = window.innerHeight || 900;
    return {
      isShell: isApp,
      showHeader: !isApp,
      sideW: wide ? "252px" : "76px",
      sideWide: wide,
      sideNarrow: !wide,
      toggleSide: () => this.store.update((s) => ({ side: !s.side })),
      sideGroups: groups
        .filter((g) => g.key !== "g3" || vh >= 600 || !wide)
        .map((g) => ({ ...g, showTitle: wide && vh >= 720 })),
      sideCur: vh >= 800 ? sideCur : null,
      sideRecent: recent.slice(0, vh >= 1080 ? 4 : 3),
      sideRecentShow:
        wide && st.authed && recent.length > 0 && vh >= (sideCur ? 1060 : 940),
      itemH: vh >= 820 ? "42px" : vh >= 680 ? "38px" : "34px",
      sideGap: vh >= 820 ? "14px" : "8px",
      crumbs: crumbs.map((c, i) => ({
        ...c,
        key: "c" + i,
        sep: i > 0,
        fw: i === crumbs.length - 1 ? 800 : 600,
        fg: i === crumbs.length - 1 ? "#0B1024" : "#8A90A2",
      })),
      topQ: st.docsQ,
      onTopQ: (e) => this.store.update({ docsQ: e.target.value }),
      onTopKey: (e) => {
        if (e.key === "Enter") this.ports.go("docs");
      },
      mainOverflow:
        r === "result" || r === "editor" || r === "processing"
          ? "hidden"
          : "auto",
      balPct: Math.min(100, (tot / 50) * 100) + "%",
      goDocs: () => this.ports.go("docs"),
      goEditor: () => this.ports.goEditor(),
      goResult: () => this.ports.go("result"),
    };
  }

  ico(name, o) {
    return window.CQI ? window.CQI.get(name, o) : "";
  }

  renderVals() {
    const st = this.store.state;
    const r = st.route;
    const D = window.CQ;
    const isApp = APP.includes(r);
    const navItems = [
      ["examples", "Примеры"],
      ["forms", "Бланки"],
      ["pricing", "Цены"],
    ];
    if (st.authed) navItems.push(["dash", "Кабинет"]);
    const tot = this.ports.total();
    const base = {
      fileInput: this.ui.fileInput,
      sigInput: this.ui.sigInput,
      onFile: this.ports.onFile,
      authed: st.authed,
      guest: !st.authed,
      hdrMax: "1240px",
      showFooter: !isApp && r !== "login",
      ...this.shellVals(isApp),
      topNav: navItems.map(([id, label]) => ({
        key: id,
        label,
        go: () => this.ports.go(id),
        fg:
          r === id || (id === "forms" && r === "form") ? "#1F4EF5" : "#0B1024",
        line:
          r === id || (id === "forms" && r === "form")
            ? "#1F4EF5"
            : "transparent",
      })),
      secIco: this.ico("security"),
      bellIco: this.ico("bell", { anim: true, nonce: 1 }),
      doneIco: this.ico("done", { anim: true }),
      camIco: this.ico("camera", { noBlob: true }),
      coinChip: st.bal.n
        ? this.ico("coin", {
            bare: true,
            low: tot < 3,
            anim: "bounce",
            nonce: st.bal.n,
          })
        : this.ico("coin", { bare: true, low: tot < 3 }),
      coinWhite: this.ico("coin1", { white: true }),
      coinPlain: this.ico("coin", { bare: true }),
      upIco: st.up.over
        ? this.ico("upload", { anim: true })
        : this.ico("upload"),
      newIco: this.ico("newdoc", { anim: true }),
      loadIco: this.ico("loading", { anim: true }),
      errIco: this.ico("error", { anim: true }),
      coinSpin: this.ico("coin1", { anim: "spin", white: true }),
      balDelta: st.bal.d
        ? st.bal.d > 0
          ? "+" + st.bal.d
          : "−" + Math.abs(st.bal.d)
        : "",
      balDeltaBg: st.bal.d > 0 ? "#16A34A" : "#0B1024",
      toastImg:
        st.toast && TOAST_ICO[st.toast.icon]
          ? this.ico(TOAST_ICO[st.toast.icon], {
              anim: true,
              loop: false,
              nonce: st.toast.n,
            })
          : "",
      toastNoImg: !(st.toast && TOAST_ICO[st.toast.icon]),
      balLabel: kr(tot),
      balDot: tot < 3 ? "#E0703A" : "#1F4EF5",
      initials: (st.email || "М").slice(0, 1).toUpperCase(),
      goHome: () => this.ports.go("landing"),
      goNew: () => this.ports.go("new"),
      goLogin: () =>
        this.store.update({
          modal: "login",
          pend: null,
          login: { step: "email", email: "", code: "", err: "" },
        }),
      goBilling: () => this.ports.go("billing"),
      goAccount: () => this.ports.go("account"),
      toast: st.toast,
      closeToast: this.ports.closeToast,
      toastAction: this.ports.toastAction,
      footCols: [
        {
          key: "c1",
          title: "Сервис",
          items: [
            ["new", "Загрузить документ"],
            ["examples", "Примеры"],
            ["pricing", "Цены"],
            ["faq", "Вопросы"],
            ["chistovik", "Режим «Чистовик»"],
            ["students", "Студентам"],
            ["business", "Для бизнеса"],
          ],
        },
        {
          key: "c2",
          title: "Конвертеры",
          items: [
            ["seo:foto-v-word", "Фото в Word"],
            ["seo:skan-v-word", "Скан в Word"],
            ["seo:pdf-v-word", "PDF в Word"],
            ["seo:jpg-v-word", "JPG в Word"],
            ["seo:skan-v-excel", "Скан в Excel"],
          ],
        },
        {
          key: "c3",
          title: "Бланки",
          items: [
            ["forms:work", "Работа"],
            ["forms:family", "Семья"],
            ["forms:home", "Жильё"],
            ["forms:study", "Учёба"],
            ["forms:tax", "Налоги"],
          ],
        },
        {
          key: "c4",
          title: "Документы",
          items: [
            ["legal:offer", "Условия использования"],
            ["legal:privacy", "Персональные данные"],
            ["security", "Данные и безопасность"],
            ["legal:contacts", "Контакты"],
          ],
        },
      ].map((c) => ({
        ...c,
        items: c.items.map(([to, label]) => ({
          key: to,
          label,
          go: () => {
            const [a, b] = to.split(":");
            if (a === "forms")
              this.ports.go("forms", "", { formCat: b || "all" });
            else this.ports.go(a, b);
          },
        })),
      })),
    };
    if (!D) return base;
    [
      "isDash",
      "isEditor",
      "isLanding",
      "isNew",
      "isProcessing",
      "isResult",
      "isDocs",
      "isBilling",
      "isAccount",
      "isLogin",
      "isPricing",
      "isExamples",
      "isForms",
      "isForm",
      "isFaq",
      "isBusiness",
      "isChistovik",
      "isStudents",
      "isSecurity",
      "isSeo",
      "isLegal",
      "isPayok",
      "isPayfail",
      "isNotfound",
    ].forEach((k) => {
      base[k] = r === k.slice(2).toLowerCase();
    });
    return Object.assign(
      base,
      this.ports.landingVals(),
      this.ports.routeValues(),
      this.ports.modalValues(),
    );
  }
}
