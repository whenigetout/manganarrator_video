import { Download, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { defaultLayer, mergeConfig } from "./config";

function Select({ label, value, options, onChange }) {
  return (
    <label>
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((item) => {
          const [v, text] = Array.isArray(item)
            ? item
            : [item, item.replaceAll("_", " ")];
          return (
            <option key={v} value={v}>
              {text}
            </option>
          );
        })}
      </select>
    </label>
  );
}
function Numeric({
  label,
  value,
  onChange,
  min = 0,
  max = 3840,
  step = 1,
  range = false,
}) {
  return (
    <label>
      <span>
        {label}
        {range && <output>{value}</output>}
      </span>
      <input
        aria-label={label}
        type={range ? "range" : "number"}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => {
          if (e.target.value !== "") onChange(Number(e.target.value));
        }}
      />
    </label>
  );
}

export function SettingsPanel({
  config,
  onChange,
  onAudio,
  onClips,
  uploading,
  source,
  onError,
}) {
  const [layer, setLayer] = useState(0);
  const [json, setJson] = useState("");
  const [tab, setTab] = useState("layers");
  const v = config.visualizers[layer];
  const rc = config.render_config;
  useEffect(() => setJson(JSON.stringify(config, null, 2)), [config]);
  const setTop = (key, value) => onChange({ ...config, [key]: value });
  const setRender = (key, value) =>
    setTop("render_config", { ...rc, [key]: value });
  const setBackground = (key, value) =>
    setTop("background", { ...config.background, [key]: value });
  const setLayerValue = (key, value) =>
    setTop(
      "visualizers",
      config.visualizers.map((item, i) =>
        i === layer ? { ...item, [key]: value } : item,
      ),
    );
  function apply(text) {
    try {
      onChange(mergeConfig(JSON.parse(text)));
      setLayer(0);
      onError("");
    } catch (e) {
      onError(e.message);
    }
  }
  function exportJSON() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(config, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "audio_video_config.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <aside className="settings">
      <section className="section">
        <h3>Source</h3>
        <label>
          Audio file
          <input
            type="file"
            accept=".mp3,.wav,.flac,.m4a,.ogg,.aac,audio/*"
            onChange={(e) => e.target.files[0] && onAudio(e.target.files[0])}
          />
        </label>
        <div className="quiet source-name">
          {uploading
            ? "Uploading and preparing audio..."
            : source?.name || "Demo audio"}
        </div>
      </section>
      <div className="tabs settings-tabs" role="tablist" aria-label="Settings">
        {[
          ["layers", "Spectrum"],
          ["background", "Background"],
          ["export", "Export"],
        ].map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "layers" && (
        <section className="section">
          <div className="row">
            <h3>Layers</h3>
            <button
              className="icon"
              title="Add spectrum layer"
              disabled={config.visualizers.length >= 4}
              onClick={() => {
                setTop("visualizers", [
                  ...config.visualizers,
                  {
                    ...defaultLayer(),
                    kind: "horizontal",
                    position: "bottom",
                    width: Math.round(rc.viewport_w * 0.8),
                    height: 220,
                  },
                ]);
                setLayer(config.visualizers.length);
              }}
            >
              <Plus size={16} />
            </button>
          </div>
          <div className="row">
            <select
              aria-label="Selected layer"
              value={layer}
              onChange={(e) => setLayer(Number(e.target.value))}
            >
              {config.visualizers.map((item, i) => (
                <option value={i} key={i}>
                  {i + 1}. {item.kind}
                  {!item.enabled ? " (hidden)" : ""}
                </option>
              ))}
            </select>
            <button
              className="icon"
              title="Remove layer"
              disabled={!v}
              onClick={() => {
                setTop(
                  "visualizers",
                  config.visualizers.filter((_, i) => i !== layer),
                );
                setLayer(Math.max(0, layer - 1));
              }}
            >
              <Trash2 size={16} />
            </button>
          </div>
          {v && (
            <div className="spectrum-fields">
              <label className="check wide">
                <input
                  type="checkbox"
                  checked={v.enabled}
                  onChange={(e) => setLayerValue("enabled", e.target.checked)}
                />
                Visible
              </label>
              <Select
                label="Layout"
                value={v.kind}
                options={["circular", "horizontal", "vertical"]}
                onChange={(x) => setLayerValue("kind", x)}
              />
              <Select
                label="Position"
                value={v.position}
                options={[
                  "center",
                  "top_left",
                  "top_right",
                  "bottom_left",
                  "bottom_right",
                  "top",
                  "bottom",
                  "left",
                  "right",
                ]}
                onChange={(x) => setLayerValue("position", x)}
              />
              <Select
                label="Shape"
                value={v.mode}
                options={["bar", "line", "dot"]}
                onChange={(x) => setLayerValue("mode", x)}
              />
              <Select
                label="Response scale"
                value={v.scale}
                options={["log", "sqrt", "cbrt", "lin"]}
                onChange={(x) => setLayerValue("scale", x)}
              />
              {[
                ["Width (px)", "width", 32, 3840],
                ["Height (px)", "height", 32, 3840],
                ["X margin", "margin_x", 0, 3840],
                ["Y margin", "margin_y", 0, 3840],
              ].map(([label, key, min, max]) => (
                <Numeric
                  key={key}
                  label={label}
                  value={v[key]}
                  min={min}
                  max={max}
                  onChange={(x) => setLayerValue(key, x)}
                />
              ))}
              {[
                ["Bars", "frequency_bins", 8, 256, 1],
                ["Sensitivity", "gain", 0.1, 10, 0.1],
                ["Radius", "radius", 0.05, 0.4, 0.01],
                ["Thickness", "bar_width", 0.1, 0.95, 0.05],
                ["Glow", "glow", 0, 2, 0.1],
                ["Smoothing", "smoothing", 0, 0.98, 0.02],
                ["Opacity", "opacity", 0, 1, 0.05],
              ].map(([label, key, min, max, step]) => (
                <Numeric
                  key={key}
                  label={label}
                  value={v[key]}
                  min={min}
                  max={max}
                  step={step}
                  range
                  onChange={(x) => setLayerValue(key, x)}
                />
              ))}
              <div className="wide">
                <div className="row">
                  <h3>Palette</h3>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={!v.colors.includes("|")}
                      onChange={(e) =>
                        setLayerValue(
                          "colors",
                          e.target.checked
                            ? v.colors.split("|")[0]
                            : "#22d3ee|#ec4899|#facc15",
                        )
                      }
                    />
                    Single color
                  </label>
                </div>
                <div className="color-row">
                  {v.colors.split("|").map((color, i, all) => (
                    <input
                      key={i}
                      type="color"
                      aria-label={`Spectrum color ${i + 1}`}
                      value={color.replace(/^0x/, "#")}
                      onChange={(e) => {
                        const next = [...all];
                        next[i] = e.target.value;
                        setLayerValue("colors", next.join("|"));
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
        </section>
      )}
      {tab === "background" && (
        <section className="section">
          <Select
            label="Background"
            value={config.background.mode}
            options={["generated", "media"]}
            onChange={(x) => setBackground("mode", x)}
          />
          {config.background.mode === "generated" ? (
            <>
              <Select
                label="Style"
                value={config.background.generated_style}
                options={["aurora", "nebula", "gradient", "plasma"]}
                onChange={(x) => setBackground("generated_style", x)}
              />
              <div className="grid2">
                {["color_a", "color_b", "color_c"].map((key, i) => (
                  <label key={key}>
                    {["Base", "Accent", "Secondary"][i]}
                    <input
                      aria-label={`Background ${key}`}
                      type="color"
                      value={config.background[key]}
                      onChange={(e) => setBackground(key, e.target.value)}
                    />
                  </label>
                ))}
              </div>
              <Numeric
                label="Blur"
                value={config.background.blur}
                range
                min={0}
                max={60}
                onChange={(x) => setBackground("blur", x)}
              />
            </>
          ) : (
            <>
              <label>
                Background clips
                <input
                  type="file"
                  multiple
                  accept="video/*"
                  disabled={uploading}
                  onChange={(e) => onClips([...e.target.files])}
                />
              </label>
              <div className="quiet">
                {config.background.media_refs.length} clips selected
              </div>
              <button onClick={() => setBackground("media_refs", [])}>
                Clear clips
              </button>
              <Numeric
                label="Playback speed"
                value={config.background.playback_rate}
                min={0.05}
                max={8}
                step={0.05}
                onChange={(x) => setBackground("playback_rate", x)}
              />
            </>
          )}
        </section>
      )}
      {tab === "export" && (
        <section className="section">
          <Select
            label="Resolution"
            value={`${rc.viewport_w}x${rc.viewport_h}`}
            options={[
              [
                `${rc.viewport_w}x${rc.viewport_h}`,
                `${rc.viewport_w} x ${rc.viewport_h}`,
              ],
              ["1280x720", "720p"],
              ["1920x1080", "1080p"],
              ["2560x1440", "1440p / 2K"],
              ["3840x2160", "2160p / 4K"],
              ["1080x1920", "Vertical 1080p"],
            ].filter((x, i, all) => all.findIndex((y) => y[0] === x[0]) === i)}
            onChange={(value) => {
              const [w, h] = value.split("x").map(Number);
              setTop("render_config", { ...rc, viewport_w: w, viewport_h: h });
            }}
          />
          <Select
            label="Frame rate"
            value={String(rc.fps)}
            options={["24", "30", "60"]}
            onChange={(x) => setRender("fps", Number(x))}
          />
          <Select
            label="Encoder"
            value={rc.vcodec}
            options={["h264_nvenc", "libx264"]}
            onChange={(x) => setRender("vcodec", x)}
          />
          <Select
            label="Quality"
            value={String(rc.cq)}
            options={[
              [String(rc.cq), `CQ / CRF ${rc.cq}`],
              ["28", "Draft"],
              ["23", "Balanced"],
              ["18", "High"],
            ].filter((x, i, all) => all.findIndex((y) => y[0] === x[0]) === i)}
            onChange={(x) => setRender("cq", Number(x))}
          />
          <label>
            Output filename
            <input
              value={config.output_name}
              onChange={(e) => setTop("output_name", e.target.value)}
            />
          </label>
        </section>
      )}
      <details>
        <summary>Configuration JSON</summary>
        <textarea
          aria-label="Configuration JSON"
          spellCheck={false}
          value={json}
          onChange={(e) => setJson(e.target.value)}
        />
        <div className="row">
          <button onClick={() => apply(json)}>Apply JSON</button>
          <button
            className="icon"
            title="Export configuration"
            onClick={exportJSON}
          >
            <Download size={16} />
          </button>
        </div>
        <label>
          Import JSON
          <input
            type="file"
            accept=".json,application/json"
            onChange={async (e) => {
              const file = e.target.files[0];
              if (file) apply(await file.text());
            }}
          />
        </label>
      </details>
    </aside>
  );
}
