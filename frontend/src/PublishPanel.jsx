import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Youtube,
  Settings2,
  Upload,
  RefreshCw,
  Download,
  ExternalLink,
  X,
} from "lucide-react";
import { PublishingClient, readLaunchToken } from "./publishingApi";
import { ChannelProfilesPanel } from "./ChannelProfilesPanel";
import { mergeConfig } from "./config";

function ReviewForm({ run, client, onRefresh, act, busy }) {
  const [draft, setDraft] = useState({
    ...run.review,
    metadata: run.metadata,
    revision: run.revision,
    confirm_public: false,
  });
  const [tags, setTags] = useState(run.metadata.tags.join(", "));
  const [confirmed, setConfirmed] = useState(false);
  const meta = (key, value) =>
    setDraft((d) => ({ ...d, metadata: { ...d.metadata, [key]: value } }));
  const body = () => ({
    ...draft,
    metadata: {
      ...draft.metadata,
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    },
  });
  return (
    <div className="publish-review">
      <h3>Review for {run.profile.channel_name}</h3>
      <p className="quiet">
        {run.source_name} | {run.profile.channel_id}
      </p>
      <video
        controls
        playsInline
        preload="metadata"
        src={client.fileUrl(run.id)}
        aria-label="Publishing video review"
      />
      {run.metadata_error && (
        <p className="error" role="alert">
          {run.metadata_error}
        </p>
      )}
      <label>
        Video title
        <input
          maxLength={100}
          value={draft.metadata.title}
          onChange={(e) => meta("title", e.target.value)}
        />
      </label>
      <label>
        Description
        <textarea
          value={draft.metadata.description}
          onChange={(e) => meta("description", e.target.value)}
        />
      </label>
      <label>
        Video tags
        <input value={tags} onChange={(e) => setTags(e.target.value)} />
      </label>
      <div className="grid2">
        <label>
          Upload privacy
          <select
            value={draft.privacy}
            onChange={(e) =>
              setDraft((d) => ({
                ...d,
                privacy: e.target.value,
                confirm_public: false,
              }))
            }
          >
            <option value="private">Private</option>
            <option value="unlisted">Unlisted</option>
            <option value="public">Public</option>
          </select>
        </label>
        <label>
          Upload category ID
          <input
            value={draft.category}
            onChange={(e) =>
              setDraft((d) => ({ ...d, category: e.target.value }))
            }
          />
        </label>
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={draft.made_for_kids}
          onChange={(e) =>
            setDraft((d) => ({ ...d, made_for_kids: e.target.checked }))
          }
        />
        Made for kids
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={draft.contains_synthetic_media}
          onChange={(e) =>
            setDraft((d) => ({
              ...d,
              contains_synthetic_media: e.target.checked,
            }))
          }
        />
        Altered or synthetic content
      </label>
      {draft.privacy === "public" && (
        <label className="check">
          <input
            type="checkbox"
            checked={draft.confirm_public}
            onChange={(e) =>
              setDraft((d) => ({ ...d, confirm_public: e.target.checked }))
            }
          />
          I confirm this upload should be Public
        </label>
      )}
      <label className="check">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        I reviewed this video, metadata, channel and disclosure settings
      </label>
      <div className="footer-actions">
        <button
          className="primary"
          disabled={
            busy ||
            !confirmed ||
            (draft.privacy === "public" && !draft.confirm_public)
          }
          onClick={() =>
            act(async () => {
              await client.call(`/runs/${run.id}/upload`, "POST", body());
              await onRefresh();
            })
          }
        >
          <Upload size={16} />
          Approve &amp; upload
        </button>
        <button
          disabled={busy}
          onClick={() =>
            act(async () => {
              await client.call(`/runs/${run.id}/metadata`, "PATCH", body());
              await onRefresh();
            })
          }
        >
          Save draft
        </button>
        <button
          disabled={busy}
          onClick={() =>
            act(async () => {
              await client.call(`/runs/${run.id}/regenerate-metadata`, "POST");
              await onRefresh();
            })
          }
        >
          <RefreshCw size={16} />
          Regenerate metadata
        </button>
        <a className="download-link" href={client.fileUrl(run.id, true)}>
          <Download size={16} />
          Download
        </a>
      </div>
    </div>
  );
}

export function PublishPanel({
  apiBase = "",
  apiToken = "",
  source,
  config,
  onConfig,
}) {
  const client = useMemo(
    () =>
      new PublishingClient(
        apiBase,
        apiToken || (!apiBase ? readLaunchToken() : ""),
      ),
    [apiBase, apiToken],
  );
  const [status, setStatus] = useState("checking");
  const [profiles, setProfiles] = useState([]),
    [providers, setProviders] = useState([]),
    [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState("");
  const [openRun, setOpenRun] = useState("");
  const [manage, setManage] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [context, setContext] = useState(""),
    [transcript, setTranscript] = useState("");
  const requestKey = useRef(null);
  const autoSelected = useRef(false);
  useEffect(() => {
    setContext("");
    setTranscript("");
    requestKey.current = null;
  }, [source?.audio_ref?.path]);
  const refresh = useCallback(async () => {
    const p = await client.call("/profiles");
    setProfiles(p);
    setProviders(await client.call("/providers"));
    setRuns(await client.call("/runs"));
    return p;
  }, [client]);
  useEffect(() => {
    let active = true,
      polling = false,
      authorized = false;
    autoSelected.current = false;
    setSelected("");
    setRuns([]);
    setProfiles([]);
    setStatus("checking");
    async function init() {
      try {
        await client.call("/info");
        await client.unlock();
        if (!active) return;
        await refresh();
        if (active) {
          authorized = true;
          setStatus("ready");
        }
      } catch (e) {
        if (active) {
          setStatus(e.status === 404 ? "disabled" : "locked");
          if (e.status !== 404) setError(e.message);
        }
      }
    }
    init();
    const timer = setInterval(async () => {
      if (polling || !active || !authorized) return;
      polling = true;
      try {
        const p = await client.call("/profiles");
        const r = await client.call("/runs");
        if (active) {
          setProfiles(p);
          setRuns(r);
        }
      } catch (e) {
        if (active && e.status === 401) {
          authorized = false;
          setStatus("locked");
          setError(e.message);
        }
      } finally {
        polling = false;
      }
    }, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [client, refresh]);
  const select = useCallback(
    (profile) => {
      setSelected(profile.id);
      requestKey.current = null;
      onConfig((current) => ({
        ...mergeConfig(profile.preset),
        output_name: current.output_name,
      }));
    },
    [onConfig],
  );
  useEffect(() => {
    if (!autoSelected.current && profiles.length) {
      autoSelected.current = true;
      let saved = "";
      try {
        saved = localStorage.getItem("audio-studio-profile:" + apiBase) || "";
      } catch {}
      select(profiles.find((p) => p.id === saved) || profiles[0]);
    }
  }, [profiles, select, apiBase]);
  const chosen = profiles.find((p) => p.id === selected);
  const activeRun = runs.find((r) => r.id === openRun);
  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function prepare() {
    const data = {
      profile_id: selected,
      audio_ref: source.audio_ref,
      source_name: source.name,
      context,
      transcript,
      config,
    };
    const fingerprint = JSON.stringify(data);
    if (requestKey.current?.fingerprint !== fingerprint)
      requestKey.current = { fingerprint, key: crypto.randomUUID() };
    const run = await client.call("/runs", "POST", data, {
      "Idempotency-Key": requestKey.current.key,
    });
    setOpenRun(run.id);
    await refresh();
  }
  return (
    <section className="publishing" aria-label="YouTube publishing">
      <div className="row">
        <h2>
          <Youtube size={20} />
          YouTube publishing
        </h2>
        <button
          className="icon"
          title="Channel profiles and setup"
          disabled={status !== "ready"}
          onClick={() => setManage(true)}
        >
          <Settings2 size={18} />
        </button>
      </div>
      {status === "disabled" && (
        <p className="quiet">
          Publishing is disabled. Start with Launch Studio.cmd.
        </p>
      )}
      {status === "checking" && (
        <p className="quiet">Connecting publishing...</p>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {status === "ready" && (
        <>
          <div className="publish-start">
            <label>
              Channel profile
              <select
                aria-label="Channel profile"
                value={selected}
                onChange={(e) => {
                  const p = profiles.find((p) => p.id === e.target.value);
                  if (p) {
                    select(p);
                    try {
                      localStorage.setItem(
                        "audio-studio-profile:" + apiBase,
                        p.id,
                      );
                    } catch {}
                  }
                }}
              >
                <option value="">Select profile</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.connected ? "" : "(disconnected)"}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary"
              disabled={busy || !source || !chosen?.connected}
              onClick={() => act(prepare)}
            >
              <Youtube size={17} />
              Prepare for YouTube
            </button>
          </div>
          {chosen && (
            <p className="quiet">
              {chosen.channel_name || "Channel not connected"} |{" "}
              {chosen.privacy} | {chosen.channel_id || ""}
            </p>
          )}
          {!profiles.length && (
            <button onClick={() => setManage(true)}>
              <Settings2 size={16} />
              Set up first channel
            </button>
          )}
          <details>
            <summary>Recording context / transcript</summary>
            <label>
              Recording context
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                placeholder="Recording title, performer, song credits, or other known facts"
              />
            </label>
            <label>
              Transcript (optional)
              <textarea
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
              />
            </label>
          </details>
          {!!runs.length && (
            <details open>
              <summary>Publishing jobs ({runs.length})</summary>
              <div className="publishing-runs">
                {runs.map((run) => (
                  <div className="publish-job" key={run.id}>
                    <button
                      className={openRun === run.id ? "selected-run" : ""}
                      onClick={() =>
                        setOpenRun(openRun === run.id ? "" : run.id)
                      }
                    >
                      <strong>{run.source_name}</strong>
                      <span>
                        {run.profile.name} / {run.profile.channel_name}
                      </span>
                      <span>
                        {run.stage}{" "}
                        {run.state === "rendering" || run.state === "uploading"
                          ? `${Math.round(run.progress)}%`
                          : ""}
                      </span>
                      <span>
                        {new Date(run.created_at * 1000).toLocaleString()}
                      </span>
                    </button>
                    {["rendering", "uploading"].includes(run.state) && (
                      <progress max="100" value={run.progress} />
                    )}
                    {run.video_url && (
                      <a href={run.video_url} target="_blank" rel="noreferrer">
                        <ExternalLink size={14} />
                        {run.video_id} (
                        {run.actual_privacy || run.review?.privacy})
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </details>
          )}
          {activeRun && (
            <>
              {activeRun.error && (
                <div className="error" role="alert">
                  {activeRun.error}
                </div>
              )}
              {activeRun.upload_total > 0 && (
                <p className="quiet">
                  {(activeRun.upload_bytes / 1048576).toFixed(1)} /{" "}
                  {(activeRun.upload_total / 1048576).toFixed(1)} MB confirmed
                </p>
              )}
              {activeRun.state === "awaiting_review" && (
                <ReviewForm
                  key={activeRun.id + ":" + activeRun.revision}
                  run={activeRun}
                  client={client}
                  onRefresh={refresh}
                  act={act}
                  busy={busy}
                />
              )}
              {["failed", "needs_reauth", "retry_wait"].includes(
                activeRun.state,
              ) && (
                <button
                  disabled={busy}
                  onClick={() =>
                    act(async () => {
                      await client.call(
                        `/runs/${activeRun.id}/retry`,
                        "POST",
                        {},
                      );
                      await refresh();
                    })
                  }
                >
                  <RefreshCw size={16} />
                  Retry failed stage
                </button>
              )}
              {["failed", "needs_reauth"].includes(activeRun.state) &&
                activeRun.artifact &&
                !activeRun.session_created &&
                !activeRun.video_id && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        await client.call(
                          `/runs/${activeRun.id}/reopen-review`,
                          "POST",
                        );
                        await refresh();
                      })
                    }
                  >
                    Edit review
                  </button>
                )}
              {activeRun.state === "needs_attention" && activeRun.video_id && (
                <button
                  disabled={busy}
                  onClick={() =>
                    act(async () => {
                      await client.call(
                        `/runs/${activeRun.id}/retry`,
                        "POST",
                        {},
                      );
                      await refresh();
                    })
                  }
                >
                  <RefreshCw size={16} />
                  Recheck YouTube processing
                </button>
              )}
              {activeRun.state === "needs_attention" && !activeRun.video_id && (
                <button
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        "Have you checked YouTube Studio and confirmed this video was NOT uploaded? This starts a new upload and could create a duplicate if it already exists.",
                      )
                    )
                      act(async () => {
                        await client.call(
                          `/runs/${activeRun.id}/retry`,
                          "POST",
                          { confirm_restart: true },
                        );
                        await refresh();
                      });
                  }}
                >
                  Restart upload after checking YouTube
                </button>
              )}
              {[
                "awaiting_review",
                "failed",
                "needs_reauth",
                "needs_attention",
              ].includes(activeRun.state) && (
                <button
                  disabled={busy}
                  onClick={() =>
                    act(async () => {
                      await client.call(`/runs/${activeRun.id}/cancel`, "POST");
                      await refresh();
                    })
                  }
                >
                  <X size={16} />
                  Cancel run
                </button>
              )}
              {activeRun.artifact && activeRun.state !== "awaiting_review" && (
                <a
                  className="download-link"
                  href={client.fileUrl(activeRun.id, true)}
                >
                  <Download size={16} />
                  Download rendered video
                </a>
              )}
              <p className="quiet job-id">{activeRun.id}</p>
            </>
          )}
        </>
      )}
      {manage && (
        <ChannelProfilesPanel
          client={client}
          profiles={profiles}
          providers={providers}
          config={config}
          selectedId={selected}
          onRefresh={refresh}
          onSelect={select}
          onClose={() => setManage(false)}
        />
      )}
    </section>
  );
}
