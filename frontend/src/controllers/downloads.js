import { plural, kr } from "../domain/demo-data.js";
export class DownloadsController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  download = (kind, force) => {
    const st = this.store.state;
    const cur = st.cur;
    if (!cur) return;
    const open = this.ports
      .doubtsOf(cur)
      .filter((d) => !cur.resolved[d.id]).length;
    if (cur.check && open && !force) {
      this.store.update({ modal: "warn", pend: { dl: kind } });
      return;
    }
    if (!st.authed) {
      this.store.update({
        modal: "login",
        pend: { dl: kind },
        login: { step: "email", email: "", code: "", err: "" },
      });
      return;
    }
    if (cur.paid) {
      this.finishDl(kind, false);
      return;
    }
    const have = this.ports.total();
    if (have < cur.cost) {
      const short = cur.cost - have;
      const pl =
        window.CQ.plans.find((p) => p.credits >= short) || window.CQ.plans[0];
      this.store.update({
        modal: "buy",
        pend: { dl: kind },
        buy: {
          need: cur.cost,
          pick: pl.id,
          method: "sbp",
          paying: false,
          sub: false,
        },
      });
      return;
    }
    const credits = this.ports.spend(cur.cost);
    this.store.update({
      credits,
      modal: null,
      pend: null,
      cur: { ...cur, paid: true, dlAt: Date.now(), refunded: false },
    });
    this.ports.setDoc(cur.id, { paid: true });
    this.ports.op(cur.type, cur.pages.length, -cur.cost);
    this.finishDl(kind, true);
  };

  finishDl(kind, charged) {
    const cur = this.store.state.cur;
    const base = cur.type.replace(/\s+/g, "_");
    const name =
      {
        docx: base + ".docx",
        pdf: base + ".pdf",
        scan: base + "_скан.pdf",
        xlsx: base + ".xlsx",
      }[kind] || base + ".docx";
    this.store.update({ modal: null, pend: null });
    this.ports.toast(
      "Скачивание: " +
        name +
        (charged
          ? " · списано " + kr(cur.cost) + ", остаток " + this.ports.total()
          : " · бесплатно"),
      "download",
    );
  }

  warnModalVals() {
    const st = this.store.state;
    const m = st.modal || (st.route === "login" ? "login" : null);
    const out = {};
    if (m === "warn") {
      const n = this.ports
        .doubtsOf(st.cur)
        .filter((d) => !st.cur.resolved[d.id]).length;
      out.mTitle =
        "Осталось проверить " + n + " " + plural(n, "место", "места", "мест");
      out.mSub =
        "Вы включили «Проверить перед скачиванием». Там, где мы не уверены, лучше взглянуть — это минута.";
      Object.assign(out, {
        warnCheck: () => {
          const d = this.ports
            .doubtsOf(st.cur)
            .find((x) => !st.cur.resolved[x.id]);
          this.store.update({ modal: null });
          this.ports.patchCur({ tab: "check", pi: d.pi, hl: d.id });
        },
        warnSkip: () => {
          const p = st.pend;
          this.store.update({ modal: null });
          this.download(p.dl, true);
        },
      });
    }
    return out;
  }
}
