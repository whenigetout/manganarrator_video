"""Explicit resumable protocol so checkpoints survive Python process restarts."""
import re
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import httpx
from .models import PublishingError

API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK_SIZE = 8 * 1024 * 1024


def retry_delay(response):
    value = response.headers.get("Retry-After", "0")
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return 0


def confirmed_offset(response, size):
    value = response.headers.get("Range")
    if not value:
        return 0
    match = re.fullmatch(r"bytes=0-(\d+)", value)
    if not match or not 0 < int(match[1]) + 1 <= size:
        raise PublishingError("YouTube returned an invalid upload offset; upload stopped.", "needs_attention")
    return int(match[1]) + 1


def check_response(response):
    if response.status_code in (200, 201, 308):
        return
    if response.status_code in (404, 410):
        raise PublishingError("Upload session expired. Check YouTube Studio for this video before explicitly restarting the upload.", "needs_attention")
    try:
        reason = response.json()["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, TypeError):
        reason = "unknown"
    safe_reason = re.sub(r"[^A-Za-z0-9_]", "", str(reason))[:80]
    if response.status_code in (429, 500, 502, 503, 504) or reason in ("rateLimitExceeded", "userRateLimitExceeded"):
        raise PublishingError("YouTube temporarily unavailable or rate limited.", "retry_wait", retry_delay(response))
    if response.status_code == 401:
        raise PublishingError("Google authorization rejected. Reconnect this channel.", "needs_reauth")
    raise PublishingError(f"YouTube HTTP {response.status_code} ({safe_reason}). Check quota, permissions and metadata before retrying.")


class YouTube:
    def __init__(self, oauth, settings, transport=None):
        self.oauth, self.settings, self.transport = oauth, settings, transport

    def request(self, profile, method, url, **kwargs):
        credentials = self.oauth.credentials(profile)
        headers = kwargs.pop("headers", {})
        with httpx.Client(timeout=120, transport=self.transport, follow_redirects=False) as client:
            for force in (False, True):
                if force:
                    credentials = self.oauth.credentials(profile, force=True)
                try:
                    response = client.request(method, url, headers={**headers, "Authorization": "Bearer " + credentials.token}, **kwargs)
                except httpx.TransportError as exc:
                    raise PublishingError("Connection interrupted. Upload will query YouTube before resuming.", "retry_wait") from exc
                if response.status_code != 401:
                    return response
            check_response(response)

    def upload(self, run, path, checkpoint, stopping=lambda: False):
        if run.get("video_id"):
            raise PublishingError("This run already has a YouTube video ID. A second upload is blocked.", "needs_attention")
        profile = run["profile"]
        self.oauth.verify(profile)
        size = path.stat().st_size
        secret_name = "upload:" + run["id"]
        session = self.settings.get_secret(secret_name)
        if not session:
            if run.get("session_created"):
                raise PublishingError("Saved upload session is missing. Check YouTube Studio before restarting.", "needs_attention")
            review = run["review"]
            body = {"snippet": {**run["metadata"], "categoryId": review["category"], "defaultLanguage": profile["language"]},
                    "status": {"privacyStatus": review["privacy"], "selfDeclaredMadeForKids": review["made_for_kids"],
                               "containsSyntheticMedia": review["contains_synthetic_media"]}}
            response = self.request(profile, "POST", UPLOAD, params={"uploadType": "resumable", "part": "snippet,status", "notifySubscribers": "false"},
                                    json=body, headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"})
            check_response(response)
            session = response.headers.get("Location", "")
            url = urlsplit(session)
            if url.scheme != "https" or url.hostname != "www.googleapis.com" or not url.path.startswith("/upload/"):
                raise PublishingError("YouTube returned an invalid upload session URL.", "needs_attention")
            self.settings.set_secret(secret_name, session)
            checkpoint({"session_created": True, "upload_bytes": 0, "upload_total": size})
        response = self.request(profile, "PUT", session, content=b"", headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"})
        with path.open("rb") as source:
            while True:
                check_response(response)
                if response.status_code in (200, 201):
                    result = response.json()
                    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", result.get("id", "")):
                        raise PublishingError("YouTube completion response has no valid video ID. Reconcile in YouTube Studio.", "needs_attention")
                    return result
                offset = confirmed_offset(response, size)
                checkpoint({"upload_bytes": offset, "upload_total": size, "progress": 100 * offset / size})
                delay = retry_delay(response)
                if delay:
                    raise PublishingError("YouTube requested a pause before the next upload chunk.", "retry_wait", delay)
                if stopping():
                    raise InterruptedError()
                if offset == size:
                    raise PublishingError("Waiting for YouTube to acknowledge completion.", "retry_wait", 5)
                source.seek(offset)
                chunk = source.read(CHUNK_SIZE)
                response = self.request(profile, "PUT", session, content=chunk,
                                        headers={"Content-Type": "video/mp4", "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{size}"})
                if response.status_code == 308 and confirmed_offset(response, size) <= offset:
                    raise PublishingError("YouTube has not acknowledged this chunk. Checking again shortly.", "retry_wait", 5)

    def processing(self, run):
        response = self.request(run["profile"], "GET", API + "/videos", params={"part": "snippet,status,processingDetails", "id": run["video_id"]})
        if response.status_code == 404:
            raise PublishingError("Uploaded video is no longer available. Check YouTube Studio.", "needs_attention")
        check_response(response)
        items = response.json().get("items", [])
        if not items:
            raise PublishingError("Uploaded video is unavailable to this channel. Check YouTube Studio.", "needs_attention")
        video = items[0]
        if video["snippet"]["channelId"] != run["profile"]["channel_id"]:
            raise PublishingError("Returned video belongs to a different channel. Check YouTube Studio.", "needs_attention")
        status = video.get("processingDetails", {}).get("processingStatus", "processing")
        upload_status = video.get("status", {}).get("uploadStatus")
        if status in ("failed", "terminated") or upload_status in ("failed", "rejected", "deleted"):
            raise PublishingError("YouTube could not process or accepted then rejected this video. Check YouTube Studio.", "needs_attention")
        return status == "succeeded" or upload_status == "processed", video["status"].get("privacyStatus")
