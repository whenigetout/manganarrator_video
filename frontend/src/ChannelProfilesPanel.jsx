import { useEffect, useRef, useState } from "react";
import { Save, Plus, X, Link, Unplug, Trash2 } from "lucide-react";

const empty = {
  name: "",
  provider_id: "",
  prompt:
    "Write accurate, engaging metadata for my recording. Do not invent credits, lyrics or claims.",
  category: "10",
  tags: [],
  privacy: "private",
  language: "en",
  made_for_kids: false,
  contains_synthetic_media: false,
};
const providerDefault = {
  name: "DeepSeek",
  base_url: "https://api.deepseek.com",
  model: "",
  json_mode: "json_object",
  timeout: 90,
};

export function ChannelProfilesPanel({
  client,
  profiles,
  providers,
  config,
  selectedId,
  onRefresh,
  onSelect,
  onClose,
}) {
  const dialog = useRef(null);
  const [editing, setEditing] = useState(selectedId || "");
  const [draft, setDraft] = useState(empty);
  const [tags, setTags] = useState("");
  const [providerId, setProviderId] = useState("");
  const [provider, setProvider] = useState(providerDefault);
  const [apiKey, setApiKey] = useState("");
  const [setup, setSetup] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [authorizationUrl, setAuthorizationUrl] = useState("");
  const selectedProfile = profiles.find((p) => p.id === editing);
  const profileExists = Boolean(selectedProfile);
  const connectionStatus =
    selectedProfile?.connection_status ||
    (selectedProfile?.connected ? "connected" : "disconnected");
  useEffect(() => {
    dialog.current.showModal();
    client
      .call("/configuration")
      .then(setSetup)
      .catch((e) => setError(e.message));
  }, [client]);
  useEffect(() => {
    const found = profiles.find((p) => p.id === editing);
    setAuthorizationUrl("");
    if (editing && !found) return;
    setDraft(
      found
        ? Object.fromEntries(Object.keys(empty).map((k) => [k, found[k]]))
        : { ...empty },
    );
    setTags(found?.tags.join(", ") || "");
  }, [editing, profileExists]);
  useEffect(() => {
    const refresh = () => onRefresh().catch((e) => setError(e.message));
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [onRefresh]);
  async function act(fn) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
      await onRefresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function save(useCurrent = false) {
    const old = profiles.find((p) => p.id === editing);
    const body = {
      ...draft,
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      preset: useCurrent || !old ? config : old.preset,
    };
    const result = await client.call(
      "/profiles" + (editing ? "/" + editing : ""),
      editing ? "PATCH" : "POST",
      body,
    );
    setEditing(result.id);
    onSelect(result);
    setMessage("Profile saved");
  }
  const set = (key, value) => setDraft((d) => ({ ...d, [key]: value }));
  function connectChannel() {
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;
    act(async () => {
      try {
        const result = await client.call(
          `/profiles/${editing}/connect`,
          "POST",
        );
        if (popup) popup.location.href = result.url;
        else setAuthorizationUrl(result.url);
        setMessage("Complete Google authorization, then return to the studio");
      } catch (e) {
        popup?.close();
        throw e;
      }
    });
  }
  return (
    <dialog className="publishing-dialog" ref={dialog} onCancel={onClose}>
      <div className="row">
        <h2>Channel profiles</h2>
        <button className="icon" title="Close profiles" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <p role="status" className="success">
          {message}
        </p>
      )}
      <div className="row">
        <label className="grow">
          Profile
          <select
            aria-label="Edit channel profile"
            value={editing}
            onChange={(e) => setEditing(e.target.value)}
          >
            <option value="">New profile</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.channel_name ? `(${p.channel_name})` : ""}
              </option>
            ))}
          </select>
        </label>
        <button
          className="icon"
          title="New profile"
          onClick={() => setEditing("")}
        >
          <Plus size={16} />
        </button>
      </div>
      {selectedProfile && (
        <section className="section" aria-label="YouTube channel connection">
          <h3>YouTube channel</h3>
          <p role="status">
            Connection status:{" "}
            {connectionStatus === "connected"
              ? "Connected"
              : connectionStatus === "needs_reauth"
                ? "Reconnect required"
                : "Disconnected"}
          </p>
          <p>
            Channel title: {selectedProfile.channel_name || "Not connected"}
          </p>
          <p>
            Channel handle: {selectedProfile.channel_handle || "Not available"}
          </p>
          <p className="job-id">
            Channel ID: {selectedProfile.channel_id || "Not connected"}
          </p>
          <div className="footer-actions">
            <button
              disabled={busy || !setup?.google_configured}
              onClick={connectChannel}
            >
              <Link size={16} />
              {selectedProfile.channel_id
                ? "Reconnect YouTube channel"
                : "Connect YouTube channel"}
            </button>
            <button
              disabled={busy || connectionStatus === "disconnected"}
              onClick={() =>
                act(() =>
                  client.call(`/profiles/${editing}/disconnect`, "POST"),
                )
              }
            >
              <Unplug size={16} />
              Disconnect
            </button>
          </div>
        </section>
      )}
      <div className="grid2">
        <label>
          Profile name
          <input
            value={draft.name}
            onChange={(e) => set("name", e.target.value)}
          />
        </label>
        <label>
          Metadata provider
          <select
            value={draft.provider_id}
            onChange={(e) => set("provider_id", e.target.value)}
          >
            <option value="">Manual metadata</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} / {p.model}
              </option>
            ))}
          </select>
        </label>
        <label>
          Default privacy
          <select
            value={draft.privacy}
            onChange={(e) => set("privacy", e.target.value)}
          >
            <option value="private">Private</option>
            <option value="unlisted">Unlisted</option>
          </select>
        </label>
        <label>
          Category ID
          <input
            type="number"
            min="1"
            max="999"
            value={draft.category}
            onChange={(e) => set("category", e.target.value)}
          />
        </label>
        <label>
          Language
          <input
            value={draft.language}
            onChange={(e) => set("language", e.target.value)}
          />
        </label>
        <label>
          Default tags
          <input value={tags} onChange={(e) => setTags(e.target.value)} />
        </label>
      </div>
      <label>
        Metadata style / prompt
        <textarea
          value={draft.prompt}
          onChange={(e) => set("prompt", e.target.value)}
        />
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={draft.made_for_kids}
          onChange={(e) => set("made_for_kids", e.target.checked)}
        />
        Made for kids by default
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={draft.contains_synthetic_media}
          onChange={(e) => set("contains_synthetic_media", e.target.checked)}
        />
        Altered or synthetic content by default
      </label>
      <div className="footer-actions">
        <button
          disabled={busy || !draft.name.trim()}
          onClick={() => act(() => save())}
        >
          <Save size={16} />
          Save profile
        </button>
        <button
          disabled={busy || !draft.name.trim()}
          onClick={() => act(() => save(true))}
        >
          <Save size={16} />
          Save current visual settings
        </button>
        {editing && (
          <button
            className="icon"
            title="Delete profile"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm("Delete this profile and its saved connection?")
              )
                act(async () => {
                  await client.call(`/profiles/${editing}`, "DELETE");
                  setEditing("");
                });
            }}
          >
            <Trash2 size={16} />
          </button>
        )}
      </div>
      {authorizationUrl && (
        <a href={authorizationUrl} target="_blank" rel="noreferrer">
          Continue to Google authorization
        </a>
      )}
      <details open={!setup?.google_configured}>
        <summary>
          Google OAuth setup {setup?.google_configured ? "(configured)" : ""}
        </summary>
        <p className="quiet">Redirect URI: {setup?.redirect_uri}</p>
        <label>
          Google OAuth web client JSON
          <input
            type="file"
            accept=".json"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files[0];
              if (file)
                act(async () => {
                  await client.call("/configuration/google", "POST", {
                    config: JSON.parse(await file.text()),
                  });
                  setSetup(await client.call("/configuration"));
                  setMessage("Google client saved securely");
                });
            }}
          />
        </label>
      </details>
      <details open={!providers.length}>
        <summary>Metadata providers</summary>
        <label>
          Provider configuration
          <select
            value={providerId}
            onChange={(e) => {
              setProviderId(e.target.value);
              const p = providers.find((p) => p.id === e.target.value);
              setProvider(
                p
                  ? Object.fromEntries(
                      Object.keys(providerDefault).map((k) => [k, p[k]]),
                    )
                  : providerDefault,
              );
              setApiKey("");
            }}
          >
            <option value="">New provider</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <div className="grid2">
          {[
            ["Name", "name"],
            ["API base URL", "base_url"],
            ["Model", "model"],
          ].map(([label, key]) => (
            <label key={key}>
              {label}
              <input
                value={provider[key]}
                onChange={(e) =>
                  setProvider((p) => ({ ...p, [key]: e.target.value }))
                }
              />
            </label>
          ))}
          <label>
            JSON response mode
            <select
              value={provider.json_mode}
              onChange={(e) =>
                setProvider((p) => ({ ...p, json_mode: e.target.value }))
              }
            >
              <option value="json_object">JSON object</option>
              <option value="text">Plain text JSON</option>
            </select>
          </label>
        </div>
        <label>
          API key {providerId ? "(leave empty to keep saved key)" : ""}
          <input
            type="password"
            autoComplete="new-password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
        <button
          disabled={busy || !provider.model || (!providerId && !apiKey)}
          onClick={() =>
            act(async () => {
              const p = await client.call(
                "/providers" + (providerId ? "/" + providerId : ""),
                providerId ? "PATCH" : "POST",
                { provider, api_key: apiKey },
              );
              setProviderId(p.id);
              setApiKey("");
              setMessage("Provider saved securely");
            })
          }
        >
          <Save size={16} />
          Save provider
        </button>
      </details>
    </dialog>
  );
}
