"""
Sandboxed file system operations.

All paths are resolved relative to a root directory. Path traversal
outside the root is rejected.
"""

from __future__ import annotations

import re
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
    if not content:
        return (
            f"WARNING: wrote empty file {filepath} (0 bytes) — "
            f"content was empty. If intentional, ignore this. "
            f"If not, re-call ws_write with the intended content."
        )
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


def ws_append(root: Path, filepath: str, content: str, separator: str = "\n\n") -> str:
    """Append content to a workspace file, creating it if it doesn't exist."""
    path = _resolve(root, filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        combined = existing.rstrip("\n") + separator + content
        path.write_text(combined, encoding="utf-8")
        return f"Appended {len(content)} chars to {filepath}"
    else:
        path.write_text(content, encoding="utf-8")
        return f"Created {filepath} with {len(content)} chars"


def ws_update(
    root: Path,
    filepath: str,
    section: str,
    content: str,
    level: int = 2,
    create_if_missing: bool = True,
) -> str:
    """Upsert a named section in a Markdown file.

    If the section exists, its content is replaced.
    If not, the section is appended.
    """
    path = _resolve(root, filepath)
    heading_marker = "#" * level
    heading_line = f"{heading_marker} {section}"

    if not path.exists():
        if not create_if_missing:
            return f"File not found: {filepath}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{heading_line}\n\n{content}\n", encoding="utf-8")
        return f"Created {filepath} with section '{section}'"

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Find the target section heading
    section_start = None
    for i, line in enumerate(lines):
        if line.rstrip("\n") == heading_line:
            section_start = i
            break

    if section_start is None:
        # Section not found — append it
        new_text = text.rstrip("\n") + f"\n\n{heading_line}\n\n{content}\n"
        path.write_text(new_text, encoding="utf-8")
        return f"Appended new section '{section}' to {filepath}"

    # Find where this section ends (next heading of same or higher level, or EOF)
    section_end = len(lines)
    heading_pattern = re.compile(r"^#{1," + str(level) + r"} ")
    for i in range(section_start + 1, len(lines)):
        if heading_pattern.match(lines[i]):
            section_end = i
            break

    # Rebuild: before section + new section content + after section
    before = "".join(lines[:section_start])
    after = "".join(lines[section_end:])
    new_text = before + f"{heading_line}\n\n{content}\n\n" + after

    path.write_text(new_text, encoding="utf-8")
    return f"Updated section '{section}' in {filepath}"


_TEXT_SUFFIXES = {".md", ".txt", ".py", ".yaml", ".yml", ".json", ".toml", ".html", ".csv"}


def ws_grep(
    root: Path,
    pattern: str,
    glob: str = "**/*",
    case_insensitive: bool = True,
    context_lines: int = 1,
    max_results: int = 20,
    regex: bool = False,
) -> str:
    """Search for a pattern across workspace files."""
    workspace = root.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    # Build matcher
    if regex:
        flags = re.IGNORECASE if case_insensitive else 0
        compiled = re.compile(pattern, flags)

        def matches(line: str) -> bool:
            return bool(compiled.search(line))
    else:
        needle = pattern.lower() if case_insensitive else pattern

        def matches(line: str) -> bool:
            haystack = line.lower() if case_insensitive else line
            return needle in haystack

    # Collect all candidate files
    candidates = sorted(workspace.glob(glob))
    candidates = [
        f for f in candidates
        if f.is_file() and f.suffix.lower() in _TEXT_SUFFIXES
    ]

    results: list[tuple[str, list[list[tuple[int, str, bool]]], int]] = []

    for filepath in candidates:
        try:
            lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue

        # Find matching line indices
        match_indices = [i for i, line in enumerate(lines) if matches(line)]
        if not match_indices:
            continue

        # Build context windows
        groups = []
        for mi in match_indices:
            start = max(0, mi - context_lines)
            end = min(len(lines) - 1, mi + context_lines)
            group = [
                (j + 1, lines[j], j == mi)
                for j in range(start, end + 1)
            ]
            groups.append(group)

        rel_path = str(filepath.relative_to(workspace))
        results.append((rel_path, groups, len(match_indices)))

        if sum(r[2] for r in results) >= max_results:
            break

    if not results:
        return f"No matches for '{pattern}' in workspace"

    # Format output
    output_lines = []
    total_matches = sum(r[2] for r in results)

    for rel_path, groups, _match_count in results:
        output_lines.append(rel_path)
        for group in groups:
            for line_num, line_text, is_match in group:
                prefix = ">" if is_match else " "
                output_lines.append(f"  {prefix} L{line_num}: {line_text.rstrip()}")
            output_lines.append("")

    if total_matches >= max_results:
        output_lines.append(
            f"... showing first {max_results} matches. "
            f"Use a more specific pattern or glob to narrow results."
        )

    return "\n".join(output_lines).strip()
