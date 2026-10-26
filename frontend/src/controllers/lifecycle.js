export class LifecycleController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  componentDidMount() {
    this.ro = new ResizeObserver(() => {
      const el = this.ui.viewerRef.current;
      const w = el ? el.clientWidth : 0;
      if (w && Math.abs(w - (this.ui.viewW || 0)) > 8) {
        this.ui.viewW = w;
        this.ui.invalidate();
      }
    });
    this.roT = this.timers.setInterval(() => {
      const el = this.ui.viewerRef.current;
      if (el && el !== this.roEl) {
        if (this.roEl) this.ro.unobserve(this.roEl);
        this.roEl = el;
        this.ro.observe(el);
      }
    }, 300);
    this.onPaste = (e) => this.ports.handlePaste(e);
    this.onKey = (e) => {
      if (e.key === "Escape" && this.store.state.modal) this.ports.closeModal();
    };
    window.addEventListener("paste", this.onPaste);
    window.addEventListener("keydown", this.onKey);
    this.onWinResize = () => {
      this.timers.clearTimeout(this.rzT);
      this.rzT = this.timers.setTimeout(() => this.ui.invalidate(), 80);
    };
    window.addEventListener("resize", this.onWinResize);
    if (!window.CQ || !window.CQI)
      this.waitT = this.timers.setInterval(() => {
        if (window.CQ && window.CQI) {
          this.timers.clearInterval(this.waitT);
          this.store.update(this.ports.makeState(this.ui.props || {}));
        }
      }, 60);
    if (this.store.state.route === "processing") this.ports.runProc();
  }

  componentDidUpdate(pp, ps) {
    if (ps && ps.credits && this.store.state.authed && ps.authed) {
      const a = ps.credits.free + ps.credits.sub + ps.credits.pack,
        b = this.ports.total();
      if (a !== b) {
        this.timers.clearTimeout(this.balT);
        this.store.update((s) => ({ bal: { n: s.bal.n + 1, d: b - a } }));
        this.balT = this.timers.setTimeout(
          () => this.store.update((s) => ({ bal: { ...s.bal, d: 0 } })),
          1800,
        );
      }
    }
    const p = this.ui.props || {};
    if (
      pp.startScreen !== p.startScreen ||
      pp.signedIn !== p.signedIn ||
      pp.balance !== p.balance
    ) {
      this.ports.stopProcessing();
      this.store.update(this.ports.makeState(p), () => {
        if (this.store.state.route === "processing") this.ports.runProc();
      });
    }
  }

  componentWillUnmount() {
    if (this.ro) this.ro.disconnect();
    window.removeEventListener("paste", this.onPaste);
    window.removeEventListener("keydown", this.onKey);
    window.removeEventListener("resize", this.onWinResize);
  }
}
