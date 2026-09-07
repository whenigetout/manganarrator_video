import React from "react";
import { createRoot } from "react-dom/client";
import { AudioVideoStudio } from "./AudioVideoStudio";
import "./studio.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AudioVideoStudio apiBase={import.meta.env.VITE_API_BASE || ""} />
  </React.StrictMode>,
);
