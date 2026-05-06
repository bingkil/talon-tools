"""
Sandboxed file system operations.

All paths are resolved relative to a root directory. Path traversal
outside the root is rejected.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


def _resolve(root: Path, filepath: str) -> Path:
    """Resolve a relative path inside the root, rejecting escapes."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    clean = PurePosixPath(filepath)
    if clean.is_absolute() or ".." in clean.parts:
        raise ValueError(f"Invalid path: {filepath}")
    resolved = (root / filepath).resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError(f"Path escapes workspace: {filepath}")
    return resolved


def ws_read(root: Path, filepath: str) -> str:
    """Read a file from the workspace."""
    path = _resolve(root, filepath)
    if not path.is_file():
        return f"File not found: {filepath}"
    return path.read_text(encoding="utf-8")


def ws_write(root: Path, filepath: str, content: str) -> str:
    """Write (create or overwrite) a file in the workspace."""
    path = _resolve(root, filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Written: {filepath} ({len(content)} bytes)"


def ws_list(root: Path, dirpath: str = "") -> str:
    """List files and directories in a workspace path."""
    root_resolved = root.resolve()
    root_resolved.mkdir(parents=True, exist_ok=True)
    if dirpath:
        target = _resolve(root, dirpath)
    else:
        target = root_resolved

    if not target.is_dir():
        return f"Not a directory: {dirpath}"

    entries = []
    for item in sorted(target.iterdir()):
        rel = item.relative_to(root_resolved)
        suffix = "/" if item.is_dir() else f" ({item.stat().st_size}b)"
        entries.append(f"{rel}{suffix}")

    return "\n".join(entries) if entries else "(empty)"


def ws_delete(root: Path, filepath: str) -> str:
    """Delete a file or directory from the workspace."""
    path = _resolve(root, filepath)
    if not path.exists():
        return f"Not found: {filepath}"
    if path.is_dir():
        import shutil
        shutil.rmtree(path)
        return f"Deleted directory: {filepath}"
    path.unlink()
    return f"Deleted: {filepath}"
