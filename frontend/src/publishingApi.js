const PREFIX = "/video/publishing";
let launchToken = "";

export function readLaunchToken() {
  if (typeof window === "undefined") return "";
  const params = new URLSearchParams(window.location.hash.slice(1));
  if (params.has("publishingToken")) {
    launchToken = params.get("publishingToken");
    params.delete("publishingToken");
    window.history.replaceState(
      null,
      "",
      window.location.pathname +
        window.location.search +
        (params.size ? "#" + params : ""),
    );
  }
  return launchToken;
}

export class PublishingClient {
  constructor(base = "", token = "") {
    this.base = base.replace(/\/$/, "");
    this.token = token;
  }
  async call(path, method = "GET", data, extra = {}) {
    const response = await fetch(this.base + PREFIX + path, {
      method,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-Publishing-Client": "studio",
        ...(this.token ? { Authorization: "Bearer " + this.token } : {}),
        ...extra,
      },
      ...(data === undefined ? {} : { body: JSON.stringify(data) }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(
        typeof body.detail === "string"
          ? body.detail
          : "Check the form fields and try again.",
      );
      error.status = response.status;
      throw error;
    }
    return body;
  }
  async unlock() {
    await this.call("/session", "POST");
    this.token = "";
    launchToken = "";
  }
  fileUrl(id, download = false) {
    return `${this.base}${PREFIX}/runs/${encodeURIComponent(id)}/file?download=${download}`;
  }
}
