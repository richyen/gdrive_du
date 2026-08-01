"""Flask web UI for gdrive_du: pick a shared drive, view du sizes and an interactive tree."""
from __future__ import annotations

import io
import os
import re
import threading
import traceback

from flask import Flask, Response, jsonify, render_template, request
from googleapiclient.http import MediaIoBaseDownload

from .auth import get_service
from .crawler import FOLDER_MIME, crawl_to_dict, list_shared_drives

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(_BASE, "templates"),
    static_folder=os.path.join(_BASE, "static"),
)

# Simple in-process cache of the most recent crawl per drive id.
_cache: dict[str, dict] = {}
_lock = threading.Lock()

# Global, server-enforced download switch. Off by default; the UI toggle flips
# it via /api/config, and /api/download refuses to serve bytes while it is off.
_allow_downloads = False

# Google-native mime -> (export mime, file extension) for click-to-download.
_EXPORT_MAP = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
    "application/vnd.google-apps.script": ("application/vnd.google-apps.script+json", ".json"),
}
_EXPORT_FALLBACK = ("application/pdf", ".pdf")


def _service():
    credentials = os.environ.get("GDRIVE_DU_CREDENTIALS", "credentials.json")
    token = os.environ.get("GDRIVE_DU_TOKEN", "token.json")
    return get_service(credentials, token)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    """Get or set the global 'allow downloads' flag."""
    global _allow_downloads
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        _allow_downloads = bool(data.get("allow_downloads"))
    return jsonify({"allow_downloads": _allow_downloads})


@app.route("/api/drives")
def api_drives():
    try:
        drives = list_shared_drives(_service())
        return jsonify({"drives": drives})
    except Exception as exc:  # surface auth/setup errors to the UI
        traceback.print_exc()
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/crawl")
def api_crawl():
    drive_id = request.args.get("drive_id", "").strip()
    if not drive_id:
        return jsonify({"error": "drive_id is required"}), 400
    drive_name = request.args.get("drive_name", drive_id)
    include_trashed = request.args.get("include_trashed") == "1"
    refresh = request.args.get("refresh") == "1"

    with _lock:
        cached = _cache.get(drive_id)
    if cached and not refresh:
        return jsonify(cached)

    try:
        snap = crawl_to_dict(_service(), drive_id, drive_name, include_trashed=include_trashed)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    with _lock:
        _cache[drive_id] = snap
    return jsonify(snap)


def _sanitize_filename(name: str) -> str:
    """Strip characters that are unsafe in a Content-Disposition filename."""
    name = re.sub(r'[\r\n"]', "", name or "download")
    return name.strip() or "download"


def _stream_media(request_obj, chunk_size: int = 1024 * 1024):
    """Yield a Drive media/export download in chunks without buffering it all."""
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request_obj, chunksize=chunk_size)
    sent = 0
    done = False
    while not done:
        _status, done = downloader.next_chunk()
        data = buf.getvalue()
        if len(data) > sent:
            yield data[sent:]
            sent = len(data)


@app.route("/api/download")
def api_download():
    """Stream a single file to the browser (only when downloads are enabled)."""
    if not _allow_downloads:
        return jsonify({"error": "Downloads are disabled. Enable 'allow downloads' first."}), 403

    file_id = request.args.get("file_id", "").strip()
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    try:
        service = _service()
        meta = (
            service.files()
            .get(fileId=file_id, fields="id,name,mimeType", supportsAllDrives=True)
            .execute()
        )
        name = meta.get("name", "download")
        mime = meta.get("mimeType", "application/octet-stream")

        if mime == FOLDER_MIME:
            return jsonify({"error": "Cannot download a folder."}), 400

        if mime.startswith("application/vnd.google-apps"):
            # Native Google doc: must be exported to a concrete format.
            export_mime, ext = _EXPORT_MAP.get(mime, _EXPORT_FALLBACK)
            if not name.lower().endswith(ext):
                name += ext
            req = service.files().export_media(fileId=file_id, mimeType=export_mime)
            out_mime = export_mime
        else:
            req = service.files().get_media(fileId=file_id, supportsAllDrives=True)
            out_mime = mime

        filename = _sanitize_filename(name)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(_stream_media(req), mimetype=out_mime, headers=headers)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="gdrive-du-web", description="gdrive_du web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    print(f"Open http://{args.host}:{args.port} in your browser.")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
