import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AudioVideoStudio } from "./AudioVideoStudio";
import { StoryStudio } from "./StoryStudio";
import "./studio.css";

function Studios() {
  const sites = import.meta.env.VITE_STORY_SITE === "1";
  const [connection, setConnection] = useState(sites ? { preparation: true } : null);
  const [mode, setMode] = useState(window.location.hash);
  const story = mode === "#story" || mode === "#story-local";
  const shared = mode === "#story" && connection?.preparation;
  useEffect(() => {
    const changed = () => setMode(window.location.hash);
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    if (sites) return;
    const base = import.meta.env.VITE_API_BASE || "";
    fetch(`${base}/video/story-connection`)
      .then((response) => {
        if (!response.ok) throw new Error("Story connection unavailable");
        return response.json();
      })
      .then(setConnection)
      .catch(() => setConnection({ error: true }));
  }, [sites]);
  if (sites) return <StoryStudio preparation />;
  return (
    <>
      <nav className="studio-switcher" aria-label="Studio mode">
        <a href="#audio" className={!story ? "active" : ""}>
          Audio Studio
        </a>
        <a href="#story" className={mode === "#story" ? "active" : ""}>
          Story Studio
        </a>
        {connection?.preparation && (
          <a href="#story-local" className={mode === "#story-local" ? "active" : ""}>
            Local Story Rendering
          </a>
        )}
      </nav>
      {story ? (
        connection?.error ? (
          <p role="alert">Unable to determine the Story Studio connection.</p>
        ) : connection ? (
          <StoryStudio
            key={shared ? "shared" : "local"}
            preparation={!!shared}
            apiBase={`${import.meta.env.VITE_API_BASE || ""}${shared ? "/shared-story" : ""}`}
          />
        ) : <p role="status">Connecting to Story Studio…</p>
      ) : (
        <AudioVideoStudio apiBase={import.meta.env.VITE_API_BASE || ""} />
      )}
    </>
  );
}
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Studios />
  </React.StrictMode>,
);
