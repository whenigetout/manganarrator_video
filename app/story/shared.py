"""Same-origin desktop access to the canonical Story Studio API."""

import os
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask


def install_shared_story(app):
    upstream = os.environ.get("STORY_SHARED_URL")
    token = os.environ.get("STORY_SHARED_TOKEN")
    if bool(upstream) != bool(token):
        raise RuntimeError("Set both STORY_SHARED_URL and STORY_SHARED_TOKEN")
    if upstream:
        parsed = urlsplit(upstream)
        loopback = parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")
        if (not parsed.hostname or (parsed.scheme != "https" and not loopback)
                or parsed.username or parsed.password or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment):
            raise RuntimeError("STORY_SHARED_URL must be an HTTPS origin or loopback HTTP origin")

    @app.get("/video/story-connection")
    def story_connection():
        return {"preparation": bool(upstream)}

    if not upstream:
        return

    import httpx

    @app.api_route("/shared-story/video/story/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def proxy(path: str, request: Request):
        # The Windows service is local. Block cross-origin browser requests from
        # using it as a bridge to the authenticated upstream.
        if request.url.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise HTTPException(403, "Use the local Studio address")
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Cross-origin story requests are forbidden")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Cross-site story requests are forbidden")
        if any(part in ("", ".", "..") for part in path.split("/")):
            raise HTTPException(400, "Invalid story path")

        target = httpx.URL(upstream.rstrip("/")).copy_with(
            path=f"/video/story/{path}", query=request.url.query.encode("ascii")
        )
        headers = {"Authorization": f"Bearer {token}"}
        if "content-type" in request.headers:
            headers["Content-Type"] = request.headers["content-type"]
        client = httpx.AsyncClient(timeout=60, trust_env=False)
        try:
            outgoing = client.build_request(
                request.method, target, headers=headers,
                content=request.stream() if request.method in ("POST", "PUT") else None,
            )
            response = await client.send(outgoing, stream=True)
        except httpx.HTTPError:
            await client.aclose()
            return Response('{"detail":"Shared Story Studio is unavailable"}',
                            status_code=502, media_type="application/json")

        async def close():
            await response.aclose()
            await client.aclose()

        return StreamingResponse(
            response.aiter_bytes(), status_code=response.status_code,
            media_type=response.headers.get("content-type"),
            headers={"Cache-Control": "no-store"}, background=BackgroundTask(close),
        )
