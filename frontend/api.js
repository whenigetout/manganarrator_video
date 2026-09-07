export class AudioVideoClient {
  constructor(baseUrl = '') { this.baseUrl = baseUrl.replace(/\/$/, ''); }
  async request(path, options = {}) {
    const response = await fetch(this.baseUrl + path, options);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || `HTTP ${response.status}`));
    }
    return response.json();
  }
  capabilities() { return this.request('/video/audio/capabilities'); }
  jobs() { return this.request('/video/audio/jobs'); }
  status(id) { return this.request(`/video/status/${encodeURIComponent(id)}`); }
  render(file, config) {
    const form = new FormData();
    form.append('audio_file', file);
    form.append('config_json', JSON.stringify(config));
    return this.request('/video/build/audio_upload', {method: 'POST', body: form});
  }
  background(file) {
    const form = new FormData(); form.append('video_file', file);
    return this.request('/video/audio/background', {method: 'POST', body: form});
  }
  fileUrl(id, download = false) { return `${this.baseUrl}/video/audio/jobs/${encodeURIComponent(id)}/file?download=${download}`; }
}
