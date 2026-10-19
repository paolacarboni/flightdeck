// Finto modulo "uebersicht" per gli screenshot: css da Emotion (come Übersicht), run risponde con i dati demo.
export { css } from "@emotion/css";

export const run = (command) => {
  const output = window.__demoOutput;
  return Promise.resolve(/ (board|show)( |$)/.test(command) && output ? output : "");
};
