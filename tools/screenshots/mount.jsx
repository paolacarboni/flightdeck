// Monta un widget Übersicht come fa Übersicht: stato da initialState, primo comando, render(state, dispatch).
import { useEffect, useReducer } from "react";
import { createRoot } from "react-dom/client";
import { css } from "@emotion/css";

const Widget = ({ widget }) => {
  const reduce = (state, event) => (widget.updateState ? widget.updateState(event, state) : state);
  const [state, dispatch] = useReducer(reduce, widget.initialState || {});
  useEffect(() => {
    if (window.__demoOutput) dispatch({ type: "UB/COMMAND_RAN", output: window.__demoOutput });
  }, []);
  return (
    <div className={`widget ${css`position: absolute; ${widget.className || ""}`}`}>
      {widget.render(state, dispatch)}
    </div>
  );
};

export const mount = (widget) => createRoot(document.getElementById("root")).render(<Widget widget={widget} />);
