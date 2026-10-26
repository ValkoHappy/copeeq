import { SAMPLES, plural } from "../domain/demo-data.js";
export class ProcessingController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  startProc = () => {
    const st = this.store.state;
    const pages = this.ports.allPages();
    if (!pages.length) {
      this.ports.pickFile();
      return;
    }
    const sm = SAMPLES.find(
      (x) => x.id === st.up.sample && x.pages[0][0] === pages[0].page,
    );
    const type = sm
      ? sm.type
      : {
          ank1: "Анкета соискателя",
          ank2: "Анкета соискателя",
          ank3: "Анкета соискателя",
          zayav: "Заявление о приёме на работу",
          akt: "Акт выполненных работ",
        }[pages[0].page] || "Другой документ";
    const cur = this.ports.newDoc(type, pages, st.up);
    this.store.update(
      (s) => ({
        cur,
        route: "processing",
        proc: { t0: 0, t: 0, err: null, done: false },
        docs: [
          {
            id: cur.id,
            type,
            page: cur.page,
            date: "Сегодня",
            pages: pages.length,
            status: "processing",
            days: s.prefs.keep,
          },
          ...s.docs,
        ],
      }),
      () => this.runProc(),
    );
    window.scrollTo(0, 0);
  };

  runProc() {
    this.timers.clearInterval(this.procT);
    this.timers.clearTimeout(this.doneT);
    this.store.update((s) => ({
      proc: {
        t0: Date.now() - (s.proc.t || 0) * 1000,
        t: s.proc.t || 0,
        err: null,
        done: false,
      },
    }));
    this.procT = this.timers.setInterval(() => {
      const st = this.store.state;
      if (st.route !== "processing" || !st.cur) return;
      const p = st.proc;
      if (p.err || p.done || !p.t0) return;
      const t = (Date.now() - p.t0) / 1000;
      const plan = this.ports.procPlan(st.cur);
      const bj = st.cur.pages.findIndex((x, j) => {
        if (!x.blur) return false;
        const q = this.ports.pageState(plan, j, t);
        return q.k > 0 || (q.k === 0 && q.pf > 0.6);
      });
      if (bj >= 0) {
        this.timers.clearInterval(this.procT);
        this.store.update({
          proc: {
            ...p,
            t,
            err: { pi: bj, reason: "Фото слишком размыто — текст не читается" },
          },
        });
        this.ports.setDoc(st.cur.id, {
          status: "error",
          reason: "Фото слишком размыто",
        });
        return;
      }
      if (t >= plan.total) {
        this.timers.clearInterval(this.procT);
        this.store.update({ proc: { ...p, t: plan.total, done: true } });
        this.doneT = this.timers.setTimeout(() => {
          if (
            this.store.state.route === "processing" &&
            this.store.state.proc.done
          )
            this.finishProc();
        }, 6000);
        return;
      }
      this.store.update({ proc: { ...p, t } });
    }, 200);
  }

  finishProc() {
    const cur = this.store.state.cur;
    this.ports.setDoc(cur.id, { status: "ready" });
    this.store.update({
      cur: { ...cur, status: "ready" },
      route: "result",
      ...(window.innerWidth < 1360 ? { side: false } : {}),
    });
    const n = this.ports.doubtsOf(cur).length;
    this.ports.toast(
      n
        ? "Готово. Проверьте " +
            n +
            " " +
            plural(n, "место", "места", "мест") +
            ", где мы не уверены."
        : "Готово. Документ собран — можно скачивать.",
      "task_alt",
    );
  }

  stopProcessing() {
    this.timers.clearInterval(this.procT);
    this.timers.clearTimeout(this.doneT);
  }
}
