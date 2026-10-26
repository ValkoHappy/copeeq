export class ModalController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  modalBaseVals() {
    const st = this.store.state;
    const m = st.modal || (st.route === "login" ? "login" : null);
    if (!m) return { modalShow: false };
    const page = !st.modal;
    const out = {
      modalShow: true,
      ovStyle: page
        ? {
            minHeight: "calc(100vh - 65px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "40px 24px",
            background:
              "radial-gradient(circle at 30% 20%, #E8EEFF, #F9F8F8 60%)",
          }
        : {
            position: "fixed",
            inset: 0,
            zIndex: 200,
            background: "rgba(11,16,36,.42)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
            animation: "fadeUp .15s ease",
          },
      closeModal: page ? () => this.ports.go("landing") : this.ports.closeModal,
      stopProp: (e) => e.stopPropagation(),
      modalW: "480px",
      mTitle: "",
      mSub: "",
      mLogin: m === "login",
      mBuy: m === "buy",
      mSig: m === "sig",
      mBad: m === "bad",
      mWarn: m === "warn",
      mConfirm: m === "del" || m === "delacc",
    };

    return out;
  }
}
