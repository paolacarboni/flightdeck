import { css, run } from "uebersicht";

// Variante «cockpit» del pannello cc-panel: stessi dati e azioni di index.jsx, con l'aspetto di un
// display multifunzione di cabina. Colori con il significato dell'avionica: verde = in corso,
// ambra = richiede attenzione, magenta = focus, ciano = informazione e consigli.

const CLI = '"$HOME/.local/bin/cc-panel"';
// true = dati inventati (cc-panel board --demo): per provare il pannello senza Jira.
const DEMO = false;
export const command = `${CLI} board --json${DEMO ? " --demo" : ""}`;
export const refreshFrequency = 5 * 60 * 1000;

const ISSUE_KEY = /^[A-Z][A-Z0-9]{1,9}-[0-9]+$/;
const SESSION_ID = /^[0-9a-f-]{8,64}$/;
const STORAGE_KEY = "cc-panel.cockpit.open";
const ADVISORY = "__advisory__";
const NO_EPIC = "__no_epic__";

const C = {
  bezel: "#151a24",
  bezelEdge: "#262d3b",
  screen: "#03060a",
  white: "#e9eef5",
  dim: "rgba(233, 238, 245, 0.5)",
  faint: "rgba(233, 238, 245, 0.28)",
  green: "#49f07c",
  cyan: "#56e3ff",
  magenta: "#ff5ad8",
  amber: "#ffb84a",
  red: "#ff6b5e",
  atmosphere: "rgba(84, 120, 255, 0.35)",
};
const MONO = `"SF Mono", "JetBrains Mono", Menlo, monospace`;

// ------------------------------------------------------------------ stato

const loadOpen = () => {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY));
    return saved && typeof saved === "object" ? saved : {};
  } catch (e) {
    return {};
  }
};

const saveOpen = (open) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(open));
  } catch (e) {
    // localStorage non disponibile: lo stato resta solo in memoria.
  }
};

// Il pannello è disegnato per lo schermo del portatile (1470×918 punti sotto la barra dei menu): su
// un altro schermo si scala sul lato che limita (l'altezza, sull'ultrawide) e occupa la stessa
// porzione di schermo. Margine dall'angolo e dimensioni sono in punti del portatile e si
// scalano con il pannello.
const REF_SCREEN = { w: 1470, h: 918 };
// Griglia comune ai quattro pannelli, in punti del portatile: colonne larghe 470 ai lati, 34 dai
// bordi e 16 tra le righe. Riga alta 479 (cc-panel, news-panel), riga bassa 355 (Harlock a 470 di
// larghezza, focus-panel). Posizione fissa: i pannelli non si trascinano.
const MARGIN = { x: 34, y: 34 }; // dall'angolo di className; negativo verso sinistra o verso l'alto
const HEIGHT = 479;
const screenScale = () => Math.min(window.innerWidth / REF_SCREEN.w, window.innerHeight / REF_SCREEN.h);

const placement = () => {
  const s = screenScale();
  return {
    transform: `translate(${MARGIN.x * s}px, ${MARGIN.y * s}px) scale(${s})`,
    transformOrigin: "top left",
    height: HEIGHT,
  };
};

// Ricalcola la scala quando cambia lo schermo (monitor collegato o scollegato). Il gestore sta su
// window perché i widget condividono la pagina e un ricaricamento rivaluta il modulo.
const followScreen = (dispatch) => {
  window.removeEventListener("resize", window.ccPanelResize);
  window.ccPanelResize = () => dispatch({ type: "RESIZE" });
  window.addEventListener("resize", window.ccPanelResize);
};

export const initialState = { data: null, open: loadOpen(), showAll: {}, loading: false, toast: null };

const parse = (output) => {
  try {
    return JSON.parse(output);
  } catch (e) {
    return { epics: [], noEpic: [], summary: {}, error: "Risposta non valida da cc-panel" };
  }
};

export const updateState = (event, prev) => {
  switch (event.type) {
    case "UB/COMMAND_RAN":
      if (event.error) {
        return { ...prev, loading: false, data: { ...(prev.data || { epics: [], noEpic: [], summary: {} }), error: String(event.error), stale: true } };
      }
      return { ...prev, loading: false, data: parse(event.output) };
    case "TOGGLE": {
      const open = { ...prev.open, [event.key]: !prev.open[event.key] };
      saveOpen(open);
      return { ...prev, open };
    }
    case "SHOW_ALL":
      return { ...prev, showAll: { ...prev.showAll, [event.key]: !prev.showAll[event.key] } };
    case "MENU":
      return { ...prev, menuFor: prev.menuFor === event.sessionId ? null : event.sessionId };
    case "RESIZE":
      return { ...prev };
    case "LOADING":
      return { ...prev, loading: true };
    case "TOAST":
      return { ...prev, toast: event.toast };
    default:
      return prev;
  }
};

// ------------------------------------------------------------------ azioni

const shellQuote = (text) => `'${String(text).replace(/'/g, `'\\''`)}'`;
const issueUrl = (base, key) => (ISSUE_KEY.test(key) ? `${base}/browse/${key}` : base);
const openUrl = (url) => run(`open ${shellQuote(url)}`);

const toast = (dispatch, text, kind) => {
  dispatch({ type: "TOAST", toast: { text, kind } });
  setTimeout(() => dispatch({ type: "TOAST", toast: null }), kind === "error" ? 7000 : 3500);
};

const refresh = (dispatch) => {
  dispatch({ type: "LOADING" });
  run(command)
    .then((output) => dispatch({ type: "UB/COMMAND_RAN", output }))
    .catch((error) => dispatch({ type: "UB/COMMAND_RAN", error }));
};

const cli = (dispatch, args, pending, done, refreshAfter) => {
  toast(dispatch, pending, "info");
  run(`${CLI} ${args} 2>&1; echo "exit:$?"`).then((output) => {
    const ok = /exit:0\s*$/.test(output);
    const lines = output.replace(/exit:\d+\s*$/, "").trim().split("\n");
    toast(dispatch, ok ? done || lines[lines.length - 1] : lines[lines.length - 1], ok ? "ok" : "error");
    if (ok && refreshAfter) refresh(dispatch);
  });
};

const resume = (dispatch, key) => ISSUE_KEY.test(key) && cli(dispatch, `start ${key} --auto`, `AVVIO ${key}…`);
const openFolder = (dispatch, path) => cli(dispatch, `open ${shellQuote(path)}`, "APRO IL TERMINALE…", "TERMINALE APERTO");
const validIds = (ids) => ids.filter((sid) => SESSION_ID.test(sid));
const ignore = (dispatch, ids) =>
  validIds(ids).length && cli(dispatch, `ignore ${validIds(ids).join(" ")}`, "SCARTO…", "PROPOSTA SCARTATA", true);
const track = (dispatch, ids, epic, title, menuKey) => {
  const sessions = validIds(ids).join(" ");
  if (!sessions) return;
  if (menuKey) dispatch({ type: "MENU", sessionId: menuKey });
  const summary = ` --summary ${shellQuote(title)}`;
  if (epic === null) cli(dispatch, `track ${sessions} --new-epic${summary}`, "CREO L'EPICA SU JIRA…", null, true);
  else if (ISSUE_KEY.test(epic)) cli(dispatch, `track ${sessions} --epic ${epic}${summary}`, `CREO IL TASK IN ${epic}…`, null, true);
};

// ------------------------------------------------------------------ stile

export const className = `
  top: 0;
  left: 0;
  width: 470px;
  font-family: ${MONO};
  color: ${C.white};
  -webkit-font-smoothing: antialiased;
  font-feature-settings: "tnum";
`;

// Cornice dello strumento: grafite-blu con il bagliore dell'atmosfera dello sfondo.
const bezel = css`
  background: linear-gradient(180deg, #1b2130, ${C.bezel});
  border: 1px solid ${C.bezelEdge};
  border-radius: 18px;
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.6), 0 0 28px ${C.atmosphere}, 0 24px 60px rgba(0, 0, 0, 0.55),
    inset 0 1px 0 rgba(255, 255, 255, 0.07);
`;
const bezelRow = css`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 4px 8px;
  font-size: 9.5px;
  letter-spacing: 1.6px;
  color: rgba(233, 238, 245, 0.55);
  text-transform: uppercase;
`;
const screw = css`
  width: 7px;
  height: 7px;
  border-radius: 7px;
  background: radial-gradient(circle at 35% 35%, #5a6273, #232833);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.5);
  flex-shrink: 0;
`;
const screen = css`
  position: relative;
  background: radial-gradient(ellipse at 50% 0%, #07101c 0%, ${C.screen} 60%);
  border-radius: 8px;
  border: 1px solid #000;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04), inset 0 0 40px rgba(0, 0, 0, 0.9);
  padding: 8px 10px 10px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  &::-webkit-scrollbar { width: 0; }
`;
const annunciators = css`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border: 1px solid rgba(233, 238, 245, 0.18);
  margin-bottom: 4px;
`;
const annunciator = css`
  text-align: center;
  padding: 4px 2px 3px;
  font-size: 9.5px;
  letter-spacing: 1px;
  border-left: 1px solid rgba(233, 238, 245, 0.18);
  &:first-child { border-left: 0; }
`;
const annunciatorValue = css`
  display: block;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0;
  margin-top: 1px;
`;
const epicRow = css`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 4px;
  cursor: pointer;
  border-radius: 3px;
  &:hover { background: rgba(86, 227, 255, 0.07); }
`;
const label = css`
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
`;
const tag = css`
  font-size: 10.5px;
  flex-shrink: 0;
`;
const detail = css`
  margin: 0 0 6px 18px;
  padding-left: 8px;
  border-left: 1px dashed rgba(86, 227, 255, 0.25);
`;
const itemRow = css`
  position: relative;
  display: flex;
  gap: 7px;
  padding: 4px 4px;
  font-size: 11.5px;
  line-height: 1.35;
  border-radius: 3px;
  &:hover { background: rgba(255, 255, 255, 0.05); }
  &:hover .keys { opacity: 1; }
`;
const itemText = css`
  flex: 1;
  min-width: 0;
`;
const oneLine = css`
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;
const softkeys = css`
  position: absolute;
  right: 2px;
  top: 2px;
  display: flex;
  gap: 4px;
  padding-left: 14px;
  background: linear-gradient(90deg, rgba(3, 6, 10, 0), ${C.screen} 14px);
  opacity: 0;
  transition: opacity 0.12s;
`;
const softkey = css`
  font-size: 9.5px;
  letter-spacing: 1px;
  padding: 2px 6px;
  border: 1px solid currentColor;
  border-radius: 2px;
  cursor: pointer;
  white-space: nowrap;
  &:hover { background: rgba(255, 255, 255, 0.1); }
`;
const sectionLabel = css`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  letter-spacing: 1.6px;
  color: ${C.dim};
  margin: 8px 0 2px;
  &::after { content: ""; flex: 1; border-top: 1px solid rgba(233, 238, 245, 0.14); }
`;
const link = css`
  font-size: 10px;
  letter-spacing: 1px;
  color: ${C.cyan};
  cursor: pointer;
  padding: 3px 4px;
  display: inline-block;
  &:hover { text-decoration: underline; }
`;
const menu = css`
  margin: 2px 0 6px 14px;
  border: 1px solid rgba(86, 227, 255, 0.35);
  padding: 2px;
`;
const menuItem = css`
  font-size: 11px;
  padding: 4px 6px;
  cursor: pointer;
  color: ${C.cyan};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  &:hover { background: rgba(86, 227, 255, 0.12); }
`;
const hardkeys = css`
  display: flex;
  gap: 8px;
  padding: 10px 2px 0;
  align-items: center;
`;
const hardkey = css`
  font-size: 9.5px;
  letter-spacing: 1.4px;
  color: rgba(233, 238, 245, 0.78);
  padding: 6px 10px;
  border-radius: 5px;
  cursor: pointer;
  background: linear-gradient(180deg, #2b3243, #1b2030);
  border: 1px solid #0b0e14;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 1px 0 rgba(0, 0, 0, 0.6);
  user-select: none;
  &:active { transform: translateY(1px); box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.6); }
  &:hover { color: #fff; }
`;
const clock = css`
  margin-left: auto;
  font-size: 13px;
  color: ${C.green};
  letter-spacing: 1px;
  text-shadow: 0 0 6px rgba(73, 240, 124, 0.45);
`;
const toastLine = css`
  margin-top: 8px;
  padding: 5px 6px;
  font-size: 11px;
  letter-spacing: 0.4px;
  border: 1px solid currentColor;
`;
const glow = (color) => ({ color, textShadow: `0 0 6px ${color}55` });

// ------------------------------------------------------------------ strumenti

const isWaiting = (item) => item.session && item.session.state === "open" && item.session.status === "waiting";
const isStale = (item) => item.session && item.session.state === "open" && item.session.staleDays;
const pct = (progress) => {
  const total = progress ? progress.done + progress.indeterminate + progress.new : 0;
  return total ? progress.done / total : null;
};
const stripEmoji = (text) => (text || "").replace(/^(\p{Extended_Pictographic}[️‍\p{Extended_Pictographic}]*)\s*/u, "");

// Arco del navigatore: ogni epica è un waypoint posizionato sulla sua percentuale di completamento
// (sinistra 0%, destra 100%). Magenta = epica in focus, ambra = una sessione aspetta, ciano = le altre.
const ARC_HEIGHT = 146;
const LABEL_GAP_DEG = 13;
const SWEEP_SECONDS = 6;
const TRAIL_DEG = 24;
const TRAIL_SLICES = 12;
// Fascio e waypoint sono livelli HTML animati con CSS: WebKit li muove sulla GPU. Con le animazioni
// SMIL dentro l'SVG ridisegnava tutto l'arco a ogni fotogramma (~35% di CPU).
// cc-sweep va dall'estremo sinistro dell'arco (-55°) a quello destro (55°) più la scia.
const RADAR_KEYFRAMES = `
  @keyframes cc-sweep { from { transform: rotate(-55deg); } to { transform: rotate(${55 + TRAIL_DEG}deg); } }
  @keyframes cc-ping { 0% { transform: scale(1); } 4% { transform: scale(1.625); } 18%, 100% { transform: scale(1); } }
  @keyframes cc-ping-fill { 0% { opacity: 0; } 4% { opacity: 0.7; } 18%, 100% { opacity: 0; } }
`;
// Come per SMIL, tutte le animazioni partono dall'origine della pagina: i waypoint aggiunti dopo
// restano in fase con il fascio.
const alignToPageStart = (el) => {
  if (el) el.getAnimations({ subtree: true }).forEach((a) => { a.startTime = 0; });
};

// Con «Riduci movimento» attivo in macOS le animazioni restano ferme.
const reducedMotion = () => {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (e) {
    return false;
  }
};

const NavArc = ({ epics, focusKey }) => {
  const animate = !reducedMotion();
  const width = 446;
  const cx = width / 2;
  const cy = 236;
  const r = 208;
  const start = -55;
  const end = 55;
  const point = (deg, radius) => {
    const rad = (deg * Math.PI) / 180;
    return [cx + radius * Math.sin(rad), cy - radius * Math.cos(rad)];
  };
  const ticks = [];
  const step = (end - start) / 20;
  for (let deg = start; deg <= end + 0.1; deg += step) {
    const major = Math.round((deg - start) / step) % 5 === 0;
    const [x1, y1] = point(deg, r);
    const [x2, y2] = point(deg, r - (major ? 9 : 5));
    ticks.push(<line key={deg} x1={x1} y1={y1} x2={x2} y2={y2} stroke={C.white} strokeOpacity={major ? 0.7 : 0.35} strokeWidth="1" />);
  }
  const labels = [0, 25, 50, 75, 100].map((value) => {
    const [x, y] = point(start + ((end - start) * value) / 100, r + 9);
    return <text key={value} x={x} y={y + 3} fill={C.white} fillOpacity="0.55" fontSize="9" textAnchor="middle" fontFamily={MONO}>{value}</text>;
  });
  const [ax, ay] = point(start, r);
  const [bx, by] = point(end, r);
  // Waypoint sulla percentuale completata; se due etichette sono troppo vicine, la seconda scende
  // su un livello più interno dell'arco invece di sovrapporsi.
  const levels = [];
  const waypoints = epics
    .filter((e) => pct(e.progress) !== null)
    .sort((a, b) => pct(a.progress) - pct(b.progress))
    .map((epic) => {
      const deg = start + (end - start) * pct(epic.progress);
      let level = 0;
      while (levels[level] !== undefined && deg - levels[level] < LABEL_GAP_DEG) level += 1;
      levels[level] = deg;
      const [x, y] = point(deg, r - 30 - level * 19);
      const top = cy - r - 20;
      const color = epic.key === focusKey ? C.magenta : epic.items.some(isWaiting) ? C.amber : C.cyan;
      // Il waypoint si illumina quando il fascio del radar ci passa sopra.
      const hit = `${(((deg - start) / (end - start)) * SWEEP_SECONDS).toFixed(2)}s`;
      const ping = (name) => (animate ? { animation: `${name} ${SWEEP_SECONDS}s linear ${hit} infinite` } : {});
      return {
        label: <text key={epic.key} x={x + 7} y={y + 3.5} fill={color} fontSize="9.5" fontFamily={MONO}>{epic.key}</text>,
        // Anello come il cerchio SVG di prima: raggio 4, tratto 1.6 centrato sul raggio.
        marker: (
          <div key={epic.key} title={`${epic.key} · ${Math.round(pct(epic.progress) * 100)}% completata`}
            style={{ position: "absolute", left: x - 4.8, top: y - top - 4.8, width: 9.6, height: 9.6, boxSizing: "border-box",
              border: `1.6px solid ${color}`, borderRadius: "50%", ...ping("cc-ping") }}>
            <div style={{ position: "absolute", inset: -0.8, borderRadius: "50%", background: color, opacity: 0, ...ping("cc-ping-fill") }} />
          </div>
        ),
      };
    });
  const [fx, fy] = point(0, r);
  // Fascio del radar: una scia di spicchi sempre più tenui dietro una linea brillante, che ruota
  // attorno al centro dell'arco da sinistra a destra, ritagliata sul settore dell'arco.
  const slice = TRAIL_DEG / TRAIL_SLICES;
  const wedge = (from, to) => {
    const [x1, y1] = point(from, r);
    const [x2, y2] = point(to, r);
    return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2} Z`;
  };
  const trail = [];
  for (let i = 0; i < TRAIL_SLICES; i += 1) {
    trail.push(<path key={i} d={wedge(-TRAIL_DEG + i * slice, -TRAIL_DEG + (i + 1) * slice)} fill={C.green} fillOpacity={0.012 + (i / TRAIL_SLICES) * 0.2} />);
  }
  const [lx, ly] = point(0, r);
  const viewBox = `0 ${cy - r - 20} ${width} ${ARC_HEIGHT}`;
  const layer = { position: "absolute", left: 0, top: 0, width, height: ARC_HEIGHT };
  // Il settore dell'arco ritaglia il fascio come maschera del livello che lo contiene.
  const sector = `url("data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${ARC_HEIGHT}" viewBox="${viewBox}"><path d="${wedge(start, end)}"/></svg>`,
  )}")`;
  return (
    <div ref={alignToPageStart} style={{ position: "relative", width, height: ARC_HEIGHT, margin: "2px auto 0" }}>
      <style>{RADAR_KEYFRAMES}</style>
      <svg width={width} height={ARC_HEIGHT} viewBox={viewBox} style={layer}>
        <path d={`M ${ax} ${ay} A ${r} ${r} 0 0 1 ${bx} ${by}`} fill="none" stroke={C.white} strokeOpacity="0.55" strokeWidth="1" />
      </svg>
      {animate && (
        <div style={{ ...layer, WebkitMaskImage: sector }}>
          <div style={{ ...layer, transformOrigin: `${cx}px ${r + 20}px`, willChange: "transform", animation: `cc-sweep ${SWEEP_SECONDS}s linear infinite` }}>
            <svg width={width} height={ARC_HEIGHT} viewBox={viewBox} style={{ display: "block" }}>
              {trail}
              <line x1={cx} y1={cy} x2={lx} y2={ly} stroke={C.green} strokeOpacity="0.85" strokeWidth="1.4" />
            </svg>
          </div>
        </div>
      )}
      <svg width={width} height={ARC_HEIGHT} viewBox={viewBox} style={layer}>
        {ticks}
        {labels}
        <line x1={fx} y1={fy - 2} x2={fx} y2={fy + ARC_HEIGHT} stroke={C.magenta} strokeOpacity="0.55" strokeWidth="1" strokeDasharray="3 3" />
        {waypoints.map((w) => w.label)}
      </svg>
      {waypoints.map((w) => w.marker)}
    </div>
  );
};

// Nastro con le attività in corso che scorre lento e continuo; le attività che aspettano te in ambra.
const TICKER_SECONDS_PER_CHAR = 0.22;

const tickerStyle = css`
  position: relative;
  overflow: hidden;
  white-space: nowrap;
  border-top: 1px solid rgba(73, 240, 124, 0.18);
  border-bottom: 1px solid rgba(73, 240, 124, 0.18);
  padding: 3px 0;
  margin: 2px 0 4px;
  font-size: 10.5px;
  letter-spacing: 0.8px;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent);
`;
// Il nastro resta fermo e scorrono le singole voci, tutte con la stessa animazione: un livello unico
// largo migliaia di pixel costringe WebKit a ridisegnarlo a ogni fotogramma.
const tickerTrack = css`
  display: inline-block;
  & > span { display: inline-block; will-change: transform; }
`;
// Animazione globale: un nome fisso, non generato da emotion, e ferma con «Riduci movimento».
const TICKER_KEYFRAMES = `
  @keyframes cc-ticker { from { transform: translateX(0); } to { transform: translateX(calc(-1 * var(--cc-ticker-shift))); } }
  @media (prefers-reduced-motion: reduce) { .cc-ticker-track > span { animation: none !important; } }
`;
// Spostamento di un giro: la larghezza di una delle due copie, misurata dopo il layout.
const setTickerShift = (track) => {
  if (track) track.style.setProperty("--cc-ticker-shift", `${track.getBoundingClientRect().width / 2}px`);
};

const Ticker = ({ items }) => {
  if (!items.length) return null;
  const text = items.map((i) => `${i.key} ${i.summary}`).join(" ◆ ");
  const seconds = Math.max(30, Math.round(text.length * TICKER_SECONDS_PER_CHAR));
  const entries = (copy) => items.map((item) => (
    <span key={`${copy}-${item.key}`} style={{ color: isWaiting(item) ? C.amber : C.green, marginRight: 22, animation: `cc-ticker ${seconds}s linear infinite` }}>
      <span style={{ color: C.dim }}>{item.key}</span> {stripEmoji(item.summary).toUpperCase()}
      <span style={{ color: C.faint, marginLeft: 22 }}>◆</span>
    </span>
  ));
  return (
    <div className={tickerStyle}>
      <style>{TICKER_KEYFRAMES}</style>
      {/* Due copie identiche: a metà percorso la seconda prende il posto della prima senza salti. */}
      <div ref={setTickerShift} className={`${tickerTrack} cc-ticker-track`}>
        {entries("a")}{entries("b")}
      </div>
    </div>
  );
};

const Annunciators = ({ summary, proposals }) => {
  const cells = [
    ["IN CORSO", summary.inProgress || 0, C.green, false],
    ["IN ATTESA", summary.waitingSessions || 0, C.amber, summary.waitingSessions > 0],
    ["FERME", summary.staleSessions || 0, C.amber, false],
    ["DA TRACC.", proposals, C.cyan, false],
  ];
  return (
    <div className={annunciators}>
      {cells.map(([name, value, color, alert]) => (
        <div key={name} className={annunciator}
          style={alert ? { background: "rgba(255,184,74,0.14)", boxShadow: `inset 0 0 0 1px ${C.amber}` } : {}}>
          <span style={{ color: value ? color : C.faint }}>{name}</span>
          <span className={annunciatorValue} style={value ? glow(color) : { color: C.faint }}>{value}</span>
        </div>
      ))}
    </div>
  );
};

const itemColor = (item) => (isWaiting(item) || isStale(item) ? C.amber : item.statusCategory === "indeterminate" ? C.green : C.dim);

const Item = ({ item, base, dispatch }) => (
  <div className={itemRow} title={`${item.key} · ${item.status}\n${item.summary}`}>
    <span style={{ color: itemColor(item), flexShrink: 0 }}>{isWaiting(item) ? "◆" : "▸"}</span>
    <div className={itemText}>
      <div className={oneLine} style={{ color: item.statusCategory === "indeterminate" ? C.white : C.dim }}>{item.summary}</div>
      {isWaiting(item) && <div style={{ color: C.amber, fontSize: 10.5 }}>SESSIONE IN ATTESA DI RISPOSTA</div>}
      {isStale(item) && <div style={{ color: C.amber, fontSize: 10.5 }}>SESSIONE FERMA DA {item.session.staleDays} G</div>}
      {item.nextStep && <div className={oneLine} style={{ color: C.cyan, fontSize: 10.5 }}>NEXT ▸ {item.nextStep}</div>}
    </div>
    <div className={`${softkeys} keys`}>
      <span className={softkey} style={{ color: C.green }} onClick={() => resume(dispatch, item.key)}>▶ VAI</span>
      <span className={softkey} style={{ color: C.cyan }} onClick={() => openUrl(issueUrl(base, item.key))}>JIRA</span>
    </div>
  </div>
);

const visibleItems = (items, showAll) => {
  if (showAll) return items;
  const active = items.filter((i) => i.statusCategory === "indeterminate" || isWaiting(i));
  return active.length ? active : items.slice(0, 3);
};

const age = (days) => (days === null || days === undefined ? "" : days === 0 ? "OGGI" : `${days}G`);

const Epic = ({ epic, base, isOpen, showAll, focus, dispatch }) => {
  const isGroup = epic.key === NO_EPIC;
  const active = epic.items.filter((i) => i.statusCategory === "indeterminate").length;
  const waiting = epic.items.some(isWaiting);
  const color = focus ? C.magenta : waiting ? C.amber : active ? C.green : C.dim;
  const done = pct(epic.progress);
  const hidden = epic.items.length - visibleItems(epic.items, false).length;
  return (
    <div>
      <div className={epicRow} onClick={() => dispatch({ type: "TOGGLE", key: epic.key })}>
        <span style={{ color, flexShrink: 0, width: 12 }}>{isOpen ? "▾" : "◇"}</span>
        <span className={tag} style={{ color: C.dim, width: 58 }}>{isGroup ? "----" : epic.key}</span>
        <span className={label} style={glow(color)} title={epic.summary}>{stripEmoji(epic.summary)}</span>
        {waiting && <span className={tag} style={{ color: C.amber }}>ATT</span>}
        <span className={tag} style={{ color: active ? C.green : C.faint, width: 22, textAlign: "right" }}>{active}▸</span>
        <span className={tag} style={{ color: C.white, width: 36, textAlign: "right" }}>{done === null ? `${epic.items.length}` : `${Math.round(done * 100)}%`}</span>
      </div>
      {isOpen && (
        <div className={detail}>
          {visibleItems(epic.items, showAll).map((item) => <Item key={item.key} item={item} base={base} dispatch={dispatch} />)}
          {hidden > 0 && (
            <span className={link} onClick={() => dispatch({ type: "SHOW_ALL", key: epic.key })}>
              {showAll ? "◂ SOLO IN CORSO" : `+${hidden} DA FARE ▸`}
            </span>
          )}
          {!isGroup && (epic.repos || []).map((repo) => (
            <div key={repo.path} className={itemRow} style={{ cursor: "pointer" }} title={`${repo.path}\nClic: apri nel terminale`}
              onClick={() => openFolder(dispatch, repo.path)}>
              <span style={{ color: C.cyan, flexShrink: 0 }}>⌂</span>
              <span className={oneLine} style={{ flex: 1, color: C.dim }}>
                <span style={{ color: C.white }}>{repo.name}</span>{repo.branch ? `  ${repo.branch}` : ""}
              </span>
              {repo.dirty > 0 && <span style={{ color: C.amber, fontSize: 10.5 }}>±{repo.dirty}</span>}
              {repo.ahead > 0 && <span style={{ color: C.cyan, fontSize: 10.5 }}>↑{repo.ahead}</span>}
              <span style={{ color: C.faint, fontSize: 10.5 }}>{age(repo.lastCommitDays)}</span>
            </div>
          ))}
          {!isGroup && <span className={link} onClick={() => openUrl(issueUrl(base, epic.key))}>EPICA IN JIRA ↗</span>}
        </div>
      )}
    </div>
  );
};

const since = (hours) =>
  hours === null || hours === undefined ? "" : hours < 24 ? `${Math.max(1, Math.round(hours))}H` : `${Math.floor(hours / 24)}G`;

const Advisory = ({ proposal, epics, menuOpen, dispatch }) => {
  const ids = proposal.sessionIds || [proposal.sessionId];
  return (
    <div>
      <div className={itemRow} title={proposal.why || ""}>
        <span style={{ color: C.cyan, flexShrink: 0 }}>＋</span>
        <div className={itemText}>
          <div style={{ color: C.white }}>{proposal.title}</div>
          <div className={oneLine} style={{ color: C.dim, fontSize: 10.5 }}>
            {proposal.epicKey ? `▸ ${proposal.epicKey} ${stripEmoji(proposal.epicSummary)}` : "▸ NUOVA EPICA"}
            {ids.length > 1 ? ` · ${ids.length} SESS` : ""} · {since(proposal.hoursAgo)}
          </div>
        </div>
        <div className={`${softkeys} keys`}>
          <span className={softkey} style={{ color: C.green }} onClick={() => track(dispatch, ids, proposal.epicKey || null, proposal.title)}>
            {proposal.epicKey ? "CREA TASK" : "CREA EPICA"}
          </span>
          <span className={softkey} style={{ color: C.cyan }} onClick={() => dispatch({ type: "MENU", sessionId: proposal.sessionId })}>ALTRA</span>
          <span className={softkey} style={{ color: C.dim }} onClick={() => ignore(dispatch, ids)}>SCARTA</span>
        </div>
      </div>
      {menuOpen && (
        <div className={menu}>
          {epics.map((epic) => (
            <div key={epic.key} className={menuItem} onClick={() => track(dispatch, ids, epic.key, proposal.title, proposal.sessionId)}>
              {epic.key} {stripEmoji(epic.summary)}
            </div>
          ))}
          <div className={menuItem} style={{ color: C.green }} onClick={() => track(dispatch, ids, null, proposal.title, proposal.sessionId)}>
            + NUOVA EPICA
          </div>
        </div>
      )}
    </div>
  );
};

export const render = ({ data, open, showAll, menuFor, loading, toast: message }, dispatch) => {
  followScreen(dispatch);
  const base = (data && data.baseUrl) || "";
  const epics = data ? [...(data.epics || [])] : [];
  if (data && data.noEpic && data.noEpic.length) epics.push({ key: NO_EPIC, summary: "Senza epica", items: data.noEpic });
  const summary = (data && data.summary) || {};
  const proposals = (data && data.proposals) || [];
  const focusKey = data && data.epics && data.epics[0] ? data.epics[0].key : null;
  const updated = data && data.updatedAt
    ? new Date(data.updatedAt * 1000).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
    : "--:--";
  const myIssuesUrl = `${base}/issues/?jql=${encodeURIComponent((data && data.myOpenJql) || "assignee = currentUser() AND statusCategory != Done")}`;

  return (
    <div className={bezel} style={placement()}>
      <div className={bezelRow}>
        <span className={screw} />
        <span style={{ flex: 1 }}>Project Display · MFD 1</span>
        <span style={{ color: loading ? C.amber : C.green }}>● {loading ? "SYNC" : "LINK"}</span>
        <span className={screw} />
      </div>
      <div className={screen}>
        {!data && <div style={{ color: C.green, fontSize: 12 }}>ALLINEAMENTO IN CORSO…</div>}
        {data && (
          <div>
            <Annunciators summary={summary} proposals={proposals.length} />
            <Ticker items={epics.flatMap((e) => e.items).filter((i) => i.statusCategory === "indeterminate" || isWaiting(i))} />
            {data.error && (
              <div style={{ color: C.amber, fontSize: 10.5, margin: "4px 0" }} title={data.error}>
                {data.stale ? `JIRA NON RAGGIUNGIBILE · DATI DELLE ${updated}` : `ERRORE: ${data.error}`}
              </div>
            )}
            <NavArc epics={data.epics || []} focusKey={focusKey} />
            <div className={sectionLabel}>EPICHE · % COMPLETATA</div>
            {epics.map((epic) => (
              <Epic key={epic.key} epic={epic} base={base} isOpen={!!open[epic.key]} showAll={!!showAll[epic.key]}
                focus={epic.key === focusKey} dispatch={dispatch} />
            ))}
            {proposals.length > 0 && (
              <div>
                <div className={sectionLabel} style={{ cursor: "pointer", color: C.cyan }} onClick={() => dispatch({ type: "TOGGLE", key: ADVISORY })}>
                  {open[ADVISORY] ? "▾" : "◇"} DA TRACCIARE · {proposals.length}
                </div>
                {open[ADVISORY] && proposals.map((proposal) => (
                  <Advisory key={proposal.sessionId} proposal={proposal} epics={data.epics || []}
                    menuOpen={menuFor === proposal.sessionId} dispatch={dispatch} />
                ))}
              </div>
            )}
            {message && (
              <div className={toastLine} style={{ color: message.kind === "error" ? C.red : message.kind === "ok" ? C.green : C.cyan }}>
                {message.text}
              </div>
            )}
          </div>
        )}
      </div>
      <div className={hardkeys}>
        <span className={hardkey} onClick={() => refresh(dispatch)}>⟳ AGGIORNA</span>
        <span className={hardkey} onClick={() => openUrl(myIssuesUrl)}>JIRA ↗</span>
        <span className={hardkey} onClick={() => dispatch({ type: "TOGGLE", key: ADVISORY })}>DA TRACCIARE</span>
        <span className={clock}>{updated}</span>
      </div>
    </div>
  );
};
