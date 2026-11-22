import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";

const here = new URL(".", import.meta.url);
const frontendDist = new URL("../dist/", here);
const output = new URL("../../dist/server/", here);
const entries = ["/index.html", ...(await readdir(new URL("assets/", frontendDist))).map((name) => `/assets/${name}`)];
const types = { html: "text/html", js: "text/javascript", css: "text/css" };
const assets = {};
for (const path of entries) {
  const type = types[path.split(".").pop()];
  if (!type) throw new Error(`Unsupported asset type: ${path}`);
  assets[path] = { type: `${type}; charset=utf-8`, body: await readFile(new URL(path.slice(1), frontendDist), "utf8") };
}
await mkdir(output, { recursive: true });
const worker = await readFile(new URL("worker.mjs", here), "utf8");
await writeFile(new URL("index.js", output), `const assets = ${JSON.stringify(assets)};\n${worker}`);
