export default {
  async fetch(request, env) {
    const email = request.headers.get("oai-authenticated-user-email");
    if (!email || !env.STORY_OWNER_EMAIL || email.toLowerCase() !== env.STORY_OWNER_EMAIL.toLowerCase()) {
      return new Response("Story Studio is private", { status: 403 });
    }
    const url = new URL(request.url);
    if (url.pathname.startsWith("/video/story/")) {
      if (!["GET", "POST", "PUT", "DELETE"].includes(request.method)) {
        return new Response(null, { status: 405 });
      }
      const origin = request.headers.get("origin");
      if ((origin && origin !== url.origin) || request.headers.get("sec-fetch-site") === "cross-site") {
        return new Response(null, { status: 403 });
      }
      if (!env.STORY_SHARED_URL || !env.STORY_SHARED_TOKEN) {
        return Response.json({ detail: "Shared Story Studio is not configured" }, { status: 503 });
      }
      try {
        const target = new URL(env.STORY_SHARED_URL);
        if (target.protocol !== "https:" || target.username || target.password
          || target.pathname !== "/" || target.search || target.hash) {
          throw new Error("Invalid upstream");
        }
        target.pathname = url.pathname;
        target.search = url.search;
        const headers = { Authorization: `Bearer ${env.STORY_SHARED_TOKEN}` };
        const contentType = request.headers.get("content-type");
        if (contentType) headers["Content-Type"] = contentType;
        const upstream = await fetch(target, {
          method: request.method, headers, body: request.body, redirect: "error",
        });
        const responseHeaders = { "Cache-Control": "no-store" };
        const type = upstream.headers.get("content-type");
        if (type) responseHeaders["Content-Type"] = type;
        return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
      } catch {
        return Response.json({ detail: "Shared Story Studio is unavailable" }, { status: 502 });
      }
    }
    const path = url.pathname === "/" ? "/index.html" : url.pathname;
    if (!Object.hasOwn(assets, path)) {
      return new Response("Not found", { status: 404 });
    }
    const asset = assets[path];
    return new Response(asset.body, { headers: {
      "Content-Type": asset.type, "Cache-Control": "private, no-store",
    } });
  },
};
