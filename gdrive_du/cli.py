"""Command-line interface for gdrive_du."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .auth import get_service
from .crawler import Node, crawl, crawl_to_dict, list_shared_drives
from .render import du, human_size, tree


def _pick_drive(service, requested: str | None) -> tuple[str, str]:
    """Resolve a drive id/name. If none given, prompt interactively."""
    drives = list_shared_drives(service)
    if not drives:
        print("No shared drives found for this account.", file=sys.stderr)
        sys.exit(1)

    if requested:
        for d in drives:
            if requested in (d["id"], d["name"]):
                return d["id"], d["name"]
        print(f"Shared drive not found: {requested}", file=sys.stderr)
        requested = None  # fall through to interactive picker

    print("Shared drives:")
    for i, d in enumerate(drives, 1):
        print(f"  {i}. {d['name']}  ({d['id']})")
    while True:
        choice = input("Select a drive [number]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(drives):
            d = drives[int(choice) - 1]
            return d["id"], d["name"]
        print("Invalid selection.")


def _load_or_crawl(args, service) -> Node:
    """Either crawl live or return a Node reconstructed from a snapshot file."""
    if getattr(args, "load", None):
        with open(args.load, encoding="utf-8") as fh:
            snap = json.load(fh)
        return _node_from_dict(snap["tree"])
    drive_id, drive_name = _pick_drive(service, args.drive)
    print(f"Crawling '{drive_name}' ...", file=sys.stderr)

    def progress(n: int) -> None:
        print(f"\r  fetched {n} items", end="", file=sys.stderr)

    root = crawl(service, drive_id, drive_name, include_trashed=args.include_trashed, progress=progress)
    print("", file=sys.stderr)
    return root


def _node_from_dict(d: dict) -> Node:
    node = Node(
        id=d["id"],
        name=d["name"],
        is_folder=d["is_folder"],
        own_size=d.get("own_size", 0),
        mime_type=d.get("mime_type", ""),
        modified_time=d.get("modified_time", ""),
        total_size=d.get("total_size", 0),
        file_count=d.get("file_count", 0),
    )
    node.children = [_node_from_dict(c) for c in d.get("children", [])]
    return node


def cmd_drives(args) -> None:
    service = get_service(args.credentials, args.token)
    for d in list_shared_drives(service):
        print(f"{d['id']}\t{d['name']}")


def cmd_du(args) -> None:
    service = None if args.load else get_service(args.credentials, args.token)
    root = _load_or_crawl(args, service)
    for line in du(root, human=not args.bytes, max_depth=args.max_depth, folders_only=not args.all):
        print(line)


def cmd_tree(args) -> None:
    service = None if args.load else get_service(args.credentials, args.token)
    root = _load_or_crawl(args, service)
    for line in tree(
        root,
        human=not args.bytes,
        max_depth=args.max_depth,
        folders_only=args.folders_only,
        show_size=not args.no_size,
    ):
        print(line)


def cmd_crawl(args) -> None:
    service = get_service(args.credentials, args.token)
    drive_id, drive_name = _pick_drive(service, args.drive)
    print(f"Crawling '{drive_name}' ...", file=sys.stderr)
    snap = crawl_to_dict(service, drive_id, drive_name, include_trashed=args.include_trashed)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2)
    print(
        f"Saved snapshot to {args.output}: {snap['file_count']} files, "
        f"{human_size(snap['total_size'])} total.",
        file=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gdrive-du",
        description="Crawl a Google Shared Drive and report folder sizes (du) and tree listings.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--credentials", default=None, help="OAuth client secrets JSON (default: credentials.json)")
    p.add_argument("--token", default=None, help="Cached token file (default: token.json)")

    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("drives", help="List accessible shared drives")
    sp.set_defaults(func=cmd_drives)

    common_drive = argparse.ArgumentParser(add_help=False)
    common_drive.add_argument("-d", "--drive", help="Shared drive id or name (else interactive)")
    common_drive.add_argument("--load", help="Read from a saved snapshot JSON instead of crawling")
    common_drive.add_argument("--include-trashed", action="store_true", help="Include trashed items")
    common_drive.add_argument("-b", "--bytes", action="store_true", help="Raw byte counts, not human-readable")
    common_drive.add_argument("-L", "--max-depth", type=int, default=None, help="Limit recursion depth")

    sp = sub.add_parser("du", parents=[common_drive], help="du-style folder sizes")
    sp.add_argument("-a", "--all", action="store_true", help="Include individual files, not just folders")
    sp.set_defaults(func=cmd_du)

    sp = sub.add_parser("tree", parents=[common_drive], help="tree-style listing")
    sp.add_argument("--folders-only", action="store_true", help="Show folders only")
    sp.add_argument("--no-size", action="store_true", help="Hide sizes")
    sp.set_defaults(func=cmd_tree)

    sp = sub.add_parser("crawl", help="Crawl and save a snapshot JSON (for reuse / web UI)")
    sp.add_argument("-d", "--drive", help="Shared drive id or name (else interactive)")
    sp.add_argument("--include-trashed", action="store_true", help="Include trashed items")
    sp.add_argument("-o", "--output", default="snapshot.json", help="Output file (default: snapshot.json)")
    sp.set_defaults(func=cmd_crawl)

    return p


def main(argv: list[str] | None = None) -> None:
    # Box-drawing characters and emoji need UTF-8; Windows consoles default to cp1252.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    # Map None defaults to auth module defaults.
    args.credentials = args.credentials or "credentials.json"
    args.token = args.token or "token.json"
    try:
        args.func(args)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
