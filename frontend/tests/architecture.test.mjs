import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";

test("domain rules stay independent of DOM, state and UI controllers", async () => {
  for (const file of await readdir(
    new URL("../src/domain/", import.meta.url),
  )) {
    const code = await readFile(
      new URL("../src/domain/" + file, import.meta.url),
      "utf8",
    );
    assert.doesNotMatch(
      code,
      /\b(?:window|document|React|DCLogic)\.|this\.(?:store|ui)\b|\.\.\/controllers\//,
      file,
    );
  }
});

test("feature controllers use ports rather than importing each other or inheriting a shared god class", async () => {
  for (const file of await readdir(
    new URL("../src/controllers/", import.meta.url),
  )) {
    const code = await readFile(
      new URL("../src/controllers/" + file, import.meta.url),
      "utf8",
    );
    assert.doesNotMatch(
      code,
      /from\s+["'](?:\.\/|.*controllers\/)|\bextends\b|controllers\[/,
      file,
    );
  }
  const adapter = await readFile(
    new URL("../src/index.js", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(adapter, /costOf|payNow|addFiles|applyCmd/);
});
