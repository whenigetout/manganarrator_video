"use client";
import React, { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Upload,
  Save,
  Undo2,
  Copy,
  Play,
  Download,
  Lock,
  Unlock,
  Plus,
  Film,
  AudioLines,
  Image as ImageIcon,
  Clock,
  CheckCircle2,
} from "lucide-react";
import "./story.css";

const sections = [
  "Library",
  "Manuscript",
  "Voices",
  "Visuals",
  "Timeline",
  "Export",
];
const clone = (value) => JSON.parse(JSON.stringify(value));
const allScenes = (p) =>
  p?.arcs.flatMap((a) => a.chapters.flatMap((c) => c.scenes)) || [];
const id = (prefix) => `${prefix}_${crypto.randomUUID()}`;
const secs = (n) => `${Number(n || 0).toFixed(2)}s`;
function download(name, value) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function lineDiff(before, after) {
  const a = before.split("\n"),
    b = after.split("\n");
  if (a.length * b.length > 200000)
    return [
      { kind: "removed", text: before },
      { kind: "added", text: after },
    ];
  const dp = Array.from(
    { length: a.length + 1 },
    () => new Uint32Array(b.length + 1),
  );
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      dp[i][j] =
        a[i] === b[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const rows = [];
  let i = 0,
    j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      rows.push({ kind: "same", text: a[i++] });
      j++;
    } else if (j < b.length && (i === a.length || dp[i][j + 1] >= dp[i + 1][j]))
      rows.push({ kind: "added", text: b[j++] });
    else rows.push({ kind: "removed", text: a[i++] });
  }
  return rows;
}

const newScene = (title, text = "Begin writing here.") => ({
  id: id("scene"), title, segments: [{ id: id("line"), kind: "narration", text }],
});

export function StoryStudio({ apiBase = "", preparation = false }) {
  const base = apiBase.replace(/\/$/, "");
  const [library, setLibrary] = useState([]),
    [doc, setDoc] = useState(null),
    [section, setSection] = useState("Library");
  const [chapterId, setChapterId] = useState(""),
    [sceneId, setSceneId] = useState("");
  const [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newText, setNewText] = useState("");
  const [timeline, setTimeline] = useState(null),
    [history, setHistory] = useState([]),
    [restoreTo, setRestoreTo] = useState("");
  const [jobs, setJobs] = useState([]),
    [job, setJob] = useState(null),
    [showDiff, setShowDiff] = useState(false);
  const [resolution, setResolution] = useState("1280x720");
  const undo = useRef([]),
    generation = useRef(0);
  const chapters =
    doc?.arcs.flatMap((a) =>
      a.chapters.map((c) => ({ ...c, arcTitle: a.title })),
    ) || [];
  const chapter = chapters.find((c) => c.id === chapterId) || chapters[0];
  const scene =
    chapter?.scenes.find((s) => s.id === sceneId) || chapter?.scenes[0];
  const assets = doc?.assets || [];
  const url = (path) => `${base}/video/story${path}`;
  async function request(path, options = {}) {
    const response = await fetch(url(path), {
      ...options,
      headers:
        options.body instanceof FormData
          ? undefined
          : { "Content-Type": "application/json" },
    });
    const value = await response.json();
    if (!response.ok)
      throw new Error(
        typeof value.detail === "string"
          ? value.detail
          : JSON.stringify(value.detail || value),
      );
    return value;
  }
  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function refreshLibrary() {
    setLibrary(await request("/projects"));
  }
  function accept(p) {
    if (doc?.id !== p.id) {
      setJob(null);
      setJobs([]);
      setTimeline(null);
      setHistory([]);
    }
    setDoc(p);
    setDirty(false);
    undo.current = [];
  }
  async function refresh(p, selectedChapter) {
    const ticket = ++generation.current;
    const [t, h, j] = await Promise.all([
      request(
        `/projects/${p.id}/timeline?chapter_id=${encodeURIComponent(selectedChapter || p.arcs[0].chapters[0].id)}`,
      ),
      request(`/projects/${p.id}/history`),
      preparation ? Promise.resolve([]) : request(`/projects/${p.id}/renders`),
    ]);
    if (ticket === generation.current) {
      setTimeline(t);
      setHistory(h);
      setJobs(j);
    }
  }
  useEffect(() => {
    act(refreshLibrary);
  }, []);
  useEffect(() => {
    if (doc && !dirty)
      refresh(doc, chapter?.id).catch((e) => setError(e.message));
  }, [doc?.id, doc?.revision, chapter?.id]);
  useEffect(() => {
    if (!job || job.status !== "processing") return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch(`${base}/video/status/${job.job_id}`);
        const j = await r.json();
        if (!cancelled) {
          setJob(j);
          if (j.status !== "processing")
            refresh(doc, chapter?.id).catch((e) => setError(e.message));
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    };
    const timer = setInterval(poll, 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [job?.job_id, job?.status]);
  function edit(fn) {
    const p = clone(doc);
    undo.current.push(clone(doc));
    if (undo.current.length > 50) undo.current.shift();
    fn(p);
    setDoc(p);
    setDirty(true);
  }
  function editScene(fn) {
    edit((p) => fn(allScenes(p).find((s) => s.id === scene.id)));
  }
  function editLine(lineId, key, value) {
    editScene((s) => {
      s.segments.find((l) => l.id === lineId)[key] = value;
    });
  }
  async function save(p = doc) {
    if (!dirty && p === doc) return p;
    const updated = await request(`/projects/${p.id}`, {
      method: "PUT",
      body: JSON.stringify(p),
    });
    accept(updated);
    return updated;
  }
  useEffect(() => {
    if (!preparation || !dirty || busy || error) return;
    const timer = setTimeout(() => act(() => save()), 1500);
    return () => clearTimeout(timer);
  }, [preparation, doc, dirty, busy, error]);

  useEffect(() => {
    if (!preparation || !dirty) return;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = true;
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [preparation, dirty]);

  async function createProject(event) {
    event.preventDefault();
    await act(async () => {
      if (dirty) await save();
      const title = newTitle.trim();
      const text = newText;
      const p = await request("/import", {
        method: "POST",
        body: JSON.stringify({
          format: "json",
          content: JSON.stringify({
            id: id("project"), title, series_title: title,
            arcs: [{ id: id("arc"), title: "Story", chapters: [{
              id: id("chapter"), title: "Chapter 1", scenes: [newScene("Scene 1", text.trim() ? text : undefined)],
            }] }],
          }),
        }),
      });
      accept(p);
      setNewTitle("");
      setNewText("");
      setSection("Manuscript");
      await refreshLibrary();
    });
  }

  async function closeProject() {
    if (dirty) await save();
    generation.current += 1;
    setDoc(null);
    setChapterId("");
    setSceneId("");
    setJob(null);
    setJobs([]);
    setHistory([]);
    setTimeline(null);
    setSection("Library");
    await refreshLibrary();
  }

  function deleteProject(p) {
    if (!window.confirm(`Delete “${p.title}” from your Story Studio library?`)) return;
    act(async () => {
      await request(`/projects/${p.id}?revision=${p.revision}`, { method: "DELETE" });
      await refreshLibrary();
    });
  }

  async function open(p) {
    if (dirty) await save();
    const next = await request(`/projects/${p.id}`);
    accept(next);
    setChapterId("");
    setSceneId("");
    setSection("Manuscript");
    setJob(null);
  }
  async function importFile(file) {
    if (!file) return;
    await act(async () => {
      if (dirty) await save();
      const p = await request("/import", {
        method: "POST",
        body: JSON.stringify({
          format: file.name.endsWith(".json") ? "json" : "markdown",
          content: await file.text(),
        }),
      });
      accept(p);
      setChapterId("");
      setSceneId("");
      setSection("Manuscript");
      await refreshLibrary();
    });
  }
  async function upload(file, kind, segmentId = null, shotId = null) {
    if (!file) return;
    await act(async () => {
      const p = await save();
      const data = new FormData();
      data.append("file", file);
      data.append("kind", kind);
      data.append("revision", p.revision);
      if (segmentId) data.append("segment_id", segmentId);
      const r = await request(`/projects/${p.id}/assets`, {
        method: "POST",
        body: data,
      });
      if (shotId) {
        allScenes(r.project)
          .find((s) => s.id === scene.id)
          .shots.find((s) => s.id === shotId).image_asset_id = r.asset.id;
        accept(
          await request(`/projects/${p.id}`, {
            method: "PUT",
            body: JSON.stringify(r.project),
          }),
        );
      } else accept(r.project);
    });
  }
  const media = (a) => url(`/projects/${doc.id}/assets/${a}`);
  async function render(selectedScene) {
    await act(async () => {
      const p = await save();
      const [width, height] = resolution.split("x").map(Number);
      const j = await request(`/projects/${p.id}/render`, {
        method: "POST",
        body: JSON.stringify({
          revision: p.revision,
          chapter_id: chapter.id,
          scene_id: selectedScene || null,
          width,
          height,
          fps: 24,
        }),
      });
      setJob(j);
      setSection("Export");
    });
  }
  function exportManuscript() {
    const p = clone(doc);
    p.assets = [];
    p.revision = 0;
    allScenes(p).forEach((s) => {
      s.segments.forEach((l) => (l.audio_asset_id = null));
      s.shots.forEach((v) => (v.image_asset_id = null));
      s.audio_layers = [];
    });
    download("story-manuscript.json", p);
  }
  const done =
    job?.status === "done" ? job : jobs.find((j) => j.status === "done");
  const renderUrl = (j, file) =>
    url(`/projects/${doc.id}/renders/${j.job_id}/${file}`);
  const spoken = allScenes(doc)
    .flatMap((s) => s.segments)
    .filter((l) => l.kind !== "silence");
  const measured = spoken.filter((l) => l.audio_asset_id).length;
  const draftText =
    scene?.segments
      .map((l) =>
        l.kind === "silence"
          ? `[Pause ${secs(l.silence_seconds)}]`
          : `${l.kind === "narration" ? "Narrator" : doc.characters.find((c) => c.id === l.character_id)?.name || "Speaker"}: ${l.text}`,
      )
      .join("\n") || "";

  return (
    <div className="story-app">
      <aside className="story-nav">
        <div className="story-brand">
          <BookOpen size={26} />
          <span>
            STORY<span>STUDIO</span>
          </span>
        </div>
        <p className="story-overline">FROM PAGE TO PICTURE</p>
        <nav aria-label="Story sections">
          {sections.filter((name) => name === "Library" || (doc && (!preparation || !["Voices", "Export"].includes(name)))).map((name, i) => (
            <button
              key={name}
              className={section === name ? "active" : ""}
              disabled={busy}
              onClick={() => name === "Library" && doc ? act(closeProject) : setSection(name)}
            >
              <span>0{i + 1}</span>
              {name}
            </button>
          ))}
        </nav>
        <div className="story-nav-note">
          A story worth telling.
          <br />
          One scene at a time.
        </div>
      </aside>
      <main className="story-main">
        <header className="story-header">
          <div>
            <p className="story-overline">YOUR PRODUCTION DESK</p>
            <h1>{doc ? doc.title : "Make room for your story."}</h1>
            <p>
              {doc
                ? `${doc.series_title || "Untitled series"} · Revision ${doc.revision}`
                : "Bring a manuscript. Find its voices. Build the first episode."}
            </p>
          </div>
          <div className="story-actions">
            <label className="story-button">
              <Upload size={16} />
              Import manuscript
              <input
                aria-label="Import manuscript"
                type="file"
                accept=".md,.json"
                disabled={busy}
                onChange={(e) => {
                  importFile(e.target.files[0]);
                  e.target.value = "";
                }}
              />
            </label>
            {doc && (
              <button
                className="story-primary"
                disabled={busy || !dirty}
                onClick={() => act(() => save())}
              >
                <Save size={16} />
                {dirty ? "Save draft" : "Saved"}
              </button>
            )}
          </div>
        </header>
        {error && (
          <div role="alert" className="story-error">
            {error}
            {preparation && dirty && doc && (
              <button onClick={exportManuscript}>Download unsaved manuscript</button>
            )}
          </div>
        )}
        {busy && (
          <p role="status" className="story-working">
            Working…
          </p>
        )}
        {section === "Library" ? (
          <>
            <div className="story-section-title">
              <h2>Your story library</h2>
              <span>{library.length} projects</span>
            </div>
            {preparation && (
              <form className="story-line" onSubmit={createProject}>
                <label>Project title
                  <input required value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
                </label>
                <label>Story text
                  <textarea value={newText} onChange={(e) => setNewText(e.target.value)} />
                </label>
                <button disabled={busy || !newTitle.trim()} type="submit">Create project</button>
              </form>
            )}
            <div className="story-project-grid">
              {library.map((p) => (
                <div key={p.id}>
                <button
                  className="story-project story-project-open"
                  disabled={busy}
                  onClick={() => act(() => open(p))}
                >
                  <BookOpen />
                  <span className="story-overline">
                    {p.series_title || "STORY PROJECT"}
                  </span>
                  <h3>{p.title}</h3>
                  <p>
                    Revision {p.revision} <span>Open manuscript →</span>
                  </p>
                </button>
                <button disabled={busy} aria-label={`Delete ${p.title}`} onClick={() => deleteProject(p)}>
                  Delete project
                </button>
                </div>
              ))}
              {!library.length && (
                <div className="story-empty">
                  <BookOpen size={42} />
                  <h2>The first page starts here.</h2>
                  <p>
                    Import structured Markdown or a Story Studio JSON file. Your
                    source stays intact while you shape a separate production
                    draft.
                  </p>
                  <p className="story-muted">
                    Markdown uses four heading levels with stable IDs, then
                    [line-id] NARRATOR: text or [line-id] CHARACTER: dialogue. A
                    sample is included in fixtures/story-demo.md.
                  </p>
                </div>
              )}
            </div>
          </>
        ) : !doc ? (
          <div className="story-empty">
            <h2>Choose a story first.</h2>
            <p>Open a project in Library or import your manuscript.</p>
          </div>
        ) : (
          <>
            <div className="story-toolbar">
              <label>
                Chapter
                <select
                  aria-label="Chapter"
                  value={chapter?.id || ""}
                  disabled={busy}
                  onChange={(e) => {
                    setChapterId(e.target.value);
                    setSceneId("");
                  }}
                >
                  {chapters.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.arcTitle} / {c.title}
                    </option>
                  ))}
                </select>
              </label>
              {preparation && (
                <>
                  <label>Project name
                    <input disabled={busy} value={doc.title} onChange={(e) => edit((p) => { p.title = e.target.value; })} />
                  </label>
                  <label>Chapter name
                    <input disabled={busy} value={chapter.title} onChange={(e) => edit((p) => {
                      p.arcs.flatMap((a) => a.chapters).find((c) => c.id === chapter.id).title = e.target.value;
                    })} />
                  </label>
                  <button disabled={busy} onClick={() => {
                    const next = { id: id("chapter"), title: `Chapter ${chapters.length + 1}`, scenes: [newScene("Scene 1")] };
                    edit((p) => p.arcs.find((a) => a.chapters.some((c) => c.id === chapter.id)).chapters.push(next));
                    setChapterId(next.id);
                    setSceneId(next.scenes[0].id);
                  }}>Add chapter</button>
                  <button disabled={busy} onClick={() => {
                    const next = newScene(`Scene ${chapter.scenes.length + 1}`);
                    edit((p) => p.arcs.flatMap((a) => a.chapters).find((c) => c.id === chapter.id).scenes.push(next));
                    setSceneId(next.id);
                  }}>Add scene</button>
                  <label>Scene name
                    <input disabled={busy || scene.locked} value={scene.title} onChange={(e) => editScene((s) => { s.title = e.target.value; })} />
                  </label>
                  <button onClick={exportManuscript}>Export manuscript JSON</button>
                </>
              )}
              <span className="story-badge">
                <AudioLines size={14} />
                {measured}/{spoken.length} takes imported
              </span>
              <span className="story-badge">
                <Clock size={14} />
                {dirty ? "Save to update timing" : secs(timeline?.duration)}
              </span>
              <button
                disabled={busy || !undo.current.length}
                onClick={() => {
                  setDoc(undo.current.pop());
                  setDirty(true);
                }}
              >
                <Undo2 size={16} />
                Undo edit
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    const p = await save();
                    accept(
                      await request(`/projects/${p.id}/duplicate`, {
                        method: "POST",
                        body: JSON.stringify({ revision: p.revision }),
                      }),
                    );
                    await refreshLibrary();
                  })
                }
              >
                <Copy size={16} />
                Duplicate draft
              </button>
            </div>
            <div className="story-workspace">
              <aside className="story-scenes">
                <p className="story-overline">SCENES</p>
                {chapter?.scenes.map((s, i) => (
                  <button
                    key={s.id}
                    className={s.id === scene?.id ? "active" : ""}
                    onClick={() => setSceneId(s.id)}
                  >
                    <span>{String(i + 1).padStart(2, "0")}</span>
                    <div>
                      <strong>{s.title}</strong>
                      <small>
                        {s.segments.length} lines {s.locked ? "· Locked" : ""}
                      </small>
                    </div>
                  </button>
                ))}
              </aside>
              <section className="story-panel">
                <div className="story-section-title">
                  <div>
                    <p className="story-overline">{section.toUpperCase()}</p>
                    <h2>{scene?.title}</h2>
                  </div>
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        const p = clone(await save());
                        const s = allScenes(p).find((s) => s.id === scene.id);
                        s.locked = !s.locked;
                        accept(
                          await request(`/projects/${p.id}`, {
                            method: "PUT",
                            body: JSON.stringify(p),
                          }),
                        );
                      })
                    }
                  >
                    {scene.locked ? <Lock size={15} /> : <Unlock size={15} />}{" "}
                    {scene.locked ? "Unlock scene" : "Lock scene"}
                  </button>
                </div>
                {section === "Manuscript" && (
                  <>
                    <div className="story-editor-columns">
                      <div>
                        <h3>
                          Canonical source{" "}
                          <span className="story-muted">Read only</span>
                        </h3>
                        <pre className="story-source">
                          {scene.canonical_text ||
                            "No canonical text supplied."}
                        </pre>
                        <small>{scene.source_refs.join(" · ")}</small>
                      </div>
                      <div>
                        <h3>Production draft</h3>
                        <fieldset disabled={busy || scene.locked}>
                          {scene.segments.map((l) => (
                            <div className="story-line" key={l.id}>
                              <div>
                                <span>{l.kind}</span>
                                <code>{l.id}</code>
                              </div>
                              {l.kind === "silence" ? (
                                <label>
                                  Silence seconds
                                  <input
                                    aria-label={`Silence ${l.id}`}
                                    type="number"
                                    min="0.01"
                                    step="0.1"
                                    value={l.silence_seconds}
                                    onChange={(e) =>
                                      editLine(
                                        l.id,
                                        "silence_seconds",
                                        Number(e.target.value),
                                      )
                                    }
                                  />
                                </label>
                              ) : (
                                <textarea
                                  aria-label={`Text ${l.id}`}
                                  value={l.text}
                                  onChange={(e) =>
                                    editLine(l.id, "text", e.target.value)
                                  }
                                />
                              )}
                            </div>
                          ))}
                        </fieldset>
                      </div>
                    </div>
                    <button onClick={() => setShowDiff(!showDiff)}>
                      {showDiff ? "Hide" : "Show"} source / draft diff
                    </button>
                    {showDiff && (
                      <div className="story-diff">
                        {lineDiff(scene.canonical_text, draftText).map(
                          (r, i) => (
                            <pre className={r.kind} key={i}>
                              {r.kind === "added"
                                ? "+ "
                                : r.kind === "removed"
                                  ? "− "
                                  : "  "}
                              {r.text}
                            </pre>
                          ),
                        )}
                      </div>
                    )}
                    <details className="story-details">
                      <summary>Adaptation brief & version history</summary>
                      <p className="story-muted">
                        These choices guide your editing. Automatic rewriting is
                        not connected. Duplicate a draft to explore another
                        treatment.
                      </p>
                      <fieldset disabled={busy}>
                        <div className="story-fields">
                          {Object.entries({
                            audience: ["public", "private"],
                            pacing: ["unhurried", "balanced", "brisk"],
                            fidelity: ["close", "condensed"],
                            narration_density: ["low", "balanced", "high"],
                            visual_emphasis: ["low", "balanced", "high"],
                            emotional_intensity: [
                              "restrained",
                              "balanced",
                              "strong",
                            ],
                          }).map(([key, options]) => (
                            <label key={key}>
                              {key.replaceAll("_", " ")}
                              <select
                                value={doc.adaptation[key]}
                                onChange={(e) =>
                                  edit(
                                    (p) => (p.adaptation[key] = e.target.value),
                                  )
                                }
                              >
                                {options.map((o) => (
                                  <option key={o}>{o}</option>
                                ))}
                              </select>
                            </label>
                          ))}
                        </div>
                        <label>
                          Editorial notes
                          <textarea
                            value={doc.adaptation.notes}
                            onChange={(e) =>
                              edit((p) => (p.adaptation.notes = e.target.value))
                            }
                          />
                        </label>
                      </fieldset>
                      <div className="story-actions">
                        <select
                          aria-label="Restore revision"
                          value={restoreTo}
                          onChange={(e) => setRestoreTo(e.target.value)}
                        >
                          <option value="">Choose revision</option>
                          {history.map((r) => (
                            <option key={r} value={r}>
                              Revision {r}
                            </option>
                          ))}
                        </select>
                        <button
                          disabled={busy || restoreTo === "" || dirty}
                          onClick={() =>
                            act(async () =>
                              accept(
                                await request(`/projects/${doc.id}/restore`, {
                                  method: "POST",
                                  body: JSON.stringify({
                                    revision: doc.revision,
                                    restore_revision: Number(restoreTo),
                                  }),
                                }),
                              ),
                            )
                          }
                        >
                          Restore as new revision
                        </button>
                        <small>
                          Save edits first. Locked scenes remain protected.
                        </small>
                      </div>
                    </details>
                  </>
                )}
                {section === "Voices" && (
                  <>
                    <p className="story-muted">
                      Assign a voice label, then import each recorded or
                      generated take. Changing text, voice or delivery flags
                      that take for replacement.
                    </p>
                    <fieldset disabled={busy || scene.locked}>
                      {scene.segments
                        .filter((l) => l.kind !== "silence")
                        .map((l) => (
                          <article className="story-voice" key={l.id}>
                            <div className="story-section-title">
                              <code>{l.id}</code>
                              <span className="story-badge">{l.kind}</span>
                            </div>
                            <p>{l.text}</p>
                            <div className="story-fields">
                              {l.kind === "dialogue" && (
                                <label>
                                  Character
                                  <select
                                    aria-label={`Character ${l.id}`}
                                    value={l.character_id}
                                    onChange={(e) =>
                                      editLine(
                                        l.id,
                                        "character_id",
                                        e.target.value,
                                      )
                                    }
                                  >
                                    {doc.characters.map((c) => (
                                      <option key={c.id} value={c.id}>
                                        {c.name}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                              )}
                              <label>
                                Voice
                                <input
                                  aria-label={`Voice ${l.id}`}
                                  value={l.voice || ""}
                                  placeholder={
                                    doc.characters.find(
                                      (c) => c.id === l.character_id,
                                    )?.voice || "Your chosen voice"
                                  }
                                  onChange={(e) =>
                                    editLine(l.id, "voice", e.target.value)
                                  }
                                />
                              </label>
                              <label>
                                Emotion
                                <input
                                  value={l.emotion}
                                  onChange={(e) =>
                                    editLine(l.id, "emotion", e.target.value)
                                  }
                                />
                              </label>
                              <label>
                                Pause after (seconds)
                                <input
                                  type="number"
                                  min="0"
                                  step="0.1"
                                  value={l.pause_after}
                                  onChange={(e) =>
                                    editLine(
                                      l.id,
                                      "pause_after",
                                      Number(e.target.value),
                                    )
                                  }
                                />
                              </label>
                            </div>
                            <label>
                              Delivery direction
                              <input
                                value={l.direction}
                                onChange={(e) =>
                                  editLine(l.id, "direction", e.target.value)
                                }
                                placeholder="Quiet, trying to sound certain"
                              />
                            </label>
                            <div className="story-actions">
                              <label className="story-button">
                                <Upload size={15} />
                                {l.audio_asset_id
                                  ? "Replace take"
                                  : "Import take"}
                                <input
                                  aria-label={`Audio ${l.id}`}
                                  type="file"
                                  accept=".wav,.mp3,.flac,.ogg,.m4a,.aac"
                                  onChange={(e) => {
                                    upload(e.target.files[0], "audio", l.id);
                                    e.target.value = "";
                                  }}
                                />
                              </label>
                              {l.audio_asset_id && (
                                <>
                                  <audio
                                    controls
                                    src={media(l.audio_asset_id)}
                                  />
                                  <span>
                                    {secs(
                                      assets.find(
                                        (a) => a.id === l.audio_asset_id,
                                      )?.duration,
                                    )}
                                  </span>
                                </>
                              )}
                            </div>
                          </article>
                        ))}
                    </fieldset>
                  </>
                )}
                {section === "Visuals" && (
                  <>
                    <p className="story-muted">
                      One image can carry several lines. Automatic shots share
                      the measured scene duration; manual placements keep your
                      exact seconds.
                    </p>
                    <fieldset disabled={busy || scene.locked}>
                      {scene.shots.map((shot) => (
                        <article className="story-shot" key={shot.id}>
                          {shot.image_asset_id ? (
                            <img
                              src={media(shot.image_asset_id)}
                              alt={shot.title}
                            />
                          ) : (
                            <div className="story-image-placeholder">
                              <ImageIcon />
                              <span>Attach an illustration</span>
                            </div>
                          )}
                          <div>
                            <label>
                              Shot title
                              <input
                                value={shot.title}
                                onChange={(e) =>
                                  editScene(
                                    (s) =>
                                      (s.shots.find(
                                        (v) => v.id === shot.id,
                                      ).title = e.target.value),
                                  )
                                }
                              />
                            </label>
                            <label>
                              Image prompt
                              <textarea
                                aria-label={`Prompt ${shot.id}`}
                                value={shot.prompt}
                                onChange={(e) =>
                                  editScene(
                                    (s) =>
                                      (s.shots.find(
                                        (v) => v.id === shot.id,
                                      ).prompt = e.target.value),
                                  )
                                }
                              />
                            </label>
                            <div className="story-fields">
                              {["timing", "fit", "motion"].map((key) => (
                                <label key={key}>
                                  {key}
                                  <select
                                    aria-label={`${key} ${shot.id}`}
                                    value={shot[key]}
                                    onChange={(e) =>
                                      editScene((s) => {
                                        const v = s.shots.find(
                                          (v) => v.id === shot.id,
                                        );
                                        v[key] = e.target.value;
                                        if (
                                          key === "timing" &&
                                          e.target.value === "manual"
                                        ) {
                                          v.duration = v.duration || 1;
                                          v.start_segment_id = null;
                                          v.end_segment_id = null;
                                        }
                                      })
                                    }
                                  >
                                    {{
                                      timing: ["auto", "manual"],
                                      fit: ["cover", "contain"],
                                      motion: ["still", "slow_zoom"],
                                    }[key].map((o) => (
                                      <option key={o}>{o}</option>
                                    ))}
                                  </select>
                                </label>
                              ))}
                              {shot.timing === "manual" &&
                                ["start", "duration"].map((key) => (
                                  <label key={key}>
                                    {key} (seconds)
                                    <input
                                      aria-label={`${key} ${shot.id}`}
                                      type="number"
                                      min={key === "duration" ? "0.01" : "0"}
                                      step="0.1"
                                      value={shot[key]}
                                      onChange={(e) =>
                                        editScene(
                                          (s) =>
                                            (s.shots.find(
                                              (v) => v.id === shot.id,
                                            )[key] = Number(e.target.value)),
                                        )
                                      }
                                    />
                                  </label>
                                ))}
                              {["fade_in", "fade_out"].map((key) => (
                                <label key={key}>
                                  {key.replace("_", " ")} (seconds)
                                  <input
                                    type="number"
                                    min="0"
                                    step="0.1"
                                    value={shot[key]}
                                    onChange={(e) =>
                                      editScene(
                                        (s) =>
                                          (s.shots.find(
                                            (v) => v.id === shot.id,
                                          )[key] = Number(e.target.value)),
                                      )
                                    }
                                  />
                                </label>
                              ))}
                            </div>
                            <label>
                              Reuse image
                              <select
                                value={shot.image_asset_id || ""}
                                onChange={(e) =>
                                  editScene(
                                    (s) =>
                                      (s.shots.find(
                                        (v) => v.id === shot.id,
                                      ).image_asset_id =
                                        e.target.value || null),
                                  )
                                }
                              >
                                <option value="">Choose uploaded image</option>
                                {assets
                                  .filter((a) => a.kind === "image")
                                  .map((a) => (
                                    <option key={a.id} value={a.id}>
                                      {a.original_name}
                                    </option>
                                  ))}
                              </select>
                            </label>
                            <div className="story-actions">
                              <label className="story-button">
                                <Upload size={15} />
                                Upload image
                                <input
                                  aria-label={`Image ${shot.id}`}
                                  type="file"
                                  accept=".png,.jpg,.jpeg,.webp"
                                  onChange={(e) => {
                                    upload(
                                      e.target.files[0],
                                      "image",
                                      null,
                                      shot.id,
                                    );
                                    e.target.value = "";
                                  }}
                                />
                              </label>
                              <button
                                onClick={() =>
                                  editScene(
                                    (s) =>
                                      (s.shots = s.shots.filter(
                                        (v) => v.id !== shot.id,
                                      )),
                                  )
                                }
                              >
                                Remove shot
                              </button>
                            </div>
                          </div>
                        </article>
                      ))}
                      <button
                        onClick={() =>
                          editScene((s) =>
                            s.shots.push({
                              id: id("shot"),
                              title: `Shot ${s.shots.length + 1}`,
                              prompt: "",
                              image_asset_id: null,
                              timing: "auto",
                              start: 0,
                              duration: null,
                              start_segment_id: null,
                              end_segment_id: null,
                              fit: "cover",
                              motion: "still",
                              fade_in: 0,
                              fade_out: 0,
                            }),
                          )
                        }
                      >
                        <Plus size={16} />
                        Add shot
                      </button>
                    </fieldset>
                  </>
                )}
                {section === "Timeline" && (
                  <>
                    <p className="story-muted">
                      {dirty
                        ? "Unsaved changes: timing below belongs to the last saved revision."
                        : "Chapter timeline from measured takes and explicit pauses. Missing takes leave timing incomplete."}
                    </p>
                    <div className="story-timeline">
                      <div className="story-ruler">
                        {[0, 0.25, 0.5, 0.75, 1].map((x) => (
                          <span key={x}>
                            {secs((timeline?.duration || 0) * x)}
                          </span>
                        ))}
                      </div>
                      {[
                        ["Speech", timeline?.audio, "audio"],
                        ["Visuals", timeline?.visuals, "visual"],
                        ["Sound beds", timeline?.layers, "layer"],
                      ].map(([name, rows, cls]) => (
                        <div key={name} className="story-track">
                          <strong>{name}</strong>
                          <div>
                            {rows?.map((r) => (
                              <div
                                key={r.id}
                                title={`${r.id} · ${secs(r.start)} → ${secs(r.start + r.duration)}`}
                                className={`story-clip ${cls}`}
                                style={{
                                  left: `${(100 * r.start) / (timeline.duration || 1)}%`,
                                  width: `${(100 * r.duration) / (timeline.duration || 1)}%`,
                                }}
                              >
                                {r.title || r.text || r.kind}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                    <h3>Sound beds for this scene</h3>
                    <fieldset disabled={busy || scene.locked}>
                      <label className="story-button">
                        <Upload size={15} />
                        Import music / ambience
                        <input
                          aria-label="Import sound bed"
                          type="file"
                          accept=".wav,.mp3,.flac,.ogg,.m4a,.aac"
                          onChange={(e) => {
                            upload(e.target.files[0], "audio");
                            e.target.value = "";
                          }}
                        />
                      </label>
                      {scene.audio_layers.map((layer) => (
                        <article className="story-voice" key={layer.id}>
                          <div className="story-fields">
                            <label>
                              Kind
                              <select
                                value={layer.kind}
                                onChange={(e) =>
                                  editScene(
                                    (s) =>
                                      (s.audio_layers.find(
                                        (x) => x.id === layer.id,
                                      ).kind = e.target.value),
                                  )
                                }
                              >
                                {["music", "ambience", "sfx"].map((k) => (
                                  <option key={k}>{k}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Audio
                              <select
                                value={layer.audio_asset_id}
                                onChange={(e) =>
                                  editScene(
                                    (s) =>
                                      (s.audio_layers.find(
                                        (x) => x.id === layer.id,
                                      ).audio_asset_id = e.target.value),
                                  )
                                }
                              >
                                {assets
                                  .filter(
                                    (a) =>
                                      a.kind === "audio" &&
                                      !a.speech_fingerprint,
                                  )
                                  .map((a) => (
                                    <option key={a.id} value={a.id}>
                                      {a.original_name}
                                    </option>
                                  ))}
                              </select>
                            </label>
                            {[
                              "start",
                              "duration",
                              "gain",
                              "fade_in",
                              "fade_out",
                            ].map((key) => (
                              <label key={key}>
                                {key.replace("_", " ")}
                                <input
                                  type="number"
                                  min="0"
                                  step="0.1"
                                  value={layer[key]}
                                  onChange={(e) =>
                                    editScene(
                                      (s) =>
                                        (s.audio_layers.find(
                                          (x) => x.id === layer.id,
                                        )[key] = Number(e.target.value)),
                                    )
                                  }
                                />
                              </label>
                            ))}
                            <label>
                              Loop
                              <input
                                type="checkbox"
                                checked={layer.loop}
                                onChange={(e) =>
                                  editScene(
                                    (s) =>
                                      (s.audio_layers.find(
                                        (x) => x.id === layer.id,
                                      ).loop = e.target.checked),
                                  )
                                }
                              />
                            </label>
                          </div>
                          <button
                            onClick={() =>
                              editScene(
                                (s) =>
                                  (s.audio_layers = s.audio_layers.filter(
                                    (x) => x.id !== layer.id,
                                  )),
                              )
                            }
                          >
                            Remove sound bed
                          </button>
                        </article>
                      ))}
                      <button
                        disabled={
                          !assets.some(
                            (a) => a.kind === "audio" && !a.speech_fingerprint,
                          )
                        }
                        onClick={() =>
                          editScene((s) =>
                            s.audio_layers.push({
                              id: id("bed"),
                              kind: "ambience",
                              audio_asset_id: assets.find(
                                (a) =>
                                  a.kind === "audio" && !a.speech_fingerprint,
                              ).id,
                              start: 0,
                              duration:
                                timeline?.scenes.find((x) => x.id === scene.id)
                                  ?.duration || 1,
                              gain: 0.2,
                              loop: true,
                              fade_in: 0,
                              fade_out: 0,
                            }),
                          )
                        }
                      >
                        <Plus size={16} />
                        Add sound bed
                      </button>
                    </fieldset>
                  </>
                )}
                {section === "Export" && (
                  <>
                    <div className="story-export">
                      <Film size={32} />
                      <div>
                        <h3>From words to a finished scene.</h3>
                        <p>
                          Preview this scene, or render the selected chapter.
                          Both use the same measured timeline.
                        </p>
                      </div>
                    </div>
                    <div className="story-actions">
                      <label>
                        Resolution
                        <select
                          aria-label="Resolution"
                          value={resolution}
                          onChange={(e) => setResolution(e.target.value)}
                        >
                          {["640x360", "1280x720", "1920x1080"].map((r) => (
                            <option key={r}>{r}</option>
                          ))}
                        </select>
                      </label>
                      <button disabled={busy} onClick={() => render(scene.id)}>
                        <Play size={15} />
                        Preview scene
                      </button>
                      <button
                        className="story-primary"
                        disabled={busy}
                        onClick={() => render()}
                      >
                        <Film size={15} />
                        Render chapter
                      </button>
                      <button onClick={exportManuscript}>
                        <Download size={15} />
                        Manuscript JSON
                      </button>
                    </div>
                    {job && (
                      <div className="story-job" role="status">
                        <strong>{job.status}</strong> · {job.stage || "Queued"}{" "}
                        {job.progress ? `${Math.round(job.progress)}%` : ""}
                        {job.error && (
                          <p className="story-error">{job.error}</p>
                        )}
                      </div>
                    )}
                    {done && (
                      <div className="story-render">
                        <video
                          controls
                          key={done.job_id}
                          src={renderUrl(done, "episode.mp4")}
                        />
                        <div className="story-actions">
                          <span>
                            Rendered revision{" "}
                            {done.metadata?.revision ??
                              done.result?.data?.revision}
                          </span>
                          <a
                            className="story-button"
                            href={
                              renderUrl(done, "episode.mp4") + "?download=true"
                            }
                          >
                            Download MP4
                          </a>
                          <a
                            className="story-button"
                            href={
                              renderUrl(done, "manifest.json") +
                              "?download=true"
                            }
                          >
                            Production manifest
                          </a>
                        </div>
                      </div>
                    )}
                    {jobs.length > 0 && (
                      <details className="story-details">
                        <summary>Earlier renders</summary>
                        {jobs.map((j) => (
                          <div className="story-actions" key={j.job_id}>
                            <span>
                              Revision {j.metadata.revision} ·{" "}
                              {j.metadata.scene_id || "Chapter"} · {j.status}
                            </span>
                            {j.status === "done" && (
                              <button onClick={() => setJob(j)}>
                                View render
                              </button>
                            )}
                          </div>
                        ))}
                      </details>
                    )}
                    <p className="story-muted">
                      Exports stay local. To publish, review the finished MP4
                      and use your existing publishing workflow. This editor
                      does not upload to YouTube.
                    </p>
                  </>
                )}
                {timeline && (
                  <details
                    className={`story-readiness ${timeline.ready ? "ready" : ""}`}
                    open={!timeline.ready && section === "Export"}
                  >
                    <summary>
                      {timeline.ready ? (
                        <CheckCircle2 size={15} />
                      ) : (
                        <Clock size={15} />
                      )}{" "}
                      {dirty
                        ? "Save to refresh readiness"
                        : timeline.ready
                          ? "Chapter ready to render"
                          : `${timeline.conflicts.length} production items to resolve`}
                    </summary>
                    <ul>
                      {timeline.conflicts.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </section>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
