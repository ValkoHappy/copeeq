import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { buildMockup } from "../build.mjs";

const builtHtml = await buildMockup({ write: false });

async function prototype() {
  const html = builtHtml;
  const script = html.match(
    /<script type="text\/x-dc"[^>]*>([\s\S]*?)<\/script>/,
  )?.[1];
  assert.ok(script);
  class Logic {
    constructor(props) {
      this.props = props;
    }
    setState(patch, done) {
      this.state = {
        ...this.state,
        ...(typeof patch === "function" ? patch(this.state) : patch),
      };
      done?.();
    }
  }
  const intervals = new Map();
  const timeouts = new Map();
  let timerId = 0;
  const network = () => {
    throw new Error("A mockup must not call a network API");
  };
  const context = vm.createContext({
    DCLogic: Logic,
    React: { createRef: () => ({ current: null }) },
    window: {
      innerWidth: 1440,
      innerHeight: 900,
      scrollTo() {},
      addEventListener() {},
      removeEventListener() {},
    },
    document: { querySelector: () => null },
    setTimeout: (fn) => {
      const id = ++timerId;
      timeouts.set(id, () => {
        timeouts.delete(id);
        fn();
      });
      return id;
    },
    clearTimeout: (id) => timeouts.delete(id),
    setInterval: (fn) => {
      intervals.set(++timerId, fn);
      return timerId;
    },
    clearInterval: (id) => intervals.delete(id),
    fetch: network,
    XMLHttpRequest: network,
  });
  for (const file of ["copeeq-data.js", "copeeq-icons.js"]) {
    vm.runInContext(
      await readFile(new URL("../public/" + file, import.meta.url), "utf8"),
      context,
    );
  }
  vm.runInContext(script + "\nthis.Mockup = Component;", context);
  return {
    create: (props) => new context.Mockup(props),
    intervals,
    timeouts,
    context,
  };
}

test("every original screen can compute its view without a backend", async () => {
  const mock = await prototype();
  const routes = [
    "landing",
    "dash",
    "new",
    "processing",
    "result",
    "editor",
    "docs",
    "billing",
    "account",
    "login",
    "pricing",
    "examples",
    "forms",
    "form",
    "faq",
    "business",
    "chistovik",
    "students",
    "security",
    "seo",
    "legal",
    "payok",
    "payfail",
    "notfound",
  ];
  for (const route of routes) {
    const component = mock.create({ startScreen: route });
    assert.doesNotThrow(() => component.renderVals(), route);
  }
});

test("sample conversion, edits and download stay local demo actions", async () => {
  const mock = await prototype();
  const component = mock.create({ startScreen: "result" });
  const values = component.renderVals();
  assert.equal(component.state.cur.status, "ready");
  values.yearUp();
  assert.equal(component.state.cur.shift, 1);
  component.application.controllers.documents.patchCur({
    cmd: "замени 2024 на 2025",
  });
  component.application.controllers.editor.applyCmd();
  assert.equal(component.state.cur.reps[0][0], "2024");
  assert.equal(component.state.cur.reps[0][1], "2025");
  component.state.credits = { free: 100, sub: 0, pack: 0 };
  component.application.controllers.downloads.download("docx", true);
  assert.match(component.state.toast.text, /Скачивание/);
});

test("displayed page rates match the demo charge", async () => {
  const mock = await prototype();
  const component = mock.create({ startScreen: "new" });
  for (const [mode, hand, rate] of [
    ["copy", false, 5],
    ["clean", false, 8],
    ["copy", true, 10],
  ]) {
    component.application.controllers.upload.setUp({
      mode,
      hand: true,
      pages: [{ id: "rate", page: "zayav", hand }],
    });
    assert.equal(
      component.application.controllers["pricing-policy"].costOf(
        component.state.up.pages,
        component.state.up,
      ),
      rate,
    );
    assert.match(
      component.renderVals().costLine,
      new RegExp("× " + rate + ".*= " + rate),
    );
  }
});

test("feature ports support demo login, payment, editing history and disposal", async () => {
  const mock = await prototype();
  const component = mock.create({ startScreen: "result" });
  const features = component.application.controllers;
  const initial = component.state.cur.values;
  const field = component.renderVals().fieldRows[0];
  field.onChange({ target: { value: "Тестовое значение" } });
  assert.equal(component.state.cur.values[field.key], "Тестовое значение");
  features.editor.undo();
  assert.equal(component.state.cur.values, initial);
  features.editor.redo();
  assert.equal(component.state.cur.values[field.key], "Тестовое значение");

  component.state.modal = "buy";
  component.state.buy.pick = "start";
  component.renderVals().payNow();
  assert.equal(component.state.buy.paying, true);
  // Run the payment delay, with no real payment provider or network.
  for (const fn of [...mock.timeouts.values()]) fn();
  assert.equal(component.state.buy.paying, false);
  assert.ok(component.state.credits.pack > 10);

  for (const modal of ["login", "buy", "sig", "bad", "warn", "del", "delacc"]) {
    component.state.modal = modal;
    assert.doesNotThrow(() => component.renderVals(), modal);
  }
  features.authentication.loginDone("demo@example.test");
  assert.equal(component.state.email, "demo@example.test");
  component.application.dispose();
  assert.equal(mock.timeouts.size, 0);
  assert.equal(mock.intervals.size, 0);
});

test("demo processing completes through its injected plan and document ports", async () => {
  const mock = await prototype();
  const component = mock.create({ startScreen: "processing" });
  const features = component.application.controllers;
  features.processing.runProc();
  component.state.proc.t0 = Date.now() - 120000;
  for (const callback of [...mock.intervals.values()]) callback();
  assert.equal(component.state.proc.done, true);
  for (const callback of [...mock.timeouts.values()]) callback();
  assert.equal(component.state.route, "result");
  assert.equal(component.state.cur.status, "ready");
  assert.doesNotThrow(() => component.renderVals());
  component.application.dispose();
});

test("original document component and all raster assets referenced by templates exist", async () => {
  const html = builtHtml;
  const references = [...html.matchAll(/(?:src=["'])(assets\/[^"']+)/g)].map(
    (match) => match[1],
  );
  for (const file of new Set([
    ...references,
    "DocSheet.dc.html",
    "support.js",
    "copeeq-data.js",
    "copeeq-icons.js",
  ])) {
    assert.ok(
      (await readFile(new URL("../public/" + file, import.meta.url))).length,
      file,
    );
  }
});
