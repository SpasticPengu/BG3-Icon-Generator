// README screenshots: headless Edge driven over the DevTools protocol (Node's built-in WebSocket, no packages).
// Each shot loads a page of a running editor, runs its setup script in the page (awaited), then saves a PNG.
//   node research/probes/readme_shots.mjs SHOTS.json OUT_DIR
// SHOTS.json: {"base": "http://127.0.0.1:8791", "width": 1600, "height": 1000, "shots": [{"name", "path", "js", "wait"}]}
// Run the editor with --drafts <empty dir> (its own autosave) so no one's session shows up in the pictures.
import {spawn} from "node:child_process";
import {mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

const [cfgPath, out] = process.argv.slice(2);
const cfg = JSON.parse(readFileSync(cfgPath, "utf8")), W = cfg.width || 1600, H = cfg.height || 1000;
const EDGE = process.env.EDGE || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const port = 9300 + Math.floor(Math.random() * 500), profile = mkdtempSync(join(tmpdir(), "shots-"));
mkdirSync(out, {recursive: true});
const sleep = ms => new Promise(r => setTimeout(r, ms));
const edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, `--window-size=${W},${H}`,
  "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run", "about:blank"], {stdio: "ignore"});
let ws, id = 0;
const pending = new Map();
const send = (method, params = {}, session) => new Promise((ok, no) => {
  const n = ++id;
  pending.set(n, {ok, no});
  ws.send(JSON.stringify({id: n, method, params, ...(session ? {sessionId: session} : {})}));
});
try {
  let ver;
  for (let k = 0; k < 50 && !ver; k++) { await sleep(200); ver = await fetch(`http://127.0.0.1:${port}/json/version`).then(r => r.json()).catch(() => null); }
  if (!ver) throw new Error("Edge didn't open its debugging port");
  ws = new WebSocket(ver.webSocketDebuggerUrl);
  await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = no; });
  ws.onmessage = e => { const m = JSON.parse(e.data); const p = pending.get(m.id); if (p) { pending.delete(m.id); m.error ? p.no(new Error(m.error.message)) : p.ok(m.result); } };
  const {targetId} = await send("Target.createTarget", {url: "about:blank"});
  const {sessionId: s} = await send("Target.attachToTarget", {targetId, flatten: true});
  await send("Page.enable", {}, s);
  await send("Emulation.setDeviceMetricsOverride", {width: W, height: H, deviceScaleFactor: 1, mobile: false}, s);
  for (const shot of cfg.shots) {
    await send("Page.navigate", {url: cfg.base + (shot.path || "/")}, s);
    await sleep(shot.load ?? 9000);                                  // the editor's start-up (data, WebGL) in software GL
    if (shot.js) {
      const r = await send("Runtime.evaluate", {expression: `(async () => { ${shot.js} })()`, awaitPromise: true, returnByValue: true}, s);
      if (r.exceptionDetails) throw new Error(`${shot.name}: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
      if (r.result?.value) console.log(shot.name, "->", r.result.value);
    }
    await sleep(shot.wait ?? 1500);
    const {data} = await send("Page.captureScreenshot", {format: "png", ...(shot.clip ? {clip: {...shot.clip, scale: 1}} : {})}, s);
    writeFileSync(join(out, shot.name + ".png"), Buffer.from(data, "base64"));
    console.log("saved", shot.name);
  }
} finally {
  try { ws?.close(); } catch {}
  edge.kill();
  await sleep(500);
  try { rmSync(profile, {recursive: true, force: true}); } catch {}
}
