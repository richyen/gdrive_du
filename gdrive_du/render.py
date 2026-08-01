"""Human-readable rendering: size formatting, du-style and tree-style output."""
from __future__ import annotations

from .crawler import Node


def human_size(num: int, binary: bool = True) -> str:
    """Format a byte count like `du -h` (binary) or `du --si` (decimal)."""
    if num is None:
        num = 0
    base = 1024.0 if binary else 1000.0
    units = ["B", "K", "M", "G", "T", "P", "E"]
    size = float(num)
    for unit in units:
        if abs(size) < base or unit == units[-1]:
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= base
    return f"{size:.1f}E"


def du(
    node: Node,
    human: bool = True,
    max_depth: int | None = None,
    folders_only: bool = True,
    _depth: int = 0,
    _prefix: str = "",
) -> list[str]:
    """Return `du`-style lines: one per folder (or file), size then path.

    Deepest entries print first (like `du`), with the total for each folder
    last among its group. Paths are shown relative to the drive root.
    """
    lines: list[str] = []
    path = node.name if _depth == 0 else f"{_prefix}/{node.name}"

    within_depth = max_depth is None or _depth < max_depth
    if within_depth:
        for child in node.children:
            if child.is_folder:
                lines.extend(
                    du(child, human, max_depth, folders_only, _depth + 1, path)
                )
            elif not folders_only:
                size = human_size(child.total_size) if human else str(child.total_size)
                lines.append(f"{size}\t{path}/{child.name}")

    size = human_size(node.total_size) if human else str(node.total_size)
    lines.append(f"{size}\t{path}")
    return lines


def tree(
    node: Node,
    human: bool = True,
    max_depth: int | None = None,
    folders_only: bool = False,
    show_size: bool = True,
    _depth: int = 0,
    _prefix: str = "",
    _is_last: bool = True,
) -> list[str]:
    """Return `tree`-style lines with box-drawing connectors and sizes."""
    lines: list[str] = []

    if _depth == 0:
        label = node.name
        if show_size:
            size = human_size(node.total_size) if human else str(node.total_size)
            label = f"{node.name}  [{size}]"
        lines.append(label)
    else:
        connector = "└── " if _is_last else "├── "
        size = human_size(node.total_size) if human else str(node.total_size)
        suffix = f"  [{size}]" if show_size else ""
        icon = "" if node.is_folder else ""
        lines.append(f"{_prefix}{connector}{icon}{node.name}{suffix}")

    if max_depth is not None and _depth >= max_depth:
        return lines

    kids = node.children
    if folders_only:
        kids = [c for c in kids if c.is_folder]

    for i, child in enumerate(kids):
        is_last = i == len(kids) - 1
        if _depth == 0:
            child_prefix = ""
        else:
            child_prefix = _prefix + ("    " if _is_last else "│   ")
        lines.extend(
            tree(
                child,
                human,
                max_depth,
                folders_only,
                show_size,
                _depth + 1,
                child_prefix,
                is_last,
            )
        )
    return lines
