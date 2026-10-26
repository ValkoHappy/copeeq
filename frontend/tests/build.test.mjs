import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";

test("mockup build preserves the entire original and has no backend integration", async () => {
  execFileSync(process.execPath, ["build.mjs"], {
    cwd: new URL("../", import.meta.url),
  });
  const built = await readFile(
    new URL("../../src/foto2word/web/copeeq/index.html", import.meta.url),
    "utf8",
  );
  const contract = JSON.parse(
    await readFile(new URL("./visual-contract.json", import.meta.url), "utf8"),
  );
  const markup = built
    .replace(/<script type="text\/x-dc"[\s\S]*?<\/script>/, "")
    .replace(/<style>[\s\S]*?<\/style>/, "")
    .replace(/\s+/g, "");
  assert.equal(
    createHash("sha256").update(markup).digest("hex"),
    contract.markupSha256,
  );
  assert.ok(!built.includes("CopeeqApplication"));
  assert.ok(!built.includes("BackendSheet"));
  assert.ok(!built.includes("/api/"));
  assert.ok(!built.includes("./api.js"));
});
