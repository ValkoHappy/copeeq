import { plural } from "../domain/demo-data.js";
export class AccountController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  accountVals() {
    const st = this.store.state;
    const r = st.route;
    const out = {};
    if (r === "account") {
      Object.assign(out, {
        email: st.email,
        savedSig: st.savedSig,
        noSavedSig: !st.savedSig,
        prefs: st.prefs,
        delSavedSig: () => {
          this.store.update({ savedSig: "" });
          this.ports.toast("Подпись удалена", "delete");
        },
        onPrefMode: (e) => {
          const v = e.target.value;
          this.store.update((s) => ({
            prefs: { ...s.prefs, mode: v },
            up: { ...s.up, mode: v },
          }));
        },
        onPrefStd: (e) => {
          const v = e.target.value;
          this.store.update((s) => ({
            prefs: { ...s.prefs, std: v },
            up: { ...s.up, std: v },
          }));
        },
        keepOpts: [1, 7, 30].map((n) => {
          const on = st.prefs.keep === n;
          return {
            key: "k" + n,
            label: n + " " + plural(n, "день", "дня", "дней"),
            onClick: () =>
              this.store.update((s) => ({
                prefs: { ...s.prefs, keep: n },
                docs: s.docs.map((d) => ({ ...d, days: Math.min(d.days, n) })),
              })),
            bg: on ? "#fff" : "transparent",
            fg: on ? "#0B1024" : "#5B6478",
            shadow: on ? "0 1px 2px rgba(11,16,36,.14)" : "none",
          };
        }),
        exportData: () =>
          this.ports.toast(
            "Выгрузка архива пока не подключена. Почта аккаунта: " + st.email,
            "archive",
          ),
        askDelAccount: () => this.store.update({ modal: "delacc" }),
        logout: () => {
          this.store.update({ authed: false, email: "" });
          this.ports.go("landing");
          this.ports.toast("Вы вышли из аккаунта", "logout");
        },
      });
    }
    return out;
  }

  delaccModalVals() {
    const st = this.store.state;
    const m = st.modal || (st.route === "login" ? "login" : null);
    const out = {};
    if (m === "delacc") {
      out.mTitle = "Удалить аккаунт?";
      out.mSub =
        "Удалим документы, подпись и историю. Неиспользованные пакетные кредиты можно вернуть деньгами — заявление в течение 14 дней с покупки.";
      out.confirmDel = () => {
        this.store.update({
          authed: false,
          everAuthed: false,
          email: "",
          docs: [],
          ops: [],
          receipts: [],
          credits: { free: 0, sub: 0, pack: 0 },
          savedSig: "",
          modal: null,
        });
        this.ports.go("landing");
        this.ports.toast("Аккаунт удалён", "delete");
      };
    }
    return out;
  }
}
