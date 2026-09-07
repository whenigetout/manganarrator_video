export const defaultLayer = () => ({
  enabled: true,
  kind: "circular",
  position: "center",
  width: 850,
  height: 850,
  margin_x: 96,
  margin_y: 96,
  opacity: 0.95,
  colors: "#22d3ee|#ec4899|#facc15",
  mode: "bar",
  scale: "log",
  frequency_bins: 64,
  gain: 1,
  radius: 0.27,
  bar_width: 0.55,
  glow: 0.6,
  smoothing: 0.72,
  background_opacity: 0,
  min_frequency: 40,
  max_frequency: 16000,
});
export const defaultConfig = () => ({
  output_name: "my_visualizer.mp4",
  render_config: {
    viewport_w: 2560,
    viewport_h: 1440,
    fps: 30,
    vcodec: "h264_nvenc",
    preset: "p1",
    tune: "hq",
    cq: 23,
  },
  background: {
    mode: "generated",
    generated_style: "aurora",
    color_a: "#080a10",
    color_b: "#6b246f",
    color_c: "#186d78",
    media_refs: [],
    playback_rate: 1,
    blur: 28,
  },
  visualizers: [defaultLayer()],
});
export function mergeConfig(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw))
    throw new Error("Configuration must be an object");
  const base = defaultConfig();
  const result = {
    ...base,
    ...raw,
    render_config: { ...base.render_config, ...raw.render_config },
    background: { ...base.background, ...raw.background },
    visualizers: (raw.visualizers ?? base.visualizers).map((v) => ({
      ...defaultLayer(),
      ...v,
    })),
  };
  if (!Array.isArray(result.background.media_refs)) {
    throw new Error("background.media_refs must be an array");
  }
  for (const layer of result.visualizers) {
    if (
      !["circular", "horizontal", "vertical"].includes(layer.kind) ||
      typeof layer.colors !== "string" ||
      !layer.colors
        .split("|")
        .every((color) => /^(#|0x)?[0-9a-f]{6}$/i.test(color))
    ) {
      throw new Error(
        "Each layer needs a supported layout and six-digit hex colors",
      );
    }
  }
  delete result.audio_ref;
  delete result.source_name;
  delete result.preview_seconds;
  return result;
}
export function exportRequest(config, source, preview = false) {
  const result = structuredClone(config);
  result.audio_ref = source?.audio_ref || {
    namespace: "outputs",
    path: "__demo__.wav",
  };
  result.source_name = source?.name;
  delete result.run_id;
  if (preview) {
    result.preview_seconds = 5;
    result.output_name = "preview.mp4";
  }
  return result;
}
