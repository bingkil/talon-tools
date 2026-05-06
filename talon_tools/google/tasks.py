"""
Google Tasks integration — list, create, complete, and delete tasks.

Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

from googleapiclient.discovery import build

from .auth import get_credentials

_services: dict[str, object] = {}


def _service(token_file=None):
    key = str(token_file) if token_file else "__default__"
    if key not in _services:
        _services[key] = build("tasks", "v1", credentials=get_credentials(token_file))
    return _services[key]


def list_task_lists(max_results: int = 10, token_file=None) -> str:
    """List all task lists."""
    svc = _service(token_file)
    result = svc.tasklists().list(maxResults=max_results).execute()
    items = result.get("items", [])
    if not items:
        return "No task lists found."

    lines = []
    for tl in items:
        lines.append(f"[{tl['id']}] {tl['title']} (updated: {tl.get('updated', '?')})")
    return "\n".join(lines)


def list_tasks(tasklist_id: str = "@default", max_results: int = 20, show_completed: bool = False, token_file=None) -> str:
    """List tasks in a task list."""
    svc = _service(token_file)
    result = svc.tasks().list(
        tasklist=tasklist_id,
        maxResults=max_results,
        showCompleted=show_completed,
        showHidden=show_completed,
    ).execute()
    items = result.get("items", [])
    if not items:
        return "No tasks found."

    lines = []
    for t in items:
        status = "\u2705" if t.get("status") == "completed" else "\u2b1c"
        due = t.get("due", "")
        due_str = f" (due: {due[:10]})" if due else ""
        notes = t.get("notes", "")
        notes_str = f" \u2014 {notes[:60]}" if notes else ""
        lines.append(f"{status} [{t['id']}] {t.get('title', '(no title)')}{due_str}{notes_str}")
    return "\n".join(lines)


def create_task(
    title: str,
    notes: str = "",
    due: str = "",
    tasklist_id: str = "@default",
    token_file=None,
) -> str:
    """Create a new task. due: RFC 3339 like '2026-05-10T00:00:00.000Z'."""
    svc = _service(token_file)
    body: dict = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due

    task = svc.tasks().insert(tasklist=tasklist_id, body=body).execute()
    return f"Created task: {task.get('title', '')} (id: {task['id']})"


def complete_task(task_id: str, tasklist_id: str = "@default", token_file=None) -> str:
    """Mark a task as completed."""
    svc = _service(token_file)
    task = svc.tasks().get(tasklist=tasklist_id, task=task_id).execute()
    task["status"] = "completed"
    svc.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()
    return f"Completed task: {task.get('title', '')}"


def delete_task(task_id: str, tasklist_id: str = "@default", token_file=None) -> str:
    """Delete a task."""
    svc = _service(token_file)
    svc.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
    return f"Deleted task {task_id}"
