import { useCallback, useRef, useState } from "react";

export function useConfigHistory(initial) {
  const [state, setState] = useState(() => ({
    past: [],
    present: initial(),
    future: [],
  }));
  const lastEdit = useRef(0);
  const set = useCallback((update) => {
    const now = Date.now(),
      coalesce = now - lastEdit.current < 400;
    lastEdit.current = now;
    setState((s) => {
      const next = typeof update === "function" ? update(s.present) : update;
      if (JSON.stringify(next) === JSON.stringify(s.present)) return s;
      return {
        past:
          coalesce && s.past.length
            ? s.past
            : [...s.past, s.present].slice(-50),
        present: next,
        future: [],
      };
    });
  }, []);
  const undo = useCallback(() => {
    lastEdit.current = 0;
    setState((s) =>
      s.past.length
        ? {
            past: s.past.slice(0, -1),
            present: s.past.at(-1),
            future: [s.present, ...s.future],
          }
        : s,
    );
  }, []);
  const redo = useCallback(() => {
    lastEdit.current = 0;
    setState((s) =>
      s.future.length
        ? {
            past: [...s.past, s.present],
            present: s.future[0],
            future: s.future.slice(1),
          }
        : s,
    );
  }, []);
  return [
    state.present,
    set,
    {
      undo,
      redo,
      canUndo: !!state.past.length,
      canRedo: !!state.future.length,
    },
  ];
}
