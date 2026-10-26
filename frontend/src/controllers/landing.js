export class LandingController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  setL(patch) {
    this.store.update((s) => ({ L: { ...s.L, ...patch } }));
  }

  landingVals() {
    return Object.assign(
      {},
      this.ports.uploadLandingVals(),
      this.ports.comparisonLandingVals(),
      this.ports.economyLandingVals(),
      this.ports.editorDemoLandingVals(),
      this.ports.featuresLandingVals(),
      this.ports.handwritingLandingVals(),
      this.ports.catalogLandingVals(),
    );
  }
}
