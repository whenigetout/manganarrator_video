export class AudioVideoClient {
  constructor(baseUrl = "") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }
  async response(path, options = {}) {
    const response = await fetch(this.baseUrl + path, options);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail || `HTTP ${response.status}`),
      );
    }
    return response;
  }
  async request(path, options) {
    return (await this.response(path, options)).json();
  }
  capabilities() {
    return this.request("/video/audio/capabilities");
  }
  jobs() {
    return this.request("/video/audio/jobs");
  }
  status(id) {
    return this.request(`/video/status/${encodeURIComponent(id)}`);
  }
  uploadSource(file, signal) {
    const form = new FormData();
    form.append("audio_file", file);
    return this.request("/video/audio/source", {
      method: "POST",
      body: form,
      signal,
    });
  }
  render(config) {
    return this.request("/video/build/audio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
  }
  async frame(config, seconds, demo, signal) {
    const response = await this.response("/video/audio/frame", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config, seconds, demo }),
      signal,
    });
    return {
      blob: await response.blob(),
      timestamp: Number(response.headers.get("X-Frame-Time") || seconds),
    };
  }
  background(file) {
    const form = new FormData();
    form.append("video_file", file);
    return this.request("/video/audio/background", {
      method: "POST",
      body: form,
    });
  }
  fileUrl(id, download = false) {
    return `${this.baseUrl}/video/audio/jobs/${encodeURIComponent(id)}/file?download=${download}`;
  }
}
