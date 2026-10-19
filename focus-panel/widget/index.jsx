import { css, run } from "uebersicht";

// Frog del giorno, un solo time box e scadenze, con l'aspetto del Project Display di cc-panel.
// Colori come in avionica: magenta = frog, verde = box in corso, ambra = ultimi minuti o scadenza
// vicina, rosso = fuori tempo o scaduto, ciano = informazioni e azioni.

const CLI = '"$HOME/.local/bin/focus-panel"';
export const command = `${CLI} show`;
// Solo file locali: il comando è leggero; la barra del box scorre con un'animazione CSS.
export const refreshFrequency = 15 * 1000;

const STORAGE_KEY = "focus-panel.open";
const PARKED = "__parked__";
const OVERDUE = "__overdue__";
const DURATIONS = [15, 30, 60, 90];
const WHEN = [["oggi", "OGGI"], ["domani", "DOMANI"], ["dopo", "PARCHEGGIO"]];
const MAX_DEADLINES = 5;

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
const PHASE_COLOR = { run: C.green, warn: C.amber, over: C.red };

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

const EMPTY_FORM = { visible: false, text: "", minutes: 30, when: null, frog: false };

// Il pannello è disegnato per lo schermo del portatile (1470×918 punti sotto la barra dei menu): su
// un altro schermo si scala sul lato che limita (l'altezza, sull'ultrawide) e occupa la stessa
// porzione di schermo. Margine dall'angolo e dimensioni sono in punti del portatile e si
// scalano con il pannello.
const REF_SCREEN = { w: 1470, h: 918 };
// Griglia comune ai quattro pannelli, in punti del portatile: colonne larghe 470 ai lati, 34 dai
// bordi e 16 tra le righe. Riga alta 479 (cc-panel, news-panel), riga bassa 355 (Harlock a 470 di
// larghezza, focus-panel). Posizione fissa: i pannelli non si trascinano.
const MARGIN = { x: -34, y: -34 }; // dall'angolo di className; negativo verso sinistra o verso l'alto
const HEIGHT = 355;
const screenScale = () => Math.min(window.innerWidth / REF_SCREEN.w, window.innerHeight / REF_SCREEN.h);

const placement = () => {
  const s = screenScale();
  return {
    transform: `translate(${MARGIN.x * s}px, ${MARGIN.y * s}px) scale(${s})`,
    transformOrigin: "bottom right",
    height: HEIGHT,
  };
};

// Ricalcola la scala quando cambia lo schermo (monitor collegato o scollegato). Il gestore sta su
// window perché i widget condividono la pagina e un ricaricamento rivaluta il modulo.
const followScreen = (dispatch) => {
  window.removeEventListener("resize", window.focusPanelResize);
  window.focusPanelResize = () => dispatch({ type: "RESIZE" });
  window.addEventListener("resize", window.focusPanelResize);
};

export const initialState = { data: null, open: loadOpen(), form: EMPTY_FORM, picking: null, toast: null };

const parse = (output) => {
  try {
    return JSON.parse(output);
  } catch (e) {
    return { error: "Risposta non valida da focus-panel" };
  }
};

export const updateState = (event, prev) => {
  switch (event.type) {
    case "UB/COMMAND_RAN":
      if (event.error) return { ...prev, data: { ...(prev.data || {}), error: String(event.error) } };
      return { ...prev, data: parse(event.output) };
    case "TOGGLE": {
      const open = { ...prev.open, [event.key]: !prev.open[event.key] };
      saveOpen(open);
      return { ...prev, open };
    }
    case "FORM":
      return { ...prev, form: { ...prev.form, ...event.form } };
    case "PICK":
      return { ...prev, picking: prev.picking === event.id ? null : event.id };
    case "RESIZE":
      return { ...prev };
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
  setTimeout(() => dispatch({ type: "TOAST", toast: null }), kind === "error" ? 6000 : 2500);
};

const refresh = (dispatch) =>
  run(command)
    .then((output) => dispatch({ type: "UB/COMMAND_RAN", output }))
    .catch((error) => dispatch({ type: "UB/COMMAND_RAN", error }));

// Esegue un comando della CLI, mostra l'esito e rilegge lo stato.
const act = (dispatch, args, after) =>
  run(`${CLI} ${args} 2>&1; echo "exit:$?"`).then((output) => {
    const ok = /exit:0\s*$/.test(output);
    const text = output.replace(/exit:\d+\s*$/, "").trim().split("\n").pop();
    toast(dispatch, text.toUpperCase(), ok ? "ok" : "error");
    if (ok && after) after();
    refresh(dispatch);
  });

const addItem = (dispatch, form, defaultWhen) => {
  if (!form.text.trim()) return;
  const when = form.when || defaultWhen;
  const args = `add ${shellQuote(form.text.trim())} -m ${form.minutes} --when ${when}${form.frog ? " --frog" : ""}`;
  act(dispatch, args, () => dispatch({ type: "FORM", form: { text: "", frog: false } }));
};

// ------------------------------------------------------------------ stile

export const className = `
  bottom: 0;
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
  margin-bottom: 6px;
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
const boxPanel = css`
  border: 1px solid currentColor;
  border-radius: 3px;
  padding: 6px 8px 7px;
  margin: 4px 0 6px;
`;
const boxTrack = css`
  height: 6px;
  margin: 6px 0 5px;
  background: rgba(233, 238, 245, 0.08);
  overflow: hidden;
`;
const boxFill = css`
  height: 100%;
  background: currentColor;
  box-shadow: 0 0 8px currentColor;
  transform-origin: left center;
`;
// Nome dell'animazione diverso da quelli degli altri pannelli: i widget condividono la pagina.
const BOX_KEYFRAMES = `
  @keyframes focus-box { from { transform: scaleX(1); } to { transform: scaleX(0); } }
  @keyframes focus-blink { 50% { opacity: 0.35; } }
  @media (prefers-reduced-motion: reduce) { .focus-anim { animation: none !important; } }
`;
const itemRow = css`
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 4px;
  font-size: 12px;
  border-radius: 3px;
  &:hover { background: rgba(255, 255, 255, 0.05); }
  &:hover .keys { opacity: 1; }
`;
const oneLine = css`
  flex: 1;
  min-width: 0;
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
  user-select: none;
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
const input = css`
  width: 100%;
  box-sizing: border-box;
  background: rgba(86, 227, 255, 0.05);
  border: 1px solid rgba(86, 227, 255, 0.35);
  border-radius: 2px;
  color: ${C.white};
  font-family: ${MONO};
  font-size: 12px;
  padding: 5px 6px;
  outline: none;
  &::placeholder { color: ${C.faint}; }
  &:focus { border-color: ${C.cyan}; }
`;
const chips = css`
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 5px;
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

const hhmm = (seconds) => new Date(seconds * 1000).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
const minutesOf = (seconds) => Math.ceil(Math.abs(seconds) / 60);
const deadlineColor = (days) => (days < 0 ? C.red : days <= 2 ? C.amber : C.cyan);
const daysLabel = (days) => (days < 0 ? `D+${-days}` : days === 0 ? "OGGI" : `D-${days}`);

const Key = ({ color, onClick, children, title }) => (
  <span className={softkey} style={{ color }} title={title} onClick={(e) => { e.stopPropagation(); onClick(); }}>
    {children}
  </span>
);

const Annunciators = ({ data }) => {
  const frog = (data.today || []).find((i) => i.frog);
  const box = data.box;
  const near = (data.deadlines || []).filter((d) => d.days <= 2).length;
  const frogCell = !frog ? ["—", C.faint, false] : frog.doneAt ? ["✓", C.green, false] : ["✗", C.magenta, data.frogFirst];
  const boxCell = box ? [box.phase === "over" ? `+${minutesOf(box.remaining)}′` : `${minutesOf(box.remaining)}′`, PHASE_COLOR[box.phase], box.phase !== "run"] : ["—", C.faint, false];
  const cells = [
    ["FROG", ...frogCell],
    ["BOX", ...boxCell],
    ["SCAD. ≤2G", near || "—", near ? C.amber : C.faint, near > 0],
    ["FUORI TEMPO", data.overToday || "—", data.overToday ? C.red : C.faint, false],
  ];
  return (
    <div className={annunciators}>
      {cells.map(([name, value, color, alert]) => (
        <div key={name} className={annunciator}
          style={alert ? { background: `${color}22`, boxShadow: `inset 0 0 0 1px ${color}` } : {}}>
          <span style={{ color: color === C.faint ? C.faint : color }}>{name}</span>
          <span className={annunciatorValue} style={color === C.faint ? { color: C.faint } : glow(color)}>{value}</span>
        </div>
      ))}
    </div>
  );
};

// Il box attivo: barra che si consuma fino alla scadenza, poi rosso lampeggiante (Parkinson).
const Box = ({ box, dispatch }) => {
  const color = PHASE_COLOR[box.phase];
  const total = box.end - box.start;
  const elapsed = Math.min(total, box.now - box.start);
  const status = box.phase === "over"
    ? `FUORI TEMPO DI ${minutesOf(box.remaining)}′ · CHIUDI: FATTO > PERFETTO`
    : `${minutesOf(box.remaining)}′ RIMASTI · FINE ${hhmm(box.end)}`;
  return (
    <div className={boxPanel} style={{ color }}>
      <style>{BOX_KEYFRAMES}</style>
      <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
        <span>▶</span>
        <span className={oneLine} style={{ color: C.white }} title={box.text}>{box.text}</span>
        <span style={{ fontSize: 10.5, color: C.dim }}>{box.minutes}′{box.extended ? "+10" : ""}</span>
      </div>
      <div className={boxTrack}>
        <div key={`${box.start}-${box.extended}`} className={`${boxFill} focus-anim`}
          style={box.phase === "over"
            ? { transform: "scaleX(1)", animation: "focus-blink 1s steps(2) infinite" }
            : { animation: `focus-box ${total}s linear ${-elapsed}s forwards` }} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10.5, letterSpacing: 0.6 }}>
        <span className={oneLine} style={glow(color)}>{status}</span>
        <Key color={C.green} onClick={() => act(dispatch, "done")}>✓ FATTO</Key>
        {!box.extended && <Key color={C.amber} title="Una sola proroga" onClick={() => act(dispatch, "extend")}>+10′</Key>}
        <Key color={C.dim} onClick={() => act(dispatch, "stop")}>■ STOP</Key>
      </div>
    </div>
  );
};

const Item = ({ item, index, dimmed, canBox, picking, dispatch, today }) => {
  const done = !!item.doneAt;
  const color = done ? C.faint : item.frog ? C.magenta : dimmed ? C.dim : C.white;
  return (
    <div>
      <div className={itemRow} style={{ opacity: dimmed && !done ? 0.55 : 1 }}>
        <span style={{ width: 14, color: item.frog ? C.magenta : C.dim, flexShrink: 0 }}>
          {done ? "✓" : item.frog ? "◆" : index}
        </span>
        <span className={oneLine} title={item.text}
          style={{ ...(item.frog && !done ? glow(color) : { color }), textDecoration: done ? "line-through" : "none" }}>
          {item.text}
        </span>
        <span style={{ fontSize: 10.5, color: C.dim, flexShrink: 0 }}>{item.minutes}′</span>
        {!done && (
          <div className={`${softkeys} keys`}>
            {canBox && <Key color={C.green} onClick={() => dispatch({ type: "PICK", id: item.id })}>▶ BOX</Key>}
            {!item.frog && item.day && <Key color={C.magenta} onClick={() => act(dispatch, `frog ${item.id}`)}>FROG</Key>}
            {today && <Key color={C.cyan} onClick={() => act(dispatch, `move ${item.id} domani`)}>→ DOM.</Key>}
            {item.day ? <Key color={C.dim} onClick={() => act(dispatch, `move ${item.id} dopo`)}>PARK</Key>
              : <Key color={C.cyan} onClick={() => act(dispatch, `move ${item.id} oggi`)}>→ OGGI</Key>}
            {today && <Key color={C.green} onClick={() => act(dispatch, `done ${item.id}`)}>✓</Key>}
            <Key color={C.red} onClick={() => act(dispatch, `drop ${item.id}`)}>✕</Key>
          </div>
        )}
      </div>
      {picking === item.id && (
        <div className={chips} style={{ margin: "0 0 4px 22px" }}>
          <span style={{ fontSize: 10, color: C.dim, alignSelf: "center" }}>DURATA</span>
          {Array.from(new Set([item.minutes, ...DURATIONS])).sort((a, b) => a - b).map((m) => (
            <Key key={m} color={m === item.minutes ? C.green : C.cyan}
              onClick={() => act(dispatch, `start ${item.id} -m ${m}`, () => dispatch({ type: "PICK", id: item.id }))}>
              {m}′
            </Key>
          ))}
        </div>
      )}
    </div>
  );
};

const AddForm = ({ form, defaultWhen, dispatch }) => {
  const when = form.when || defaultWhen;
  return (
    <div style={{ margin: "6px 0 2px" }}>
      <input className={input} value={form.text} autoFocus placeholder="Verbo + oggetto: «Scrivere indice slide»"
        onChange={(e) => dispatch({ type: "FORM", form: { text: e.target.value } })}
        onKeyDown={(e) => {
          if (e.key === "Enter") addItem(dispatch, form, defaultWhen);
          if (e.key === "Escape") dispatch({ type: "FORM", form: { visible: false } });
        }} />
      <div className={chips}>
        {DURATIONS.map((m) => (
          <Key key={m} color={form.minutes === m ? C.green : C.faint} onClick={() => dispatch({ type: "FORM", form: { minutes: m } })}>{m}′</Key>
        ))}
        <span style={{ width: 6 }} />
        {WHEN.map(([value, name]) => (
          <Key key={value} color={when === value ? C.cyan : C.faint} onClick={() => dispatch({ type: "FORM", form: { when: value } })}>{name}</Key>
        ))}
        {when !== "dopo" && (
          <Key color={form.frog ? C.magenta : C.faint} onClick={() => dispatch({ type: "FORM", form: { frog: !form.frog } })}>◆ FROG</Key>
        )}
        <span style={{ marginLeft: "auto" }} />
        <Key color={C.green} onClick={() => addItem(dispatch, form, defaultWhen)}>↵ AGGIUNGI</Key>
      </div>
    </div>
  );
};

const Deadline = ({ entry }) => {
  const color = deadlineColor(entry.days);
  return (
    <div className={itemRow} style={{ cursor: entry.url ? "pointer" : "default", fontSize: 11.5 }}
      onClick={() => openUrl(entry.url)} title={entry.url || entry.due}>
      <span style={{ ...glow(color), width: 34, flexShrink: 0, fontSize: 10.5 }}>{daysLabel(entry.days)}</span>
      {entry.key && <span style={{ color: C.dim, fontSize: 10.5, flexShrink: 0 }}>{entry.key}</span>}
      <span className={oneLine}>{entry.title}</span>
    </div>
  );
};

const Deadlines = ({ data, open, dispatch }) => {
  const all = data.deadlines || [];
  const overdue = all.filter((d) => d.days < 0);
  const upcoming = all.filter((d) => d.days >= 0).slice(0, MAX_DEADLINES);
  if (!all.length && !data.jiraError) return null;
  return (
    <div>
      <div className={sectionLabel}>SCADENZE · 7 GIORNI{data.syncing ? " · SYNC" : ""}</div>
      {upcoming.map((entry) => <Deadline key={entry.key || `l${entry.id}`} entry={entry} />)}
      {!upcoming.length && <div style={{ fontSize: 11, color: C.faint, padding: "2px 4px" }}>NESSUNA NEI PROSSIMI 7 GIORNI</div>}
      {overdue.length > 0 && (
        <div>
          <div className={itemRow} style={{ cursor: "pointer", fontSize: 10.5, color: C.red }} onClick={() => dispatch({ type: "TOGGLE", key: OVERDUE })}>
            {open[OVERDUE] ? "▾" : "◇"} {overdue.length} SCADUTE · AGGIORNA LA DATA O CHIUDI
          </div>
          {open[OVERDUE] && overdue.map((entry) => <Deadline key={entry.key || `l${entry.id}`} entry={entry} />)}
        </div>
      )}
      {data.jiraError && <div style={{ color: C.amber, fontSize: 10.5, padding: "2px 4px" }} title={data.jiraError}>JIRA: {data.jiraError}</div>}
    </div>
  );
};

export const render = ({ data, open, form, picking, toast: message }, dispatch) => {
  followScreen(dispatch);
  const ready = data && data.today;
  const defaultWhen = ready && data.planMode ? "domani" : "oggi";
  const today = (ready && data.today) || [];
  const tomorrow = (ready && data.tomorrow) || [];
  const parked = (ready && data.parked) || [];
  const box = ready && data.box ? { ...data.box, now: data.now } : null;
  const showTomorrow = ready && (data.planMode || tomorrow.length > 0);
  const planAlert = ready && data.planMode && !data.tomorrowFrog;

  return (
    <div className={bezel} style={placement()}>
      <div className={bezelRow}>
        <span className={screw} />
        <span style={{ flex: 1 }}>Focus · MFD 3</span>
        <span style={{ color: box ? PHASE_COLOR[box.phase] : C.dim }}>● {box ? "BOX" : "STBY"}</span>
        <span className={screw} />
      </div>
      <div className={screen}>
        {!ready && <div style={{ color: data && data.error ? C.amber : C.green, fontSize: 12 }}>{data && data.error ? data.error : "AVVIO…"}</div>}
        {ready && (
          <div>
            <Annunciators data={data} />
            {box && <Box box={box} dispatch={dispatch} />}
            <div className={sectionLabel}>OGGI · {today.length}/{data.maxPerDay}{data.frogFirst ? " · PRIMA IL FROG" : ""}</div>
            {!today.length && <div style={{ fontSize: 11, color: C.faint, padding: "2px 4px" }}>NESSUNA VOCE: SCEGLI IL FROG</div>}
            {today.map((item, index) => (
              <Item key={item.id} item={item} index={index + 1} today dispatch={dispatch} picking={picking}
                canBox={!box} dimmed={data.frogFirst && !item.frog} />
            ))}
            {showTomorrow && (
              <div>
                <div className={sectionLabel} style={planAlert ? { color: C.amber } : {}}>
                  ☾ DOMANI · {tomorrow.length}/{data.maxPerDay}{planAlert ? " · SCEGLI IL FROG" : ""}
                </div>
                {tomorrow.map((item, index) => (
                  <Item key={item.id} item={item} index={index + 1} dispatch={dispatch} picking={picking} canBox={false} />
                ))}
              </div>
            )}
            {form.visible && <AddForm form={form} defaultWhen={defaultWhen} dispatch={dispatch} />}
            <Deadlines data={data} open={open} dispatch={dispatch} />
            {parked.length > 0 && (
              <div>
                <div className={sectionLabel} style={{ cursor: "pointer" }} onClick={() => dispatch({ type: "TOGGLE", key: PARKED })}>
                  {open[PARKED] ? "▾" : "◇"} PARCHEGGIO · {parked.length}
                </div>
                {open[PARKED] && parked.map((item) => (
                  <Item key={item.id} item={item} index="·" dispatch={dispatch} picking={picking} canBox={false} />
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
        <span className={hardkey} onClick={() => dispatch({ type: "FORM", form: { visible: !form.visible } })}>
          {form.visible ? "✕ CHIUDI" : "+ AGGIUNGI"}
        </span>
        <span className={hardkey} onClick={() => act(dispatch, "sync")}>⟳ JIRA</span>
        <span className={clock}>{ready ? hhmm(data.now) : "--:--"}</span>
      </div>
    </div>
  );
};
