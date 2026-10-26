import { FREE } from "../domain/demo-data.js";
export class AuthenticationController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  needAuth(pend) {
    if (this.store.state.authed) return false;
    this.store.update({
      modal: "login",
      pend: pend || { route: "new" },
      login: {
        step: "email",
        email: this.store.state.login.email,
        code: "",
        err: "",
      },
    });
    return true;
  }

  afterAuth() {
    const p = this.store.state.pend;
    this.store.update({ pend: null });
    if (p && p.dl)
      this.timers.setTimeout(() => this.ports.download(p.dl, true), 250);
    else if (p && p.route)
      this.timers.setTimeout(() => {
        this.ports.go(p.route, p.param);
        if (p.pick)
          this.ports.toast(
            "Готово — теперь выберите файлы",
            "folder_open",
            "Выбрать",
            () => this.ports.pickFile(),
          );
      }, 0);
    else if (p && p.form)
      this.ports.toast(
        "Скачивание: " + p.form + ".docx · бесплатно",
        "download",
      );
  }

  loginDone(email) {
    const st = this.store.state;
    const first = !st.everAuthed;
    const credits = first
      ? { ...st.credits, free: st.credits.free + FREE }
      : st.credits;
    this.store.update({
      authed: true,
      everAuthed: true,
      email: email || st.login.email || "m.sokolova@mail.ru",
      credits,
      modal: null,
      ...(first ? { docs: st.docs.length ? st.docs : [] } : {}),
    });
    if (first) this.ports.op("Бесплатные страницы за регистрацию", 0, FREE);
    this.ports.toast(
      first
        ? "Аккаунт создан. Начислили 25 бесплатных кредитов."
        : "Вы вошли в аккаунт",
      "waving_hand",
    );
    if (
      !st.pend &&
      !["result", "editor", "new", "processing"].includes(st.route)
    ) {
      this.timers.setTimeout(() => this.ports.go("dash"), 0);
      return;
    }
    this.afterAuth();
  }

  loginModalVals() {
    const st = this.store.state;
    const m = st.modal || (st.route === "login" ? "login" : null);
    const out = {};
    const L = st.login;
    const setLogin = (p) =>
      this.store.update((s) => ({ login: { ...s.login, ...p } }));
    if (m === "login") {
      const p = st.pend || {};
      out.mTitle = L.step === "email" ? "Вход в Copeeq" : "Введите код";
      out.mSub =
        L.step === "email"
          ? p.dl
            ? "Войдите, чтобы скачать — документ не потеряется. Новым аккаунтам — 25 кредитов бесплатно."
            : p.form
              ? "Пустые бланки бесплатны после входа."
              : p.route === "new"
                ? "Чтобы загрузить документ, войдите или зарегистрируйтесь. Новым аккаунтам — 25 кредитов бесплатно."
                : "Код на почту — без паролей."
          : "";
      Object.assign(out, {
        login: L,
        loginEmailStep: L.step === "email",
        loginCodeStep: L.step === "code",
        loginBorder: L.err ? "#DC3B45" : "#E3E1EA",
        onLoginEmail: (e) => setLogin({ email: e.target.value, err: "" }),
        onLoginKey: (e) => {
          if (e.key === "Enter") out.sendCode();
        },
        sendCode: () => {
          if (!/^\S+@\S+\.\S+$/.test(this.store.state.login.email.trim())) {
            setLogin({ err: "Проверьте адрес — нужен вид name@mail.ru" });
            return;
          }
          setLogin({ step: "code", code: "", err: "" });
        },
        onLoginCode: (e) => {
          const v = e.target.value.replace(/\D/g, "").slice(0, 6);
          setLogin({ code: v, err: "" });
          if (v.length === 6)
            this.timers.setTimeout(
              () => this.loginDone(this.store.state.login.email.trim()),
              250,
            );
        },
        checkCode: () => {
          if (this.store.state.login.code.length < 6) {
            setLogin({ err: "Нужно 6 цифр из письма" });
            return;
          }
          this.loginDone(this.store.state.login.email.trim());
        },
        backEmail: () => setLogin({ step: "email", err: "" }),
        resend: () =>
          this.ports.toast("Отправили новый код на " + L.email, "mail"),
        yandex: () => this.loginDone("m.sokolova@yandex.ru"),
        vk: () => this.loginDone("m.sokolova@vk.com"),
      });
    }
    return out;
  }
}
