export class FormsController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  formsVals() {
    const st = this.store.state;
    const D = window.CQ;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };
    const chip = (on) => ({
      bg: on ? "#0B1024" : "#fff",
      fg: on ? "#fff" : "#0B1024",
      border: on ? "#0B1024" : "#DEDBE4",
    });

    if (r === "forms") {
      const q = st.formQ.trim().toLowerCase();
      const cats = {};
      D.formCats.forEach((c) => {
        cats[c[0]] = c[1];
      });
      out.formQ = st.formQ;
      out.onFormQ = (e) => this.store.update({ formQ: e.target.value });
      out.formChips = D.formCats.map(([id, label]) => ({
        key: id,
        label,
        onClick: () => this.store.update({ formCat: id }),
        ...chip(st.formCat === id),
      }));
      out.formCards = D.forms
        .filter(
          (x) =>
            (st.formCat === "all" || x.cat === st.formCat) &&
            (!q || x.title.toLowerCase().includes(q)),
        )
        .map((x) => ({
          ...x,
          key: x.slug,
          catLabel: cats[x.cat],
          onClick: () => this.ports.go("form", x.slug),
        }));
      out.formsEmpty = !out.formCards.length;
    }
    return out;
  }

  formVals() {
    const st = this.store.state;
    const D = window.CQ;
    const r = st.route;
    const out = {
      isPayResult: r === "payok" || r === "payfail",
      goForms: () => this.ports.go("forms"),
    };

    if (r === "form") {
      const f = D.forms.find((x) => x.slug === st.param) || D.forms[0];
      out.form = f;
      out.formNote = st.authed
        ? "Скачивание бесплатное, кредиты не списываются."
        : "Нужен вход по почте — это бесплатно.";
      out.dlForm = () => {
        if (!st.authed) {
          this.store.update({
            modal: "login",
            pend: { form: f.title.replace(/\s+/g, "_") },
            login: { step: "email", email: "", code: "", err: "" },
          });
          return;
        }
        this.ports.toast(
          "Скачивание: " + f.title.replace(/\s+/g, "_") + ".docx · бесплатно",
          "download",
        );
      };
    }
    return out;
  }
}
