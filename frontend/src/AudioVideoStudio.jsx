"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AudioLines, Image, Video, Film, Plug, Download } from "lucide-react";
import { AudioVideoClient } from "./api";
import { defaultConfig, exportRequest, mergeConfig } from "./config";
import { SettingsPanel } from "./SettingsPanel";
import { JobList } from "./JobList";
import { useLiveFrame } from "./useLiveFrame";

export function AudioVideoStudio({
  apiBase = "",
  initialConfig,
  onRenderStarted,
  onRenderCompleted,
}) {
  const [base, setBase] = useState(apiBase);
  const [draftBase, setDraftBase] = useState(apiBase);
  const client = useMemo(() => new AudioVideoClient(base), [base]);
  const [config, setConfig] = useState(() =>
    initialConfig ? mergeConfig(initialConfig) : defaultConfig(),
  );
  const [source, setSource] = useState(null);
  const [audioUrl, setAudioUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [connection, setConnection] = useState("Connecting");
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState("editor");
  const [seconds, setSeconds] = useState(2);
  const [playingJob, setPlayingJob] = useState(null);
  const videoRef = useRef(null);
  const sourceController = useRef(null);
  const completed = useRef(new Set());
  const callbacks = useRef({ onRenderStarted, onRenderCompleted });
  callbacks.current = { onRenderStarted, onRenderCompleted };
  const live = useLiveFrame(
    client,
    config,
    source,
    seconds,
    view === "editor" && !uploading,
  );
  const rc = config.render_config;
  const current = jobs.find((job) => job.job_id === selected);
  useEffect(() => {
    setBase(apiBase);
    setDraftBase(apiBase);
  }, [apiBase]);
  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    },
    [audioUrl],
  );
  useEffect(() => () => sourceController.current?.abort(), []);
  useEffect(() => {
    if (view === "editor") videoRef.current?.pause();
  }, [view]);

  const refresh = useCallback(async () => {
    try {
      setJobs(await client.jobs());
    } catch (e) {
      setError("Job status: " + e.message);
    }
  }, [client]);
  useEffect(() => {
    let active = true,
      polling = false;
    setConnection("Connecting");
    client
      .capabilities()
      .then((cap) => {
        if (!active) return;
        setConnection(cap.nvenc ? "NVIDIA ready" : "CPU ready");
        if (!cap.nvenc)
          setConfig((c) => ({
            ...c,
            render_config: { ...c.render_config, vcodec: "libx264" },
          }));
      })
      .catch((e) => {
        if (active) {
          setConnection("Offline");
          setError(e.message);
        }
      });
    const poll = async () => {
      if (polling) return;
      polling = true;
      try {
        const result = await client.jobs();
        if (active) setJobs(result);
      } catch (e) {
        if (active) setConnection("Disconnected");
      } finally {
        polling = false;
      }
    };
    poll();
    const timer = setInterval(poll, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [client]);
  useEffect(() => {
    if (current?.status !== "done" || completed.current.has(current.job_id))
      return;
    completed.current.add(current.job_id);
    setPlayingJob(current);
    setView("video");
    callbacks.current.onRenderCompleted?.(current);
  }, [current]);

  async function chooseAudio(file) {
    sourceController.current?.abort();
    const controller = new AbortController();
    sourceController.current = controller;
    setSource(null);
    setAudioUrl(URL.createObjectURL(file));
    setUploading(true);
    setError("");
    try {
      const result = await client.uploadSource(file, controller.signal);
      if (controller.signal.aborted) return;
      setSource(result);
      setSeconds(Math.min(2, Math.max(0, result.duration - 1 / rc.fps)));
      setView("editor");
      setConfig((c) => ({
        ...c,
        output_name: file.name.replace(/\.[^.]+$/, "") + "_visualizer.mp4",
      }));
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      if (!controller.signal.aborted) setUploading(false);
    }
  }
  async function chooseClips(files) {
    setUploading(true);
    setError("");
    try {
      const refs = [];
      for (const file of files) refs.push(await client.background(file));
      setConfig((c) => ({
        ...c,
        background: {
          ...c.background,
          media_refs: [...c.background.media_refs, ...refs],
        },
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }
  async function render(preview) {
    if (!source) {
      setError("Choose an audio file first.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const job = await client.render(exportRequest(config, source, preview));
      setSelected(job.job_id);
      callbacks.current.onRenderStarted?.(job);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }
  async function inspect(id) {
    if (!id.trim()) return;
    try {
      const job = await client.status(id.trim());
      if (job.status === "not_found") throw new Error("Job not found");
      setJobs((list) => [job, ...list.filter((j) => j.job_id !== job.job_id)]);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }
  function connect() {
    if (base === draftBase.trim()) {
      refresh();
      return;
    }
    sourceController.current?.abort();
    setSource(null);
    setAudioUrl("");
    setPlayingJob(null);
    setSelected(null);
    setUploading(false);
    setJobs([]);
    setBase(draftBase.trim());
  }

  return (
    <div className="audio-studio">
      <header>
        <div className="brand">
          <AudioLines size={30} />
          <div>
            <h1>Audio Studio</h1>
            <div className="subtitle">MangaNarrator</div>
          </div>
        </div>
        <div className="connection">
          <span>
            <i className={connection.includes("ready") ? "dot" : "dot off"} />
            {connection}
          </span>
          <input
            className="api"
            aria-label="Backend URL"
            placeholder="Same-origin backend"
            value={draftBase}
            onChange={(e) => setDraftBase(e.target.value)}
          />
          <button className="icon" title="Connect backend" onClick={connect}>
            <Plug size={17} />
          </button>
        </div>
      </header>
      <div className="layout">
        <SettingsPanel
          config={config}
          onChange={setConfig}
          onAudio={chooseAudio}
          onClips={chooseClips}
          uploading={uploading}
          source={source}
          onError={setError}
        />
        <main className="workspace">
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <div className="toolbar">
            <div className="tabs" role="tablist" aria-label="Preview mode">
              <button
                role="tab"
                aria-selected={view === "editor"}
                className={view === "editor" ? "active" : ""}
                onClick={() => setView("editor")}
              >
                <Image size={16} />
                Live editor
              </button>
              <button
                role="tab"
                aria-selected={view === "video"}
                className={view === "video" ? "active" : ""}
                onClick={() => setView("video")}
              >
                <Video size={16} />
                Rendered video
              </button>
            </div>
            <div className="actions">
              <button
                onClick={() => render(true)}
                disabled={uploading || submitting || !source}
              >
                <Film size={16} />
                Preview 5 seconds
              </button>
              <button
                className="primary"
                onClick={() => render(false)}
                disabled={uploading || submitting || !source}
              >
                <Video size={16} />
                Render video
              </button>
            </div>
          </div>
          <section hidden={view !== "editor"} aria-label="Live frame editor">
            <div className="frame-info">
              <span>
                {rc.viewport_w} x {rc.viewport_h} | {rc.fps} fps
              </span>
              <span role="status">
                {uploading
                  ? "Preparing audio"
                  : live.loading
                    ? "Updating frame"
                    : live.error
                      ? "Frame unavailable"
                      : source
                        ? "Audio frame"
                        : "Demo audio frame"}
              </span>
            </div>
            <div className="stage-wrap">
              <div
                className="stage"
                style={{ aspectRatio: rc.viewport_w / rc.viewport_h }}
                aria-busy={live.loading}
              >
                {live.frame && (
                  <img
                    src={live.frame.url}
                    alt="Live composition frame"
                    data-testid="live-frame"
                  />
                )}
                {!live.frame && (
                  <span className="empty-label">
                    {live.loading ? "Preparing frame..." : "No frame available"}
                  </span>
                )}
              </div>
            </div>
            {live.error && (
              <div className="error" role="alert">
                {live.error}
              </div>
            )}
            <div className="timeline">
              <label>
                Frame time
                <input
                  aria-label="Frame time"
                  type="range"
                  min="0"
                  max={Math.min(
                    7200,
                    Math.max(0, (source?.duration || 5) - 1 / rc.fps),
                  )}
                  step={1 / rc.fps}
                  value={seconds}
                  onChange={(e) => setSeconds(Number(e.target.value))}
                />
              </label>
              <input
                aria-label="Frame time seconds"
                type="number"
                min="0"
                max={Math.min(7200, source?.duration || 5)}
                step=".1"
                value={Number(seconds.toFixed(3))}
                onChange={(e) =>
                  setSeconds(
                    Math.max(
                      0,
                      Math.min(
                        7200,
                        source?.duration || 5,
                        Number(e.target.value),
                      ),
                    ),
                  )
                }
              />
              <span className="quiet">
                {(live.frame?.timestamp || 0).toFixed(3)} s
              </span>
            </div>
          </section>
          <section
            hidden={view !== "video"}
            aria-label="Rendered video preview"
          >
            <div className="frame-info">
              <span>
                {playingJob?.metadata?.source_name || "Rendered video"}
              </span>
              <span>{playingJob?.metadata?.output_name || ""}</span>
            </div>
            <div className="stage-wrap">
              <div
                className="stage"
                style={{
                  aspectRatio: playingJob?.metadata?.width
                    ? playingJob.metadata.width / playingJob.metadata.height
                    : 16 / 9,
                }}
              >
                {playingJob ? (
                  <video
                    ref={videoRef}
                    src={client.fileUrl(playingJob.job_id)}
                    controls
                    playsInline
                  />
                ) : (
                  <span className="empty-label">
                    No rendered video selected
                  </span>
                )}
              </div>
            </div>
            {playingJob && (
              <a
                className="download-link"
                href={client.fileUrl(playingJob.job_id, true)}
              >
                <Download size={16} />
                Download video
              </a>
            )}
          </section>
          {audioUrl && (
            <div className="audio-line">
              <span className="filename">
                {source?.name || "Preparing audio..."}
              </span>
              <audio src={audioUrl} controls />
            </div>
          )}
          {current?.status === "processing" && (
            <div className="active-render">
              <span>
                {current.metadata?.source_name} | {current.stage} |{" "}
                {Math.round(current.progress)}%
              </span>
              <progress max="100" value={current.progress} />
            </div>
          )}
        </main>
        <div className="history">
          <JobList
            jobs={jobs}
            client={client}
            onView={(job) => {
              setPlayingJob(job);
              setView("video");
            }}
            onRefresh={refresh}
            onInspect={inspect}
          />
        </div>
      </div>
    </div>
  );
}
