import { useEffect, useState } from "react";
import { exportRequest } from "./config";

export function useLiveFrame(client, config, source, seconds, enabled) {
  const [frame, setFrame] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const serialized = JSON.stringify(exportRequest(config, source));
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const timer = setTimeout(async () => {
      try {
        const result = await client.frame(
          JSON.parse(serialized),
          seconds,
          !source,
          controller.signal,
        );
        if (!active) return;
        const url = URL.createObjectURL(result.blob);
        setFrame({ url, timestamp: result.timestamp, config: serialized });
      } catch (e) {
        if (active && e.name !== "AbortError") setError(e.message);
      } finally {
        if (active) setLoading(false);
      }
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [client, serialized, seconds, enabled, Boolean(source)]);
  useEffect(
    () => () => {
      if (frame?.url) URL.revokeObjectURL(frame.url);
    },
    [frame],
  );
  return { frame, loading, error };
}
