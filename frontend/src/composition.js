import { AccountController } from "./controllers/account.js";
import { AuthenticationController } from "./controllers/authentication.js";
import { BillingController } from "./controllers/billing.js";
import { BusinessController } from "./controllers/business.js";
import { ContentController } from "./controllers/content.js";
import { DashboardController } from "./controllers/dashboard.js";
import { DocumentListController } from "./controllers/document-list.js";
import { DocumentsController } from "./controllers/documents.js";
import { DownloadsController } from "./controllers/downloads.js";
import { EditorViewController } from "./controllers/editor-view.js";
import { EditorController } from "./controllers/editor.js";
import { ExamplesController } from "./controllers/examples.js";
import { FaqController } from "./controllers/faq.js";
import { FormsController } from "./controllers/forms.js";
import { InitialStateController } from "./controllers/initial-state.js";
import { LandingCatalogController } from "./controllers/landing-catalog.js";
import { LandingComparisonController } from "./controllers/landing-comparison.js";
import { LandingEconomyController } from "./controllers/landing-economy.js";
import { LandingEditorDemoController } from "./controllers/landing-editor-demo.js";
import { LandingFeaturesController } from "./controllers/landing-features.js";
import { LandingHandwritingController } from "./controllers/landing-handwriting.js";
import { LandingUploadController } from "./controllers/landing-upload.js";
import { LandingController } from "./controllers/landing.js";
import { LegalController } from "./controllers/legal.js";
import { LifecycleController } from "./controllers/lifecycle.js";
import { ModalController } from "./controllers/modal.js";
import { NavigationController } from "./controllers/navigation.js";
import { NotificationsController } from "./controllers/notifications.js";
import { PaymentResultController } from "./controllers/payment-result.js";
import { PricingController } from "./controllers/pricing.js";
import { ProcessingViewController } from "./controllers/processing-view.js";
import { ProcessingController } from "./controllers/processing.js";
import { RefundController } from "./controllers/refund.js";
import { ResultViewController } from "./controllers/result-view.js";
import { ReviewPanelController } from "./controllers/review-panel.js";
import { ShellController } from "./controllers/shell.js";
import { SignatureController } from "./controllers/signature.js";
import { UploadController } from "./controllers/upload.js";
import { ViewerController } from "./controllers/viewer.js";
import { WalletController } from "./controllers/wallet.js";
import { CreditPolicy } from "./domain/credit-policy.js";
import { DocumentFactory } from "./domain/document-factory.js";
import { PricingPolicy } from "./domain/pricing-policy.js";
import { ProcessingPlan } from "./domain/processing-plan.js";

/** Composition root: explicit feature ports and their implementations. */
export function createControllers(store, ui, scheduler, callbacks) {
  const controllers = {};
  controllers["account"] = new AccountController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["authentication"] = new AuthenticationController(
    store,
    ui,
    {
      download: (...args) => controllers["downloads"].download(...args),
      go: (...args) => controllers["navigation"].go(...args),
      op: (...args) => controllers["wallet"].op(...args),
      pickFile: (...args) => controllers["upload"].pickFile(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["billing"] = new BillingController(
    store,
    ui,
    {
      ico: (...args) => controllers["shell"].ico(...args),
      payNow: (...args) => controllers["wallet"].payNow(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
      total: (...args) => controllers["wallet"].total(...args),
    },
    scheduler.scope(),
  );
  controllers["business"] = new BusinessController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["content"] = new ContentController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      ico: (...args) => controllers["shell"].ico(...args),
    },
    scheduler.scope(),
  );
  controllers["dashboard"] = new DashboardController(
    store,
    ui,
    {
      doubtsOf: (...args) => controllers["documents"].doubtsOf(...args),
      go: (...args) => controllers["navigation"].go(...args),
      goEditor: (...args) => controllers["navigation"].goEditor(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      openDocsDoc: (...args) => controllers["documents"].openDocsDoc(...args),
      total: (...args) => controllers["wallet"].total(...args),
    },
    scheduler.scope(),
  );
  controllers["document-list"] = new DocumentListController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      openDocsDoc: (...args) => controllers["documents"].openDocsDoc(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["documents"] = new DocumentsController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      newDoc: (...args) => controllers["document-factory"].newDoc(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["downloads"] = new DownloadsController(
    store,
    ui,
    {
      doubtsOf: (...args) => controllers["documents"].doubtsOf(...args),
      op: (...args) => controllers["wallet"].op(...args),
      patchCur: (...args) => controllers["documents"].patchCur(...args),
      setDoc: (...args) => controllers["documents"].setDoc(...args),
      spend: (...args) => controllers["wallet"].spend(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
      total: (...args) => controllers["wallet"].total(...args),
    },
    scheduler.scope(),
  );
  controllers["editor-view"] = new EditorViewController(
    store,
    ui,
    {
      doubtsOf: (...args) => controllers["documents"].doubtsOf(...args),
      edOnField: (...args) => controllers["editor"].edOnField(...args),
      firstSigLine: (...args) => controllers["signature"].firstSigLine(...args),
      go: (...args) => controllers["navigation"].go(...args),
      patchCur: (...args) => controllers["documents"].patchCur(...args),
      redo: (...args) => controllers["editor"].redo(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
      undo: (...args) => controllers["editor"].undo(...args),
    },
    scheduler.scope(),
  );
  controllers["editor"] = new EditorController(
    store,
    ui,
    {
      patchCur: (...args) => controllers["documents"].patchCur(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["examples"] = new ExamplesController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["faq"] = new FaqController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
    },
    scheduler.scope(),
  );
  controllers["forms"] = new FormsController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["initial-state"] = new InitialStateController(
    store,
    ui,
    {
      newDoc: (...args) => controllers["document-factory"].newDoc(...args),
      samplePages: (...args) =>
        controllers["document-factory"].samplePages(...args),
    },
    scheduler.scope(),
  );
  controllers["landing-catalog"] = new LandingCatalogController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      planTiles: (...args) => controllers["wallet"].planTiles(...args),
      setL: (...args) => controllers["landing"].setL(...args),
    },
    scheduler.scope(),
  );
  controllers["landing-comparison"] = new LandingComparisonController(
    store,
    ui,
    {
      setL: (...args) => controllers["landing"].setL(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["landing-economy"] = new LandingEconomyController(
    store,
    ui,
    {
      ico: (...args) => controllers["shell"].ico(...args),
      setL: (...args) => controllers["landing"].setL(...args),
    },
    scheduler.scope(),
  );
  controllers["landing-editor-demo"] = new LandingEditorDemoController(
    store,
    ui,
    {
      setL: (...args) => controllers["landing"].setL(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["landing-features"] = new LandingFeaturesController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      setL: (...args) => controllers["landing"].setL(...args),
    },
    scheduler.scope(),
  );
  controllers["landing-handwriting"] = new LandingHandwritingController(
    store,
    ui,
    {
      ico: (...args) => controllers["shell"].ico(...args),
      setL: (...args) => controllers["landing"].setL(...args),
    },
    scheduler.scope(),
  );
  controllers["landing-upload"] = new LandingUploadController(
    store,
    ui,
    {
      addFiles: (...args) => controllers["upload"].addFiles(...args),
      pickFile: (...args) => controllers["upload"].pickFile(...args),
    },
    scheduler.scope(),
  );
  controllers["landing"] = new LandingController(
    store,
    ui,
    {
      catalogLandingVals: (...args) =>
        controllers["landing-catalog"].catalogLandingVals(...args),
      comparisonLandingVals: (...args) =>
        controllers["landing-comparison"].comparisonLandingVals(...args),
      economyLandingVals: (...args) =>
        controllers["landing-economy"].economyLandingVals(...args),
      editorDemoLandingVals: (...args) =>
        controllers["landing-editor-demo"].editorDemoLandingVals(...args),
      featuresLandingVals: (...args) =>
        controllers["landing-features"].featuresLandingVals(...args),
      handwritingLandingVals: (...args) =>
        controllers["landing-handwriting"].handwritingLandingVals(...args),
      uploadLandingVals: (...args) =>
        controllers["landing-upload"].uploadLandingVals(...args),
    },
    scheduler.scope(),
  );
  controllers["legal"] = new LegalController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
    },
    scheduler.scope(),
  );
  controllers["lifecycle"] = new LifecycleController(
    store,
    ui,
    {
      closeModal: (...args) => controllers["navigation"].closeModal(...args),
      handlePaste: (...args) => controllers["upload"].handlePaste(...args),
      makeState: (...args) => controllers["initial-state"].makeState(...args),
      runProc: (...args) => controllers["processing"].runProc(...args),
      stopProcessing: (...args) =>
        controllers["processing"].stopProcessing(...args),
      total: (...args) => controllers["wallet"].total(...args),
    },
    scheduler.scope(),
  );
  controllers["modal"] = new ModalController(
    store,
    ui,
    {
      closeModal: (...args) => controllers["navigation"].closeModal(...args),
      go: (...args) => controllers["navigation"].go(...args),
    },
    scheduler.scope(),
  );
  controllers["navigation"] = new NavigationController(
    store,
    ui,
    {
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["notifications"] = new NotificationsController(
    store,
    ui,
    {},
    scheduler.scope(),
  );
  controllers["payment-result"] = new PaymentResultController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      total: (...args) => controllers["wallet"].total(...args),
    },
    scheduler.scope(),
  );
  controllers["pricing"] = new PricingController(
    store,
    ui,
    {
      go: (...args) => controllers["navigation"].go(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      planTiles: (...args) => controllers["wallet"].planTiles(...args),
    },
    scheduler.scope(),
  );
  controllers["processing-view"] = new ProcessingViewController(
    store,
    ui,
    {
      costOf: (...args) => controllers["pricing-policy"].costOf(...args),
      finishProc: (...args) => controllers["processing"].finishProc(...args),
      go: (...args) => controllers["navigation"].go(...args),
      matchOf: (...args) => controllers["processing-plan"].matchOf(...args),
      pageState: (...args) => controllers["processing-plan"].pageState(...args),
      pickFile: (...args) => controllers["upload"].pickFile(...args),
      procPlan: (...args) =>
        controllers["processing-plan"].procPlan(args[0], store.state.up),
      runProc: (...args) => controllers["processing"].runProc(...args),
      setDoc: (...args) => controllers["documents"].setDoc(...args),
    },
    scheduler.scope(),
  );
  controllers["processing"] = new ProcessingController(
    store,
    ui,
    {
      allPages: (...args) => controllers["upload"].allPages(...args),
      doubtsOf: (...args) => controllers["documents"].doubtsOf(...args),
      newDoc: (...args) => controllers["document-factory"].newDoc(...args),
      pageState: (...args) => controllers["processing-plan"].pageState(...args),
      pickFile: (...args) => controllers["upload"].pickFile(...args),
      procPlan: (...args) =>
        controllers["processing-plan"].procPlan(args[0], store.state.up),
      setDoc: (...args) => controllers["documents"].setDoc(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["refund"] = new RefundController(
    store,
    ui,
    {
      op: (...args) => controllers["wallet"].op(...args),
      setDoc: (...args) => controllers["documents"].setDoc(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["result-view"] = new ResultViewController(
    store,
    ui,
    {
      applyCmd: (...args) => controllers["editor"].applyCmd(...args),
      defaultVal: (...args) => controllers["documents"].defaultVal(...args),
      doubtsOf: (...args) => controllers["documents"].doubtsOf(...args),
      download: (...args) => controllers["downloads"].download(...args),
      edOnField: (...args) => controllers["editor"].edOnField(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      onScrollE: (...args) => controllers["viewer"].onScrollE(...args),
      onScrollP: (...args) => controllers["viewer"].onScrollP(...args),
      patchCur: (...args) => controllers["documents"].patchCur(...args),
      scrollToPage: (...args) => controllers["viewer"].scrollToPage(...args),
      secVals: (...args) => controllers["review-panel"].secVals(...args),
      setDoc: (...args) => controllers["documents"].setDoc(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
      total: (...args) => controllers["wallet"].total(...args),
    },
    scheduler.scope(),
  );
  controllers["review-panel"] = new ReviewPanelController(
    store,
    ui,
    {
      download: (...args) => controllers["downloads"].download(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      patchCur: (...args) => controllers["documents"].patchCur(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["shell"] = new ShellController(
    store,
    ui,
    {
      closeToast: (...args) => controllers["notifications"].closeToast(...args),
      doubtsOf: (...args) => controllers["documents"].doubtsOf(...args),
      go: (...args) => controllers["navigation"].go(...args),
      goEditor: (...args) => controllers["navigation"].goEditor(...args),
      landingVals: (...args) => controllers["landing"].landingVals(...args),
      modalValues: (...args) => callbacks.modalValues(...args),
      onFile: (...args) => controllers["upload"].onFile(...args),
      openDocsDoc: (...args) => controllers["documents"].openDocsDoc(...args),
      routeValues: (...args) => callbacks.routeValues(...args),
      toastAction: (...args) =>
        controllers["notifications"].toastAction(...args),
      total: (...args) => controllers["wallet"].total(...args),
    },
    scheduler.scope(),
  );
  controllers["signature"] = new SignatureController(
    store,
    ui,
    {
      patchCur: (...args) => controllers["documents"].patchCur(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
    },
    scheduler.scope(),
  );
  controllers["upload"] = new UploadController(
    store,
    ui,
    {
      costOf: (...args) => controllers["pricing-policy"].costOf(...args),
      go: (...args) => controllers["navigation"].go(...args),
      ico: (...args) => controllers["shell"].ico(...args),
      needAuth: (...args) => controllers["authentication"].needAuth(...args),
      samplePages: (...args) =>
        controllers["document-factory"].samplePages(...args),
      startProc: (...args) => controllers["processing"].startProc(...args),
      toast: (...args) => controllers["notifications"].toast(...args),
      total: (...args) => controllers["wallet"].total(...args),
    },
    scheduler.scope(),
  );
  controllers["viewer"] = new ViewerController(
    store,
    ui,
    {
      patchCur: (...args) => controllers["documents"].patchCur(...args),
    },
    scheduler.scope(),
  );
  controllers["wallet"] = new WalletController(
    store,
    ui,
    {
      balance: (...args) => controllers["credit-policy"].balance(...args),
      chargeCredits: (...args) =>
        controllers["credit-policy"].chargeCredits(...args),
      download: (...args) => controllers["downloads"].download(...args),
      go: (...args) => controllers["navigation"].go(...args),
      ico: (...args) => controllers["shell"].ico(...args),
    },
    scheduler.scope(),
  );
  controllers["credit-policy"] = new CreditPolicy({});
  controllers["document-factory"] = new DocumentFactory({
    costOf: (...args) => controllers["pricing-policy"].costOf(...args),
  });
  controllers["pricing-policy"] = new PricingPolicy({});
  controllers["processing-plan"] = new ProcessingPlan({});
  return controllers;
}
