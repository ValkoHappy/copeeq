export class ViewerController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  syncPane(from) {
    if (this.syncLock && this.syncLock !== from) return;
    const a =
        from === "p" ? this.ui.photoRef.current : this.ui.viewerRef.current,
      b = from === "p" ? this.ui.viewerRef.current : this.ui.photoRef.current;
    if (!a || !b) return;
    this.syncLock = from;
    this.timers.clearTimeout(this.syncT);
    this.syncT = this.timers.setTimeout(() => {
      this.syncLock = null;
    }, 120);
    const r = a.scrollTop / Math.max(1, a.scrollHeight - a.clientHeight);
    b.scrollTop = r * (b.scrollHeight - b.clientHeight);
    b.scrollLeft = a.scrollLeft;
  }

  onScrollP = () => this.syncPane("p");

  onScrollE = () => this.syncPane("e");

  scrollToPage(i) {
    this.ports.patchCur({ pi: i });
    this.timers.setTimeout(() => {
      const box = this.ui.viewerRef.current;
      if (!box) return;
      const el = box.querySelector('[data-pg="' + i + '"]');
      if (el)
        box.scrollTo({
          top:
            el.getBoundingClientRect().top -
            box.getBoundingClientRect().top +
            box.scrollTop -
            40,
          behavior: "smooth",
        });
    }, 30);
  }
}
