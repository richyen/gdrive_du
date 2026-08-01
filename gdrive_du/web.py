"""Flask web UI for gdrive_du: pick a shared drive, view du sizes and an interactive tree."""
from __future__ import annotations

import os
import threading
import traceback

from flask import Flask, jsonify, render_template, request

from .auth import get_service
from .crawler import crawl_to_dict, list_shared_drives

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(_BASE, "templates"),
    static_folder=os.path.join(_BASE, "static"),
)

# Simple in-process cache of the most recent crawl per drive id.
_cache: dict[str, dict] = {}
_lock = threading.Lock()


def _service():
    credentials = os.environ.get("GDRIVE_DU_CREDENTIALS", "credentials.json")
    token = os.environ.get("GDRIVE_DU_TOKEN", "token.json")
    return get_service(credentials, token)


@app.route("/")
def index():
    return render_template("index.html")


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
