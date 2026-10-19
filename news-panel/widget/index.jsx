import { css, run } from "uebersicht";

// Rassegna quotidiana su AI, LLM e tecnologia con l'aspetto del Project Display di cc-panel (stessa
// cornice, schermo e tasti), senza arco radar. Colori come in avionica: magenta = tema principale,
// ambra = molto caldo, verde = caldo, ciano = informazioni e link.

const CLI = '"$HOME/.local/bin/news-panel"';
export const command = `${CLI} show`;
export const refreshFrequency = 5 * 60 * 1000;

const STORAGE_KEY = "news-panel.open";
const PICKS = "__picks__";
const SOURCES = "__sources__";

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
const MARGIN = { x: -34, y: 34 }; // dall'angolo di className; negativo verso sinistra o verso l'alto
const HEIGHT = 479;
const screenScale = () => Math.min(window.innerWidth / REF_SCREEN.w, window.innerHeight / REF_SCREEN.h);

const placement = () => {
  const s = screenScale();
  return {
    transform: `translate(${MARGIN.x * s}px, ${MARGIN.y * s}px) scale(${s})`,
    transformOrigin: "top right",
    height: HEIGHT,
  };
};

// Ricalcola la scala quando cambia lo schermo (monitor collegato o scollegato). Il gestore sta su
// window perché i widget condividono la pagina e un ricaricamento rivaluta il modulo.
const followScreen = (dispatch) => {
  window.removeEventListener("resize", window.newsPanelResize);
  window.newsPanelResize = () => dispatch({ type: "RESIZE" });
  window.addEventListener("resize", window.newsPanelResize);
};

export const initialState = { data: null, open: loadOpen(), loading: false, toast: null };

const parse = (output) => {
  try {
    return JSON.parse(output);
  } catch (e) {
    return { topics: [], picks: [], sources: [], error: "Risposta non valida da news-panel" };
  }
};

export const updateState = (event, prev) => {
  switch (event.type) {
    case "UB/COMMAND_RAN":
      if (event.error) {
        return { ...prev, loading: false, data: { ...(prev.data || { topics: [], picks: [], sources: [] }), error: String(event.error) } };
      }
      return { ...prev, loading: false, data: parse(event.output) };
    case "TOGGLE": {
      const open = { ...prev.open, [event.key]: !prev.open[event.key] };
      saveOpen(open);
      return { ...prev, open };
    }
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
const openUrl = (url) => /^https?:\/\//.test(url || "") && run(`open ${shellQuote(url)}`);

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

// Nuova edizione subito: raccolta e sintesi richiedono un minuto circa.
const fetchNow = (dispatch) => {
  toast(dispatch, "RACCOLGO LE NOTIZIE…", "info");
  dispatch({ type: "LOADING" });
  run(`${CLI} fetch 2>&1; echo "exit:$?"`).then((output) => {
    const ok = /exit:0\s*$/.test(output);
    const lines = output.replace(/exit:\d+\s*$/, "").trim().split("\n");
    toast(dispatch, ok ? lines[0].toUpperCase() : lines[lines.length - 1], ok ? "ok" : "error");
    refresh(dispatch);
  });
};

// ------------------------------------------------------------------ stile

export const className = `
  top: 0;
  right: 0;
  width: 470px;
  font-family: ${MONO};
  color: ${C.white};
  -webkit-font-smoothing: antialiased;
  font-feature-settings: "tnum";
`;

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
const headline = css`
  font-size: 11.5px;
  line-height: 1.4;
  color: ${C.green};
  padding: 6px 4px 2px;
  text-shadow: 0 0 6px rgba(73, 240, 124, 0.35);
`;
const topicRow = css`
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
const summaryText = css`
  font-size: 11px;
  line-height: 1.45;
  color: ${C.dim};
  padding: 2px 4px 4px;
`;
const itemRow = css`
  position: relative;
  display: flex;
  gap: 7px;
  padding: 4px 4px;
  font-size: 11.5px;
  line-height: 1.35;
  border-radius: 3px;
  cursor: pointer;
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

const heatColor = (topic, index) => (index === 0 ? C.magenta : topic.heat >= 4 ? C.amber : topic.heat === 3 ? C.green : C.cyan);

// Barra del calore a cinque segmenti, come un indicatore di livello.
const Heat = ({ value, color }) => (
  <span className={tag} style={{ letterSpacing: 1 }} title={`Calore ${value}/5`}>
    {[1, 2, 3, 4, 5].map((n) => (
      <span key={n} style={n <= value ? { color, textShadow: `0 0 5px ${color}66` } : { color: C.faint }}>▮</span>
    ))}
  </span>
);

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
// largo migliaia di pixel costringe WebKit a ridisegnarlo a ogni fotogramma (~11% di CPU).
const tickerTrack = css`
  display: inline-block;
  & > span { display: inline-block; will-change: transform; }
`;
// Nome dell'animazione diverso da quello di cc-panel: i due widget condividono la pagina.
const TICKER_KEYFRAMES = `
  @keyframes news-ticker { from { transform: translateX(0); } to { transform: translateX(calc(-1 * var(--news-ticker-shift))); } }
  @media (prefers-reduced-motion: reduce) { .news-ticker-track > span { animation: none !important; } }
`;
// Spostamento di un giro: la larghezza di una delle due copie, misurata dopo il layout.
const setTickerShift = (track) => {
  if (track) track.style.setProperty("--news-ticker-shift", `${track.getBoundingClientRect().width / 2}px`);
};

// Nastro con i titoli delle notizie dei temi caldi.
const Ticker = ({ items }) => {
  if (!items.length) return null;
  const text = items.map((i) => `${i.source} ${i.title}`).join(" ◆ ");
  const seconds = Math.max(30, Math.round(text.length * TICKER_SECONDS_PER_CHAR));
  const entries = (copy) => items.map((item, index) => (
    <span key={`${copy}-${index}`} style={{ color: C.green, marginRight: 22, animation: `news-ticker ${seconds}s linear infinite` }}>
      <span style={{ color: C.dim }}>{item.source.toUpperCase()}</span> {item.title.toUpperCase()}
      <span style={{ color: C.faint, marginLeft: 22 }}>◆</span>
    </span>
  ));
  return (
    <div className={tickerStyle}>
      <style>{TICKER_KEYFRAMES}</style>
      <div ref={setTickerShift} className={`${tickerTrack} news-ticker-track`}>
        {entries("a")}{entries("b")}
      </div>
    </div>
  );
};

const Annunciators = ({ data }) => {
  const topics = data.topics || [];
  const sources = data.sources || [];
  const hot = topics.filter((t) => t.heat >= 4).length;
  const down = sources.filter((s) => !s.ok).length;
  const cells = [
    ["TEMI", topics.length, C.green, false],
    ["CALDI", hot, C.amber, false],
    ["NOTIZIE", data.count || 0, C.cyan, false],
    [down ? "FONTI KO" : "FONTI", down ? down : sources.length, down ? C.amber : C.cyan, down > 0],
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

const News = ({ item, note }) => (
  <div className={itemRow} title={`${item.title}\n${item.url}`} onClick={() => openUrl(item.url)}>
    <span style={{ color: C.cyan, flexShrink: 0 }}>▸</span>
    <div className={itemText}>
      <div className={oneLine} style={{ color: C.white }}>{item.title}</div>
      <div className={oneLine} style={{ color: C.dim, fontSize: 10.5 }}>
        {item.source.toUpperCase()}{item.score !== null && item.score !== undefined ? ` · ${item.score}▲` : ""}
        {note ? <span style={{ color: C.cyan }}> · {note}</span> : null}
      </div>
    </div>
    <div className={`${softkeys} keys`}>
      <span className={softkey} style={{ color: C.green }} onClick={(e) => { e.stopPropagation(); openUrl(item.url); }}>LEGGI</span>
      {item.commentsUrl && item.commentsUrl !== item.url && (
        <span className={softkey} style={{ color: C.cyan }} onClick={(e) => { e.stopPropagation(); openUrl(item.commentsUrl); }}>DISCUSS.</span>
      )}
    </div>
  </div>
);

const Topic = ({ topic, index, isOpen, dispatch }) => {
  const color = heatColor(topic, index);
  const key = `topic:${topic.title}`;
  return (
    <div>
      <div className={topicRow} onClick={() => dispatch({ type: "TOGGLE", key })}>
        <span style={{ color, flexShrink: 0, width: 12 }}>{isOpen ? "▾" : "◇"}</span>
        <span className={tag} style={{ color: C.dim, width: 58 }}>{topic.area}</span>
        <span className={label} style={glow(color)} title={topic.summary}>{topic.title}</span>
        <Heat value={topic.heat} color={color} />
      </div>
      {isOpen && (
        <div className={detail}>
          <div className={summaryText}>{topic.summary}</div>
          {topic.items.map((item) => <News key={item.url} item={item} />)}
        </div>
      )}
    </div>
  );
};

const Sources = ({ sources }) => (
  <div className={detail}>
    {sources.map((s) => (
      <div key={s.name} className={oneLine} style={{ fontSize: 10.5, padding: "2px 4px", color: s.ok ? C.dim : C.amber }}
        title={s.error || ""}>
        <span style={{ color: s.ok ? (s.count ? C.green : C.faint) : C.amber }}>{s.ok ? "●" : "✕"}</span> {s.name.toUpperCase()}
        <span style={{ color: C.faint }}> · {s.ok ? `${s.count}` : s.error}</span>
      </div>
    ))}
  </div>
);

export const render = ({ data, open, loading, toast: message }, dispatch) => {
  followScreen(dispatch);
  const topics = (data && data.topics) || [];
  const picks = (data && data.picks) || [];
  const sources = (data && data.sources) || [];
  const busy = loading || (data && data.fetching);
  const edition = data && data.updatedAt
    ? new Date(data.updatedAt * 1000).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "--/-- --:--";
  // Se la sintesi non c'è (Haiku non disponibile), le letture consigliate restano aperte.
  const picksOpen = topics.length ? !!open[PICKS] : true;

  return (
    <div className={bezel} style={placement()}>
      <div className={bezelRow}>
        <span className={screw} />
        <span style={{ flex: 1 }}>Tech Briefing · MFD 2</span>
        <span style={{ color: busy ? C.amber : C.green }}>● {busy ? "SYNC" : "LINK"}</span>
        <span className={screw} />
      </div>
      <div className={screen}>
        {(!data || (!data.edition && data.fetching)) && <div style={{ color: C.green, fontSize: 12 }}>RACCOLTA IN CORSO…</div>}
        {data && (data.edition || !data.fetching) && (
          <div>
            <Annunciators data={data} />
            <Ticker items={topics.flatMap((t) => t.items.slice(0, 1))} />
            {data.headline && <div className={headline}>{data.headline}</div>}
            {data.error && <div style={{ color: C.amber, fontSize: 10.5, margin: "4px 0" }} title={data.error}>{data.error}</div>}
            {topics.length > 0 && <div className={sectionLabel}>ARGOMENTI CALDI · CALORE</div>}
            {topics.map((topic, index) => (
              <Topic key={topic.title} topic={topic} index={index} isOpen={!!open[`topic:${topic.title}`]} dispatch={dispatch} />
            ))}
            {picks.length > 0 && (
              <div>
                <div className={sectionLabel} style={{ cursor: "pointer", color: C.cyan }} onClick={() => dispatch({ type: "TOGGLE", key: PICKS })}>
                  {picksOpen ? "▾" : "◇"} DA LEGGERE · {picks.length}
                </div>
                {picksOpen && picks.map((item) => <News key={item.url} item={item} note={item.why} />)}
              </div>
            )}
            {sources.length > 0 && (
              <div>
                <div className={sectionLabel} style={{ cursor: "pointer" }} onClick={() => dispatch({ type: "TOGGLE", key: SOURCES })}>
                  {open[SOURCES] ? "▾" : "◇"} FONTI · {sources.filter((s) => s.ok).length}/{sources.length}
                </div>
                {open[SOURCES] && <Sources sources={sources} />}
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
        <span className={hardkey} onClick={() => fetchNow(dispatch)}>⟳ NUOVA EDIZIONE</span>
        <span className={hardkey} onClick={() => openUrl("https://news.ycombinator.com/")}>HN ↗</span>
        <span className={hardkey} onClick={() => openUrl("https://huggingface.co/papers")}>PAPERS ↗</span>
        <span className={clock}>{edition}</span>
      </div>
    </div>
  );
};
