import { css } from "uebersicht";

// Capitan Harlock al timone dell'Arcadia, in pixel art, con la cornice degli altri pannelli.
// Nessun comando shell e nessun timer: tutto il movimento è fatto da animazioni CSS a scatti
// (steps), che aggiornano lo schermo circa una volta al secondo.

export const refreshFrequency = false;

const S = 3; // un pixel dello sprite = 3px sullo schermo
const W = 360;
const H = 272;
const SCREEN = { x: 12, y: 32, w: 336, h: 228 }; // 112 x 76 pixel di scena
const PORT = { cx: 56, cy: 30, r: 26 }; // oblò, in pixel di scena

const C = {
  bezel: "#151a24",
  bezelEdge: "#262d3b",
  white: "#e9eef5",
  green: "#49f07c",
  cyan: "#56e3ff",
  amber: "#ffb84a",
  red: "#ff6b5e",
  atmosphere: "rgba(84, 120, 255, 0.35)",
};
const MONO = `"SF Mono", "JetBrains Mono", Menlo, monospace`;

// ------------------------------------------------------------------ posizione (come gli altri pannelli)

// Il pannello è disegnato per lo schermo del portatile (1470×918 punti sotto la barra dei menu): su
// un altro schermo si scala sul lato che limita (l'altezza, sull'ultrawide) e occupa la stessa
// porzione di schermo. Margine dall'angolo e dimensioni sono in punti del portatile e si
// scalano con il pannello.
const REF_SCREEN = { w: 1470, h: 918 };
// Griglia comune ai quattro pannelli, in punti del portatile: colonne larghe 470 ai lati, 34 dai
// bordi e 16 tra le righe. Riga alta 479 (cc-panel, news-panel), riga bassa 355 (Harlock a 470 di
// larghezza, focus-panel). Posizione fissa: i pannelli non si trascinano.
const MARGIN = { x: 34, y: -34 }; // dall'angolo di className; negativo verso sinistra o verso l'alto
const ZOOM = 470 / W; // Harlock largo quanto gli altri pannelli
const screenScale = () => Math.min(window.innerWidth / REF_SCREEN.w, window.innerHeight / REF_SCREEN.h);

const placement = () => {
  const s = screenScale();
  return {
    transform: `translate(${MARGIN.x * s}px, ${MARGIN.y * s}px) scale(${s * ZOOM})`,
    transformOrigin: "bottom left",
  };
};

// Ricalcola la scala quando cambia lo schermo (monitor collegato o scollegato). Il gestore sta su
// window perché i widget condividono la pagina e un ricaricamento rivaluta il modulo.
const followScreen = (dispatch) => {
  window.removeEventListener("resize", window.harlockPanelResize);
  window.harlockPanelResize = () => dispatch({ type: "RESIZE" });
  window.addEventListener("resize", window.harlockPanelResize);
};

export const initialState = {};

export const updateState = (event, prev) => {
  return event.type === "RESIZE" ? { ...prev } : prev;
};

// ------------------------------------------------------------------ sprite

const PALETTE = {
  K: "#07080d", // nero
  k: "#121729", // mantello
  B: "#26345e", // pieghe del mantello
  R: "#a8222c", // fodera rossa
  r: "#5e1016", // fodera in ombra
  Y: "#e9b830", // bordi gialli
  H: "#a85a1c", // capelli
  h: "#6b3410", // capelli in ombra
  L: "#d88238", // capelli in luce
  S: "#e2a77e", // pelle
  s: "#a8704e", // pelle in ombra
  G: "#4a3020", // guanti
};

// Harlock di spalle, testa girata a destra verso l'oblò: si vede il profilo con la benda.
const HEAD = [
  "...........h...hhhh..h",
  "..........hHhhhHHHHhhHh",
  ".........hHHHHHHLLLHHHHh",
  "......hhhHHHHLLHHHHHHHHHh",
  ".......hHHHLLHHHHHHHHHHHh",
  ".......hHHLHHHHHHHHHHHHHHh",
  ".....hhHHHHHHHHHHHHHHHHHHh",
  "......hHHHHHHHHHHHHHHHHhHHHs",
  "....hhHHHHHHHHHHHHHHHHhKKKSSs",
  ".....hHHHHHHHHHHHHHHHHhKKKKSSs",
  ".....hHHHHHHHHHHHHHHHHHhKKsSSSS",
  ".....hHHhHHHHHHHHHHHHHHhSSSSSs",
  "....hHHhhHHHHhHHHHHHHHHhsSSSKs",
  "....hHh.hHHHhhHHHHHhHHHHhsSSs",
  "....hh..hHHh.hHHHHhhHHHh.ssSs",
  "...hh...hHh..hHHHh.hHHh...ss",
];

// Ciocche sotto la nuca: oscillano piano, sfasate rispetto alla testa.
const LOCKS = [
  "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
  "...h....hHh..hHHh..hHh",
  ".........h...hHh....h",
  "..............h",
];

const BODY = [
  "", "", "", "", "",
  "..Y................................Y",
  "..YY..............................YY",
  "..YkY............................YRY",
  "..YkkY..........................YRRY",
  "..YkkkY........................YRRRY",
  "..YkkkkY......................YRRRRY",
  "..YkkkkkY....................YRRRRRY",
  "...YkkkkkY..................YRRRRRY",
  "...YkkkkkkYY..............YYRRRRRY",
  "....YkkkkkkkYYYY......YYYYRRRRRRY",
  "....YkkkkkkkkkkkYYYYYYRRRRRRRRRY",
  "...kkYkkkkkkkkkkkkkkkkkkkkkRRRYkkk",
  "..kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk",
  ".YkkkkkkkkBkkkkkkkkkkkkkkkkkkBkkkkkkkkY",
  ".YkkkkkkkkBkkkkkkkkkkkkkkkkkkBkkkkkkkkY",
  ".YkkkkkkkBkkkkkkkkkkkkkkkkkkkkBkkkkkkkY",
  "..YkkkkkkBkkkkkkkkkkkkkkkkkkkkBkkkkkkY",
  "..YYkkkkBkkkkkkkkkkkkkkkkkkkkkkBkkkkYY",
  "...YYYkkkkkkkkkkkkkkkkkkkkkkkkkkkYYYY",
  "...kRYYYYkkkkkkkkkkkkkkkkkkkkYYYYYRk",
  "...kRkkkkYYYYYYYYYYYYYYYYYYYYkkkkRRk",
  "...kRkkkkkkkkkBkkkkkkkkkBkkkkkkkkRRk",
  "...kRkkkkkkkkkBkkkkkkkkkBkkkkkkkkRRk",
  "..kRRkkkkkkkkBkkkkkkkkkkkBkkkkkkkRRk",
  "..kRrkkkkkkkkBkkkkkkkkkkkBkkkkkkkrRk",
  "..kRrkkkkkkkBkkkkkkkkkkkkkBkkkkkkrRRk",
  "..kRrkkkkkkkBkkkkkkkkkkkkkBkkkkkkrRRk",
  ".kRRrkkkkkkBkkkkkkkkkkkkkkkBkkkkkrRRk",
  ".kRrkkkkkkkBkkkkkkkkkkkkkkkBkkkkkkrRk",
  ".kRrkkkkkkBkkkkkkkkkkkkkkkkkBkkkkkrRRk",
  ".kRrkkkkkkBkkkkkkkkkkkkkkkkkBkkkkkrRRk",
  "kRRrkkkkkBkkkkkkkkkkkkkkkkkkkBkkkkrRRk",
  "kRrkkkkkkBkkkkkkkkkkkkkkkkkkkBkkkkkrRk",
  "kRrkkkkkBkkkkkkkkkkkkkkkkkkkkkBkkkkrRRk",
  "kRrkkkkkBkkkkkkkkkkkkkkkkkkkkkBkkkkrRRk",
  "kRrkkkkBkkkkkkkkkkkkkkkkkkkkkkkBkkkrRRk",
  "kRrkkkkBkkkkkkkkkkkkkkkkkkkkkkkBkkkkrRk",
  "kRrkkkBkkkkkkkkkkkkkkkkkkkkkkkkkBkkkrRk",
  "kRrkkkBkkkkkkkkkkkkkkkkkkkkkkkkkBkkkrRk",
  "kRrkkBkkkkkkkkkkkkkkkkkkkkkkkkkkkBkkrRk",
  "kRrkkBkkkkkkkkkkkkkkkkkkkkkkkkkkkBkkrRk",
  "kRrkBkkkkkkkkkkkkkkkkkkkkkkkkkkkkkBkrRk",
  "kRrkBkkkkkkkkkkkkkkkkkkkkkkkkkkkkkBkrRk",
];

// Un rettangolo per ogni tratto orizzontale dello stesso colore: poche centinaia di nodi in tutto.
const runs = (rows) => {
  const rects = [];
  rows.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const ch = row[x];
      let end = x;
      while (row[end + 1] === ch) end++;
      if (PALETTE[ch]) {
        rects.push(<rect key={`${x}.${y}`} x={x} y={y} width={end - x + 1} height={1} fill={PALETTE[ch]} />);
      }
      x = end + 1;
    }
  });
  return rects;
};

const SPRITE_W = 40;
const SPRITE_H = 48;
const SPRITE_AT = { x: 36, y: 28 }; // in pixel di scena

const Sprite = ({ rows, className }) => (
  <svg className={className} width={SPRITE_W * S} height={SPRITE_H * S} viewBox={`0 0 ${SPRITE_W} ${SPRITE_H}`}
    shapeRendering="crispEdges" style={{ position: "absolute", left: SPRITE_AT.x * S, top: SPRITE_AT.y * S }}>
    {runs(rows)}
  </svg>
);

// Timone: 60 x 60 pixel di scena, centro in (56, 58); ruota di qualche grado avanti e indietro.
const WHEEL_AT = { x: 26, y: 28 };
const SPOKES = [0, 45, 90, 135, 180, 225, 270, 315].map((a) => (a * Math.PI) / 180);

const Wheel = () => (
  <svg className="harlock-anim harlock-wheel" width={60 * S} height={60 * S} viewBox="0 0 60 60" shapeRendering="crispEdges"
    style={{ position: "absolute", left: WHEEL_AT.x * S, top: WHEEL_AT.y * S }}>
    {SPOKES.map((a, i) => (
      <g key={i}>
        <line x1={30} y1={30} x2={30 + 28 * Math.cos(a)} y2={30 + 28 * Math.sin(a)} stroke="#2a1a0e" strokeWidth={3.4} />
        <line x1={30} y1={30} x2={30 + 27.5 * Math.cos(a)} y2={30 + 27.5 * Math.sin(a)} stroke="#8a5a32" strokeWidth={2} />
      </g>
    ))}
    <circle cx={30} cy={30} r={21} fill="none" stroke="#2a1a0e" strokeWidth={4.4} />
    <circle cx={30} cy={30} r={21} fill="none" stroke="#9a6a3a" strokeWidth={2.6} />
    <circle cx={30} cy={30} r={5} fill="#2a3140" stroke="#07080d" />
  </svg>
);

// Mani guantate sulle impugnature a ore 9 e 3, con le maniche che escono dal mantello.
const HANDS = [
  "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
  ".......GGG.kkkkk.........................kkkkk.GGG",
  "......GGGGGkkkkkk.......................kkkkkkGGGGG",
  "......GGGGGkkkkkk.......................kkkkkkGGGGG",
  ".......GGG.......................................GGG",
];

const Hands = () => (
  <svg className="harlock-anim harlock-wheel" width={60 * S} height={60 * S} viewBox="0 0 60 60" shapeRendering="crispEdges"
    style={{ position: "absolute", left: WHEEL_AT.x * S, top: WHEEL_AT.y * S }}>
    {runs(HANDS)}
  </svg>
);

// ------------------------------------------------------------------ plancia (statica)

const rounded = (x, y, w, h, r) =>
  `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}A${r} ${r} 0 0 1 ${x + w - r} ${y + h}` +
  `H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`;
const circle = (cx, cy, r) => `M${cx - r} ${cy}A${r} ${r} 0 1 0 ${cx + r} ${cy}A${r} ${r} 0 1 0 ${cx - r} ${cy}Z`;

const HOLE = circle(SCREEN.x + PORT.cx * S, SCREEN.y + PORT.cy * S, PORT.r * S);
const RIVETS = Array.from({ length: 12 }, (_, i) => (i * Math.PI) / 6);

const Monitor = ({ x }) => (
  <g>
    <rect x={x} y={8} width={20} height={26} fill="#0b2350" stroke="#2e5fae" strokeWidth={1} />
    {[4, 8, 12, 16].map((d) => <rect key={`v${d}`} x={x + d} y={9} width={0.4} height={24} fill="rgba(86,227,255,0.3)" />)}
    {[5, 10, 15, 20].map((d) => <rect key={`h${d}`} x={x + 1} y={8 + d} width={18} height={0.4} fill="rgba(86,227,255,0.3)" />)}
    <rect x={x - 2} y={40} width={24} height={36} fill="#10151f" stroke="#1d2433" />
    {[0, 1, 2, 3].map((i) => <rect key={`l${i}`} x={x + 1 + i * 5} y={43} width={3} height={1} fill={i % 2 ? "#3b6bd6" : "#56e3ff"} />)}
    <circle cx={x + 5} cy={52} r={3} fill="#0f2a16" stroke="#49f07c" strokeWidth={0.5} />
    <circle cx={x + 15} cy={52} r={3} fill="#0f2a16" stroke="#49f07c" strokeWidth={0.5} />
    {[0, 1, 2].map((i) => <rect key={`b${i}`} x={x + 6 + i * 3} y={59 + i * 2} width={8} height={1} fill="#a8222c" />)}
  </g>
);

const Backdrop = () => (
  <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ position: "absolute", left: 0, top: 0 }}>
    <defs>
      <linearGradient id="harlock-bezel" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#1b2130" />
        <stop offset="1" stopColor={C.bezel} />
      </linearGradient>
    </defs>
    <path d={rounded(0.5, 0.5, W - 1, H - 1, 18) + HOLE} fillRule="evenodd" fill="url(#harlock-bezel)" stroke={C.bezelEdge} />
    <g transform={`translate(${SCREEN.x} ${SCREEN.y}) scale(${S})`} shapeRendering="crispEdges">
      <path d={`M0 0H112V76H0Z${circle(PORT.cx, PORT.cy, PORT.r)}`} fillRule="evenodd" fill="rgba(5, 8, 14, 0.94)" />
      <Monitor x={4} />
      <Monitor x={88} />
      <circle cx={PORT.cx} cy={PORT.cy} r={PORT.r + 1.6} fill="none" stroke="#2a3242" strokeWidth={3.2} />
      <circle cx={PORT.cx} cy={PORT.cy} r={PORT.r + 0.2} fill="none" stroke="rgba(86,227,255,0.35)" strokeWidth={0.5} />
      {RIVETS.map((a, i) => (
        <rect key={i} x={PORT.cx + (PORT.r + 1.6) * Math.cos(a) - 0.5} y={PORT.cy + (PORT.r + 1.6) * Math.sin(a) - 0.5}
          width={1} height={1} fill="#5a6273" />
      ))}
    </g>
    <rect x={SCREEN.x + 0.5} y={SCREEN.y + 0.5} width={SCREEN.w - 1} height={SCREEN.h - 1} rx={8} fill="none" stroke="#000" />
  </svg>
);

// Spie che lampeggiano lente sulle due console.
const Lights = () => (
  <svg width={SCREEN.w} height={SCREEN.h} viewBox="0 0 112 76" shapeRendering="crispEdges" style={{ position: "absolute", left: 0, top: 0 }}>
    <rect className="harlock-anim harlock-blink" x={7} y={66} width={2} height={2} fill={C.amber} />
    <rect className="harlock-anim harlock-blink-late" x={101} y={66} width={2} height={2} fill={C.green} />
    <rect className="harlock-anim harlock-blink-late" x={13} y={37} width={2} height={1} fill={C.red} />
    <rect className="harlock-anim harlock-blink" x={95} y={37} width={2} height={1} fill={C.cyan} />
  </svg>
);

// ------------------------------------------------------------------ stile

export const className = `
  bottom: 0;
  left: 0;
  font-family: ${MONO};
  color: ${C.white};
  -webkit-font-smoothing: antialiased;
`;

const frame = css`
  position: relative;
  width: ${W}px;
  height: ${H}px;
  border-radius: 18px;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.6), 0 0 28px ${C.atmosphere}, 0 24px 60px rgba(0, 0, 0, 0.55);
`;
const bezelRow = css`
  position: absolute;
  left: 16px;
  right: 16px;
  top: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
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
  position: absolute;
  left: ${SCREEN.x}px;
  top: ${SCREEN.y}px;
  width: ${SCREEN.w}px;
  height: ${SCREEN.h}px;
  border-radius: 8px;
  overflow: hidden;
`;
// Vetro dell'oblò: quasi trasparente, lascia vedere il desktop dietro le stelle.
const porthole = css`
  position: absolute;
  left: ${(PORT.cx - PORT.r) * S}px;
  top: ${(PORT.cy - PORT.r) * S}px;
  width: ${PORT.r * 2 * S}px;
  height: ${PORT.r * 2 * S}px;
  border-radius: 50%;
  overflow: hidden;
  background: radial-gradient(circle at 50% 60%, rgba(40, 70, 150, 0.16), rgba(10, 20, 50, 0.32));
`;
const dot = (x, y, size, alpha) =>
  `radial-gradient(circle at ${x}px ${y}px, rgba(233, 238, 245, ${alpha}) ${size}px, transparent ${size + 0.4}px)`;
// Le dimensioni delle tessere dividono 156px: lo scorrimento di 156px torna al punto di partenza.
const stars = css`
  position: absolute;
  top: 0;
  left: 0;
  width: ${PORT.r * 4 * S}px;
  height: 100%;
  will-change: transform;
`;
const farStars = css`
  background: ${dot(9, 14, 1, 0.5)} 0 0 / 52px 52px, ${dot(31, 40, 1, 0.35)} 0 0 / 52px 52px,
    ${dot(20, 6, 1, 0.45)} 0 0 / 39px 39px, ${dot(60, 27, 1, 0.3)} 0 0 / 78px 78px;
`;
const nearStars = css`
  background: ${dot(12, 50, 1.5, 0.9)} 0 0 / 78px 78px, ${dot(110, 120, 1.5, 0.8)} 0 0 / 156px 156px,
    ${dot(40, 20, 1.2, 0.7)} 0 0 / 156px 156px;
`;
const glare = css`
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: radial-gradient(ellipse at 30% 22%, rgba(255, 255, 255, 0.12), transparent 40%);
  box-shadow: inset 0 0 18px rgba(86, 227, 255, 0.18);
`;
const scanlines = css`
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: repeating-linear-gradient(0deg, rgba(0, 0, 0, 0.16) 0 1px, transparent 1px 3px);
`;

// Movimenti a scatti, fatti da un timer invece che da animazioni CSS: WebKit non passa alla GPU le
// animazioni steps()/step-end e le ricalcola a ogni fotogramma, rallentando anche gli altri widget
// (~11% di CPU con tutti i pannelli accesi). Il timer cambia lo stile solo quando cambia il passo.
// Per ogni movimento: classe degli elementi, durata del ciclo in secondi, proprietà e valore in
// funzione della fase del ciclo (da 0 a 1). Sono gli stessi passi delle animazioni CSS di prima.
const MOTION = [
  ["harlock-far", 104, "transform", (p) => `translateX(${-3 * Math.floor(p * 52)}px)`],
  ["harlock-near", 52, "transform", (p) => `translateX(${-3 * Math.floor(p * 52)}px)`],
  ["harlock-wheel", 16, "transform", (p) => {
    const deg = -6 + 1.5 * (Math.floor(p * 16) % 8);
    return `rotate(${p < 0.5 ? deg : -deg}deg)`;
  }],
  ["harlock-head", 9, "transform", (p) => (p < 0.3 ? "none" : p < 0.6 ? "translate(3px, 0)" : "translate(3px, 3px)")],
  ["harlock-locks", 5, "transform", (p) => (p < 0.5 ? "none" : "translate(3px, 0)")],
  ["harlock-blink", 2.4, "opacity", (p) => (p < 0.5 ? "1" : "0.15")],
  ["harlock-blink-late", 3.7, "opacity", (p) => (p < 0.5 ? "1" : "0.15")],
];
const MOTION_TICK_MS = 100;
const MOTION_CSS = `
  .harlock-far, .harlock-near, .harlock-head, .harlock-locks { will-change: transform; }
  .harlock-wheel { transform-origin: 50% 50%; will-change: transform; }
`;

// Con «Riduci movimento» attivo in macOS la scena resta ferma.
const reducedMotion = () => {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (e) {
    return false;
  }
};

// Ref del pannello: avvia il timer al montaggio e lo ferma allo smontaggio. Il timer sta su window
// perché un ricaricamento del widget rivaluta il modulo e perderebbe il riferimento.
const runMotion = (root) => {
  clearInterval(window.harlockMotionTimer);
  if (!root || reducedMotion()) return;
  const tracks = MOTION.map(([cls, seconds, prop, value]) => ({ els: [...root.getElementsByClassName(cls)], seconds, prop, value, last: null }));
  const tick = () => {
    const t = performance.now() / 1000;
    tracks.forEach((track) => {
      const v = track.value((t % track.seconds) / track.seconds);
      if (v === track.last) return;
      track.last = v;
      track.els.forEach((el) => { el.style[track.prop] = v; });
    });
  };
  tick();
  window.harlockMotionTimer = setInterval(tick, MOTION_TICK_MS);
};

// ------------------------------------------------------------------ render

export const render = (_, dispatch) => {
  followScreen(dispatch);
  return (
    <div ref={runMotion} className={frame} style={placement()}>
      <style>{MOTION_CSS}</style>
      <Backdrop />
      <div className={bezelRow}>
        <span className={screw} />
        <span style={{ flex: 1 }}>Arcadia · Ponte di comando</span>
        <span style={{ color: C.green }}>● In rotta</span>
        <span className={screw} />
      </div>
      <div className={screen}>
        <div className={porthole}>
          <div className={`${stars} ${farStars} harlock-anim harlock-far`} />
          <div className={`${stars} ${nearStars} harlock-anim harlock-near`} />
          <div className={glare} />
        </div>
        <Lights />
        <Wheel />
        <Sprite rows={BODY} />
        <Sprite rows={LOCKS} className="harlock-anim harlock-locks" />
        <Sprite rows={HEAD} className="harlock-anim harlock-head" />
        <Hands />
        <div className={scanlines} />
      </div>
    </div>
  );
};
