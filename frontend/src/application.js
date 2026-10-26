import { createControllers } from "./composition.js";
import { UiResources } from "./infrastructure/ui-resources.js";
import { Scheduler } from "./infrastructure/scheduler.js";
export function createApplication(store, React, props, invalidate) {
  const scheduler = new Scheduler();
  const ui = new UiResources(React, props, invalidate);
  const controllers = {};
  const routePresenters = {
    dash: () => Object.assign({}, controllers["dashboard"].dashVals()),
    new: () => Object.assign({}, controllers["upload"].newVals()),
    processing: () =>
      Object.assign({}, controllers["processing-view"].procVals()),
    result: () =>
      Object.assign(
        {},
        controllers["editor-view"].editorVals(),
        controllers["result-view"].resultVals(),
      ),
    editor: () =>
      Object.assign(
        {},
        controllers["result-view"].resultVals(),
        controllers["editor-view"].editorVals(),
      ),
    docs: () =>
      Object.assign({}, controllers["document-list"].documentListVals()),
    billing: () => Object.assign({}, controllers["billing"].billingVals()),
    account: () => Object.assign({}, controllers["account"].accountVals()),
    pricing: () => Object.assign({}, controllers["pricing"].pricingVals()),
    examples: () => Object.assign({}, controllers["examples"].examplesVals()),
    forms: () => Object.assign({}, controllers["forms"].formsVals()),
    form: () => Object.assign({}, controllers["forms"].formVals()),
    faq: () => Object.assign({}, controllers["faq"].faqVals()),
    seo: () => Object.assign({}, controllers["content"].seoVals()),
    chistovik: () => Object.assign({}, controllers["content"].chistovikVals()),
    students: () => Object.assign({}, controllers["content"].studentsVals()),
    security: () => Object.assign({}, controllers["content"].securityVals()),
    business: () => Object.assign({}, controllers["business"].businessVals()),
    legal: () => Object.assign({}, controllers["legal"].legalVals()),
    payok: () =>
      Object.assign({}, controllers["payment-result"].paymentResultVals()),
    payfail: () =>
      Object.assign({}, controllers["payment-result"].paymentResultVals()),
  };
  const modalPresenters = {
    login: () => controllers["authentication"].loginModalVals(),
    buy: () => controllers["billing"].buyModalVals(),
    sig: () => controllers["signature"].sigModalVals(),
    bad: () => controllers["refund"].badModalVals(),
    warn: () => controllers["downloads"].warnModalVals(),
    del: () => controllers["document-list"].delModalVals(),
    delacc: () => controllers["account"].delaccModalVals(),
  };
  const routeValues = () => routePresenters[store.state.route]?.() || {};
  const modalValues = () => {
    const modal =
      store.state.modal || (store.state.route === "login" ? "login" : null);
    return {
      ...controllers.modal.modalBaseVals(),
      ...modalPresenters[modal]?.(),
    };
  };
  Object.assign(
    controllers,
    createControllers(store, ui, scheduler, { routeValues, modalValues }),
  );
  store.initialize(controllers["initial-state"].makeState(props));
  return {
    controllers,
    render: () => controllers.shell.renderVals(),
    mount: () => controllers.lifecycle.componentDidMount(),
    update: (previousProps, previousState, nextProps) => {
      ui.props = nextProps;
      controllers.lifecycle.componentDidUpdate(previousProps, previousState);
    },
    dispose: () => {
      controllers.lifecycle.componentWillUnmount();
      scheduler.dispose();
    },
  };
}
