export class NotificationsController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  toast(text, icon, action, fn) {
    this.timers.clearTimeout(this.toastT);
    this.store.update({
      toast: {
        text,
        icon: icon || "check_circle",
        action: action || "",
        n: Date.now(),
      },
    });
    this.toastFn = fn;
    this.toastT = this.timers.setTimeout(
      () => this.store.update({ toast: null }),
      4800,
    );
  }

  closeToast = () => this.store.update({ toast: null });

  toastAction = () => {
    const action = this.toastFn;
    this.closeToast();
    if (action) action();
  };
}
