import { Download, Play, RefreshCw, Search } from "lucide-react";
import { useState } from "react";

function localDate(value) {
  if (!value) return "";
  const date = new Date(/[Z+]|-\d\d:\d\d$/.test(value) ? value : value + "Z");
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
export function JobList({ jobs, client, onView, onRefresh, onInspect }) {
  const [query, setQuery] = useState("");
  const [id, setId] = useState("");
  const visible = jobs.filter((job) =>
    JSON.stringify([job.metadata, job.job_id, job.result])
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <section className="job-section">
      <div className="job-header">
        <h2>Render jobs</h2>
        <button className="icon" title="Refresh jobs" onClick={onRefresh}>
          <RefreshCw size={16} />
        </button>
      </div>
      <label className="search">
        <Search size={16} />
        <input
          aria-label="Filter jobs"
          placeholder="Filter by filename or job ID"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      <div aria-live="polite">
        {visible.length ? (
          visible.map((job) => {
            const m = job.metadata || {};
            const output =
              m.output_name ||
              job.result?.data?.path?.split("/").pop() ||
              "Untitled render";
            return (
              <article className="job" key={job.job_id}>
                <div className="job-title">
                  <strong>{m.source_name || output}</strong>
                  <div className="quiet">
                    {m.kind === "preview"
                      ? "5-second preview"
                      : m.kind === "video"
                        ? "Full video"
                        : "Earlier render"}
                    {m.width
                      ? ` | ${m.width} x ${m.height} | ${m.fps} fps`
                      : ""}
                    {m.layouts?.length ? ` | ${m.layouts.join(", ")}` : ""}
                  </div>
                  <div className="quiet">
                    {output} | {localDate(job.created_at)}
                  </div>
                  <details>
                    <summary>Job ID</summary>
                    <code>{job.job_id}</code>
                  </details>
                </div>
                <div>
                  <span className="badge">
                    {job.status === "done"
                      ? "Complete"
                      : job.stage || job.status}{" "}
                    | {Math.round(job.progress || 0)}%
                  </span>
                  <progress value={job.progress || 0} max="100" />
                </div>
                <div className="job-actions">
                  {job.status === "done" && (
                    <>
                      <button onClick={() => onView(job)}>
                        <Play size={14} />
                        View
                      </button>
                      <a
                        className="icon"
                        href={client.fileUrl(job.job_id, true)}
                        title={`Download ${output}`}
                      >
                        <Download size={17} />
                      </a>
                    </>
                  )}
                </div>
                {job.error && <div className="job-error">{job.error}</div>}
              </article>
            );
          })
        ) : (
          <p className="quiet empty-jobs">No matching renders</p>
        )}
      </div>
      <div className="inspect">
        <input
          placeholder="Job ID"
          aria-label="Job ID"
          value={id}
          onChange={(e) => setId(e.target.value)}
        />
        <button onClick={() => onInspect(id)}>Check status</button>
      </div>
    </section>
  );
}
