export class LandingUploadController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  uploadLandingVals() {
    const st = this.store.state;

    return {
      pickFile: this.ports.pickFile,
      dzBorder: st.up.over ? "#1F4EF5" : "#C9D3E8",
      dzBg: st.up.over ? "#EEF3FF" : "#fff",
      dzOver: (e) => {
        e.preventDefault();
        if (!st.up.over)
          this.store.update((s) => ({ up: { ...s.up, over: true } }));
      },
      dzLeave: () =>
        this.store.update((s) => ({ up: { ...s.up, over: false } })),
      dzDrop: (e) => {
        e.preventDefault();
        this.store.update((s) => ({ up: { ...s.up, over: false } }));
        this.ports.addFiles(e.dataTransfer && e.dataTransfer.files);
      },
    };
  }
}
