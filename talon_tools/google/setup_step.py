"""Granular, machine-driven Google setup steps for the Talon web UI.

The interactive CLI flow in ``setup.py`` (``run_setup``) drives the user through
project creation, API enablement, the consent screen, and OAuth client creation
via terminal prompts. This module exposes the *same* underlying functions as
discrete, non-interactive sub-commands that emit JSON to stdout, so a GUI (the
Nest web wizard) can drive each step itself and render its own UI.

Contract:
    * Each sub-command writes one or more JSON objects (one per line) to stdout.
    * Human-readable progress from the reused ``setup.py`` helpers is redirected
      to stderr, so stdout stays pure JSON.
    * The final stdout line of every command is a terminal event: either
      ``{"event": "done", ...}`` or ``{"event": "error", "message": ...}``.

Sub-commands:
    status        -> gcloud installed? active account? active project?
    install-gcloud(stream) download + install the standalone gcloud SDK
    gcloud-login  -> run ``gcloud auth login`` (opens a browser, waits)
    projects      -> list accessible GCP projects
    set-project   -> create (--create) or select a project
    enable-apis   -> enable the Workspace APIs (streams per-API progress)
    consent       -> configure the OAuth consent screen (brand) via REST
    save-client   -> persist a client_secret JSON from a pasted client id/secret
                     (reads {"client_id","client_secret"} as JSON from stdin)

Usage:
    python -m talon_tools.google.setup_step status --json
    python -m talon_tools.google.setup_step enable-apis --project-id X --json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from talon_tools.google import setup as gsetup


# The real stdout, captured before any redirect so JSON events never get mixed
# with the human-readable progress printed by the reused setup.py helpers.
_REAL_STDOUT = sys.stdout


def _emit(obj: dict[str, Any]) -> None:
    """Write a single JSON event line to the real stdout and flush."""
    _REAL_STDOUT.write(json.dumps(obj) + "\n")
    _REAL_STDOUT.flush()


@contextlib.contextmanager
def _quiet_human_output():
    """Redirect helper print() output to stderr so stdout stays pure JSON."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


# ── Commands ─────────────────────────────────────────────────────


def cmd_status(_args: argparse.Namespace) -> int:
    with _quiet_human_output():
        gcloud = gsetup.check_gcloud_installed()
        account = None
        project = None
        if gcloud:
            # One `gcloud config list` call returns both account and project,
            # which is ~2x faster than two separate `config get-value` calls
            # (each gcloud invocation bootstraps Python and is slow on Windows).
            result = gsetup._run_gcloud("config", "list", "--format=json")
            if result.returncode == 0:
                try:
                    core = (json.loads(result.stdout) or {}).get("core", {})
                    account = core.get("account") or None
                    project = core.get("project") or None
                except (json.JSONDecodeError, AttributeError):
                    pass
    _emit({
        "event": "done",
        "gcloud": gcloud,
        "account": account,
        "project": project,
    })
    return 0


def cmd_install_gcloud(_args: argparse.Namespace) -> int:
    _emit({"event": "start", "message": "Installing Google Cloud SDK…"})
    with _quiet_human_output():
        ok = gsetup.install_gcloud()
    if ok:
        _emit({"event": "done", "gcloud": True})
        return 0
    _emit({"event": "error", "message": "gcloud installation failed. See server logs."})
    return 1


def cmd_gcloud_login(_args: argparse.Namespace) -> int:
    _emit({"event": "start", "message": "Opening browser for gcloud sign-in…"})

    # Run gcloud auth login in a fully non-interactive way: prompts disabled and
    # stdin closed. The CLI helper (gsetup.gcloud_auth_login) enables prompts and
    # inherits stdin, which deadlocks when driven from the web server — after the
    # browser callback gcloud blocks forever on a prompt it can never read.
    import subprocess
    bin_ = gsetup._gcloud_bin()
    env = gsetup._gcloud_env(CLOUDSDK_CORE_DISABLE_PROMPTS="1")
    try:
        result = subprocess.run(
            [bin_, "auth", "login", "--quiet"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        _emit({"event": "error", "message": "Sign-in timed out after 5 minutes. Please try again."})
        return 1
    except FileNotFoundError:
        _emit({"event": "error", "message": "gcloud CLI not found."})
        return 1

    if result.returncode != 0:
        tail = (result.stdout or "").strip()
        tail = tail[-400:] if tail else "gcloud auth login failed."
        _emit({"event": "error", "message": tail})
        return 1

    with _quiet_human_output():
        account = gsetup.get_gcloud_account()
    if not account:
        _emit({"event": "error", "message": "Login completed but no active account was found."})
        return 1
    _emit({"event": "done", "account": account})
    return 0


def cmd_projects(_args: argparse.Namespace) -> int:
    with _quiet_human_output():
        projects = gsetup.list_gcloud_projects()
        current = gsetup.get_gcloud_project()
    _emit({
        "event": "done",
        "projects": [{"id": pid, "name": name} for pid, name in projects],
        "current": current,
    })
    return 0


def cmd_set_project(args: argparse.Namespace) -> int:
    project_id = (args.project_id or "").strip()
    if not project_id:
        _emit({"event": "error", "message": "project-id is required"})
        return 1
    with _quiet_human_output():
        if args.create:
            ok, err = gsetup.create_gcloud_project(project_id)
        else:
            ok = gsetup.set_gcloud_project(project_id)
            err = "" if ok else "Failed to select project"
    if ok:
        _emit({"event": "done", "project": project_id})
        return 0
    _emit({"event": "error", "message": err or "Failed to set project"})
    return 1


def cmd_enable_apis(args: argparse.Namespace) -> int:
    project_id = (args.project_id or "").strip()
    if not project_id:
        _emit({"event": "error", "message": "project-id is required"})
        return 1
    _emit({"event": "start", "total": len(gsetup.WORKSPACE_APIS)})
    with _quiet_human_output():
        already = set(gsetup.get_enabled_apis(project_id))
    n_enabled = n_skipped = n_failed = 0
    for api_id, label in gsetup.WORKSPACE_APIS:
        if api_id in already:
            n_skipped += 1
            _emit({"event": "api", "id": api_id, "label": label, "status": "skipped"})
            continue
        with _quiet_human_output():
            ok, err = gsetup.enable_api(project_id, api_id)
        if ok:
            n_enabled += 1
            _emit({"event": "api", "id": api_id, "label": label, "status": "enabled"})
        else:
            n_failed += 1
            _emit({"event": "api", "id": api_id, "label": label, "status": "failed", "error": err})
    _emit({
        "event": "done",
        "enabled": n_enabled,
        "skipped": n_skipped,
        "failed": n_failed,
    })
    return 0


def cmd_consent(args: argparse.Namespace) -> int:
    project_id = (args.project_id or "").strip()
    account = (args.account or "").strip()
    if not project_id or not account:
        _emit({"event": "error", "message": "project-id and account are required"})
        return 1
    with _quiet_human_output():
        ok, msg = gsetup.configure_consent_screen(project_id, account)
    _emit({
        "event": "done",
        "configured": ok,
        "message": msg,
        "urls": {
            "consent": f"https://console.cloud.google.com/auth/overview?project={project_id}",
            "audience": f"https://console.cloud.google.com/auth/audience?project={project_id}",
            "clients": f"https://console.cloud.google.com/auth/clients?project={project_id}",
        },
    })
    return 0


def cmd_save_client(args: argparse.Namespace) -> int:
    project_id = (args.project_id or "").strip()
    flock_dir = Path(args.flock_dir) if args.flock_dir else None
    agent_name = (args.agent or "").strip() or None
    if not project_id:
        _emit({"event": "error", "message": "project-id is required"})
        return 1
    if not flock_dir:
        _emit({"event": "error", "message": "flock-dir is required"})
        return 1

    # Read the client id/secret as a JSON object from stdin so the secret never
    # appears in the process argument list.
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        _emit({"event": "error", "message": "Invalid JSON payload on stdin"})
        return 1
    client_id = str(payload.get("client_id", "")).strip()
    client_secret = str(payload.get("client_secret", "")).strip()
    if not client_id:
        _emit({"event": "error", "message": "client_id is required"})
        return 1
    if not client_secret:
        _emit({"event": "error", "message": "client_secret is required"})
        return 1

    with _quiet_human_output():
        creds_path = gsetup.save_client_credentials(
            client_id=client_id,
            client_secret=client_secret,
            project_id=project_id,
            output_path=None,
            flock_dir=flock_dir,
            agent_name=agent_name,
        )
    _emit({"event": "done", "credentials_file": str(creds_path)})
    return 0


# ── Entry point ──────────────────────────────────────────────────


_COMMANDS = {
    "status": cmd_status,
    "install-gcloud": cmd_install_gcloud,
    "gcloud-login": cmd_gcloud_login,
    "projects": cmd_projects,
    "set-project": cmd_set_project,
    "enable-apis": cmd_enable_apis,
    "consent": cmd_consent,
    "save-client": cmd_save_client,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m talon_tools.google.setup_step",
        description="Granular, JSON-emitting Google setup steps for the Talon web UI.",
    )
    parser.add_argument("command", choices=sorted(_COMMANDS.keys()))
    parser.add_argument("--json", action="store_true", help="(accepted for symmetry; output is always JSON)")
    parser.add_argument("--project-id", help="GCP project id")
    parser.add_argument("--create", action="store_true", help="Create the project instead of selecting it")
    parser.add_argument("--account", help="Active gcloud account email (for consent screen)")
    parser.add_argument("--flock-dir", help="Flock root directory")
    parser.add_argument("--agent", help="Agent name for per-agent credential isolation")
    args = parser.parse_args(argv)

    handler = _COMMANDS[args.command]
    try:
        return handler(args)
    except Exception as exc:  # noqa: BLE001 — surface any failure as a JSON error event
        _emit({"event": "error", "message": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
