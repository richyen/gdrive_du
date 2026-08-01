"""Crawl a Google Shared Drive: list drives, fetch every item, build a size tree."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

FOLDER_MIME = "application/vnd.google-apps.folder"

# Fields requested per file. `size` is absent on Google-native docs (Docs,
# Sheets, Slides, ...), which occupy no Drive storage quota, so we treat them
# as 0 bytes.
FILE_FIELDS = "id,name,mimeType,size,parents,md5Checksum,modifiedTime,trashed"
LIST_FIELDS = f"nextPageToken, files({FILE_FIELDS})"


def list_shared_drives(service) -> list[dict]:
    """Return all shared drives the user can access: [{id, name}, ...]."""
    drives: list[dict] = []
    page_token = None
    while True:
        resp = (
            service.drives()
            .list(pageSize=100, fields="nextPageToken, drives(id,name)", pageToken=page_token)
            .execute()
        )
        drives.extend(resp.get("drives", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return drives


def fetch_all_items(
    service,
    drive_id: str,
    include_trashed: bool = False,
    progress: Callable[[int], None] | None = None,
) -> list[dict]:
    """Fetch every file/folder in a shared drive via paginated listing."""
    items: list[dict] = []
    page_token = None
    query = "trashed = false" if not include_trashed else None
    while True:
        resp = (
            service.files()
            .list(
                corpora="drive",
                driveId=drive_id,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                q=query,
                pageSize=1000,
                fields=LIST_FIELDS,
                pageToken=page_token,
            )
            .execute()
        )
        items.extend(resp.get("files", []))
        if progress:
            progress(len(items))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


@dataclass
class Node:
    """A folder or file node in the drive tree."""

    id: str
    name: str
    is_folder: bool
    own_size: int = 0  # bytes of this file itself (0 for folders / native docs)
    mime_type: str = ""
    modified_time: str = ""
    children: list["Node"] = field(default_factory=list)
    total_size: int = 0  # own_size + all descendants (computed)
    file_count: int = 0  # number of non-folder descendants (computed)

    def to_dict(self, include_files: bool = True) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "is_folder": self.is_folder,
            "total_size": self.total_size,
            "own_size": self.own_size,
            "file_count": self.file_count,
            "mime_type": self.mime_type,
            "modified_time": self.modified_time,
        }
        if self.is_folder:
            kids = self.children if include_files else [c for c in self.children if c.is_folder]
            d["children"] = [c.to_dict(include_files) for c in kids]
        return d


def _to_int_size(raw) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def build_tree(items: list[dict], drive_id: str, drive_name: str) -> Node:
    """Assemble items into a tree rooted at the shared drive, computing sizes.

    Items whose parents fall outside the fetched set (rare, e.g. permission
    edge cases) are attached to the root so nothing is silently dropped.
    """
    root = Node(id=drive_id, name=drive_name, is_folder=True, mime_type=FOLDER_MIME)
    nodes: dict[str, Node] = {drive_id: root}

    # First pass: create a Node for every item.
    for it in items:
        is_folder = it.get("mimeType") == FOLDER_MIME
        nodes[it["id"]] = Node(
            id=it["id"],
            name=it.get("name", "(unnamed)"),
            is_folder=is_folder,
            own_size=0 if is_folder else _to_int_size(it.get("size")),
            mime_type=it.get("mimeType", ""),
            modified_time=it.get("modifiedTime", ""),
        )

    # Second pass: wire up parent -> child relationships.
    for it in items:
        node = nodes[it["id"]]
        parents = it.get("parents") or []
        parent_id = parents[0] if parents else drive_id
        parent = nodes.get(parent_id, root)
        parent.children.append(node)

    _aggregate(root)
    return root


def _aggregate(node: Node) -> tuple[int, int]:
    """Post-order: fill total_size and file_count. Returns (size, file_count)."""
    total = node.own_size
    count = 0 if node.is_folder else 1
    for child in node.children:
        c_size, c_count = _aggregate(child)
        total += c_size
        count += c_count
    node.total_size = total
    node.file_count = count
    # Sort children: folders first, then by descending size, then name.
    node.children.sort(key=lambda n: (not n.is_folder, -n.total_size, n.name.lower()))
    return total, count


def crawl(
    service,
    drive_id: str,
    drive_name: str,
    include_trashed: bool = False,
    progress: Callable[[int], None] | None = None,
) -> Node:
    """Full crawl: fetch all items in a drive and build the aggregated tree."""
    items = fetch_all_items(service, drive_id, include_trashed, progress)
    return build_tree(items, drive_id, drive_name)


def crawl_to_dict(service, drive_id: str, drive_name: str, include_trashed: bool = False) -> dict:
    """Crawl and return a JSON-serializable snapshot with metadata."""
    root = crawl(service, drive_id, drive_name, include_trashed)
    return {
        "drive_id": drive_id,
        "drive_name": drive_name,
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_size": root.total_size,
        "file_count": root.file_count,
        "tree": root.to_dict(include_files=True),
    }
