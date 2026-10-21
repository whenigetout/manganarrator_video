import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AudioVideoStudio } from "./AudioVideoStudio";
import { StoryStudio } from "./StoryStudio";
import "./studio.css";

function Studios() {
  const [story, setStory] = useState(window.location.hash === "#story");
  useEffect(() => {
    const changed = () => setStory(window.location.hash === "#story");
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return (
    <>
      <nav className="studio-switcher" aria-label="Studio mode">
        <a href="#audio" className={!story ? "active" : ""}>
          Audio Studio
        </a>
        <a href="#story" className={story ? "active" : ""}>
          Story Studio
        </a>
      </nav>
      {story ? (
        <StoryStudio apiBase={import.meta.env.VITE_API_BASE || ""} />
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
