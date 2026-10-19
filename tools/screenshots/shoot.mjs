// Screenshot del README: ogni widget renderizzato con dati inventati in Chrome headless.
// Uso: npm install && npm run shoot   (Google Chrome installato; CHROME_PATH per un percorso diverso)
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import puppeteer from "puppeteer-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const OUT = join(ROOT, "docs/screenshots");
const BUILD = join(HERE, ".build");
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const SCREEN = { width: 1470, height: 918 }; // schermo di riferimento dei pannelli
const WIDGETS = ["cc-panel", "focus-panel", "news-panel", "harlock-panel"];

const fixtures = JSON.parse(execFileSync("/usr/bin/python3", [join(HERE, "fixtures.py")], { encoding: "utf8" }));
mkdirSync(OUT, { recursive: true });
mkdirSync(BUILD, { recursive: true });

// Orologio fermo all'ora dei dati demo, così età e countdown sono quelli previsti.
const clock = `
  (() => {
    const NOW = ${fixtures.now * 1000};
    const Real = Date;
    class Fixed extends Real {
      constructor(...args) { super(...(args.length ? args : [NOW])); }
      static now() { return NOW; }
    }
    window.Date = Fixed;
  })();`;

const page = (body, script = "") => `<!doctype html><html><head><meta charset="utf-8">
<style>html, body { margin: 0; width: 100%; height: 100%; background: transparent; overflow: hidden; }</style>
</head><body>${body}<script>${script}</script></body></html>`;

const bundleWidget = async (name) => {
  const result = await build({
    stdin: {
      contents: `import * as widget from ${JSON.stringify(join(ROOT, name, "widget/index.jsx"))};
                 import { mount } from ${JSON.stringify(join(HERE, "mount.jsx"))};
                 mount(widget);`,
      resolveDir: HERE,
      loader: "jsx",
    },
    bundle: true,
    write: false,
    format: "iife",
    jsx: "automatic",
    loader: { ".jsx": "jsx" },
    alias: { uebersicht: join(HERE, "uebersicht-shim.js") },
    nodePaths: [join(HERE, "node_modules")],
    define: { "process.env.NODE_ENV": '"production"' },
  });
  const output = fixtures[name] ? JSON.stringify(JSON.stringify(fixtures[name])) : "null";
  const file = join(BUILD, `${name}.html`);
  writeFileSync(file, page('<div id="root"></div>', `${clock}\nwindow.__demoOutput = ${output};\n${result.outputFiles[0].text}`));
  return file;
};

// Il desktop: sfondo scuro e i quattro pannelli, ognuno nella sua pagina trasparente sovrapposta.
const desktopPage = (files) => page(`
  <div style="position:fixed; inset:0; background: radial-gradient(ellipse at 70% 20%, #24345e 0%, #0d1220 55%, #05070d 100%);"></div>
  ${files.map((f) => `<iframe src="file://${f}" style="position:fixed; inset:0; width:100%; height:100%; border:0; background:transparent;" allowtransparency="true"></iframe>`).join("")}`);

// Il menu di xbar non si può renderizzare fuori da macOS: lo ridisegno dalle righe del plugin, con lo stile del menu scuro.
const parseLine = (raw) => {
  let depth = 0;
  let text = raw;
  while (text !== "---" && text.startsWith("--")) { depth++; text = text.slice(2); }
  if (text === "---") return { depth, sep: true };
  const [label, params = ""] = text.split(" | ");
  const p = Object.fromEntries(params.split(" ").filter(Boolean).map((kv) => [kv.split("=")[0], kv.slice(kv.indexOf("=") + 1)]));
  return { depth, label, p };
};

const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");

const barPage = (lines) => {
  const items = lines.map(parseLine);
  const [title, ...all] = items;
  const rest = all[0] && all[0].sep ? all.slice(1) : all; // xbar non disegna il separatore sotto il titolo
  const hasChildren = (i) => rest[i + 1] && rest[i + 1].depth > rest[i].depth;
  const row = (it, i) => it.sep ? '<div class="sep"></div>' : `<div class="row" style="${it.p.color ? `color:${it.p.color};` : ""}${it.p.size ? `font-size:${it.p.size}px;` : ""}">
      <span>${escapeHtml(it.label)}</span>${hasChildren(i) ? '<span class="chev">›</span>' : ""}</div>`;
  const top = rest.map((it, i) => (it.depth === 0 ? row(it, i) : "")).join("");
  // Apro il sottomenu della prima epica, per far vedere i ticket raggruppati.
  const epic = rest.findIndex((it) => it.depth === 0 && it.label && it.label.startsWith("● "));
  let sub = "";
  for (let i = epic + 1; i < rest.length && rest[i].depth > 0; i++) if (rest[i].depth === 1) sub += row(rest[i], i);
  const epicRow = rest.slice(0, epic).filter((it) => it.depth === 0 && !it.sep).length;
  return page(`
  <style>
    body { font: 13px -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; color: #e8e8ea;
           background: radial-gradient(ellipse at 70% 20%, #24345e 0%, #0d1220 55%, #05070d 100%); }
    .bar { height: 26px; background: rgba(20, 22, 28, 0.85); display: flex; justify-content: flex-end; align-items: center;
           gap: 14px; padding: 0 14px; font-size: 13px; }
    .bar .item { display: flex; align-items: center; gap: 4px; padding: 1px 6px; border-radius: 5px; }
    .bar .on { background: rgba(255, 255, 255, 0.2); }
    .menu { position: absolute; background: rgba(38, 38, 44, 0.96); border: 0.5px solid rgba(255,255,255,0.15);
            border-radius: 10px; padding: 5px; box-shadow: 0 12px 40px rgba(0,0,0,0.55); min-width: 330px; }
    .row { display: flex; justify-content: space-between; gap: 18px; padding: 3px 10px; border-radius: 5px; white-space: nowrap; }
    .row.hl { background: #2f5fd0; color: #fff !important; }
    .chev { opacity: 0.7; }
    .sep { height: 1px; margin: 5px 10px; background: rgba(255,255,255,0.12); }
  </style>
  <div class="bar">
    <span class="item on" id="harlock"><img src="data:image/png;base64,${title.p.image}" width="20" height="20"><span>${escapeHtml(title.label.trim())}</span></span>
    <span class="item">mar 20 ott  10:40</span>
  </div>
  <div class="menu" id="menu" style="right: 150px; top: 29px;">${top}</div>
  <div class="menu" id="submenu">${sub}</div>
  <script>
    const menu = document.getElementById("menu");
    const rows = menu.querySelectorAll(".row");
    const anchor = rows[${epicRow}];
    anchor.classList.add("hl");
    const sub = document.getElementById("submenu");
    const r = anchor.getBoundingClientRect();
    sub.style.top = (r.top - 5) + "px";
    sub.style.left = (menu.getBoundingClientRect().left - sub.offsetWidth + 4) + "px";
  </script>`);
};

const main = async () => {
  const files = {};
  for (const name of WIDGETS) files[name] = await bundleWidget(name);
  writeFileSync(join(BUILD, "desktop.html"), desktopPage(WIDGETS.map((w) => files[w])));
  writeFileSync(join(BUILD, "bar.html"), barPage(fixtures["harlock-bar"]));

  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--allow-file-access-from-files"] });
  try {
    const tab = await browser.newPage();
    await tab.setViewport({ ...SCREEN, deviceScaleFactor: 2 });
    for (const name of WIDGETS) {
      await tab.goto(`file://${files[name]}`);
      await new Promise((r) => setTimeout(r, 1500));
      const box = await tab.evaluate(() => {
        const r = document.querySelector(".widget > *").getBoundingClientRect();
        return { x: r.left, y: r.top, width: r.width, height: r.height };
      });
      const pad = 28; // spazio per l'alone dei pannelli
      const clip = { x: Math.max(box.x - pad, 0), y: Math.max(box.y - pad, 0) };
      clip.width = Math.min(box.width + 2 * pad, SCREEN.width - clip.x);
      clip.height = Math.min(box.height + 2 * pad, SCREEN.height - clip.y);
      await tab.screenshot({ path: join(OUT, `${name}.png`), clip, omitBackground: true });
      console.log("ok", name);
    }
    await tab.setViewport({ ...SCREEN, deviceScaleFactor: 1 });
    await tab.goto(`file://${join(BUILD, "desktop.html")}`);
    await new Promise((r) => setTimeout(r, 2500));
    await tab.screenshot({ path: join(OUT, "desktop.png") });
    console.log("ok desktop");

    await tab.setViewport({ ...SCREEN, deviceScaleFactor: 2 });
    await tab.goto(`file://${join(BUILD, "bar.html")}`);
    await new Promise((r) => setTimeout(r, 500));
    const clip = await tab.evaluate(() => {
      const boxes = ["menu", "submenu"].map((id) => document.getElementById(id).getBoundingClientRect());
      const left = Math.min(...boxes.map((b) => b.left)) - 20;
      const bottom = Math.max(...boxes.map((b) => b.bottom)) + 20;
      return { x: Math.max(left, 0), y: 0, width: window.innerWidth - Math.max(left, 0), height: bottom };
    });
    await tab.screenshot({ path: join(OUT, "harlock-bar.png"), clip });
    console.log("ok harlock-bar");
  } finally {
    await browser.close();
  }
};

main().catch((error) => { console.error(error); process.exit(1); });
