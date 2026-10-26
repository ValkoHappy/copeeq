import { cp, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const source = new URL("./src/templates/", import.meta.url);
const output = new URL("../src/foto2word/web/copeeq/", import.meta.url);

export async function renderTemplate(path = "index.html", ancestors = []) {
  if (ancestors.includes(path)) throw new Error(`Recursive template: ${path}`);
  if (path.includes("..") || path.startsWith("/"))
    throw new Error(`Invalid template: ${path}`);
  const file =
    path === "styles/copeeq.css"
      ? new URL("./src/styles/copeeq.css", import.meta.url)
      : new URL(path, source);
  const text = await readFile(file, "utf8");
  const matches = [...text.matchAll(/<!-- include: ([^\s]+) -->/g)];
  let result = text;
  for (const match of matches) {
    result = result.replace(
      match[0],
      await renderTemplate(match[1], [...ancestors, path]),
    );
  }
  return result;
}

export async function buildMockup({ write = true } = {}) {
  const bundle = await build({
    entryPoints: [fileURLToPath(new URL("./src/index.js", import.meta.url))],
    bundle: true,
    write: false,
    format: "iife",
    globalName: "CopeeqMockup",
    target: "es2022",
  });
  const logic =
    bundle.outputFiles[0].text +
    "\nconst Component = CopeeqMockup.createComponent(DCLogic, React);";
  const html = (await renderTemplate()).replace(
    "/* application-bundle */",
    logic,
  );
  if (write) {
    await mkdir(output, { recursive: true });
    await cp(new URL("./public/", import.meta.url), output, {
      recursive: true,
    });
    // Remove the known generated export left by the previous builder.
    await rm(new URL("Copeeq v5.dc.html", output), { force: true });
    await writeFile(new URL("index.html", output), html);
    console.log(
      `Built modular Copeeq mockup (no API): ${fileURLToPath(output)}`,
    );
  }
  return html;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await buildMockup();
