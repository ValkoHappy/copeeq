import { createApplication } from "./application.js";
import { ComponentStore } from "./infrastructure/component-store.js";

/** Rendering adapter only. Feature behavior lives in injected controllers. */
export function createComponent(DCLogic, React) {
  return class Component extends DCLogic {
    constructor(props) {
      super(props);
      this.application = createApplication(
        new ComponentStore(this),
        React,
        props || {},
        () => this.forceUpdate(),
      );
    }
    renderVals() {
      return this.application.render();
    }
    componentDidMount() {
      this.application.mount();
    }
    componentDidUpdate(props, state) {
      this.application.update(props, state, this.props || {});
    }
    componentWillUnmount() {
      this.application.dispose();
    }
  };
}
