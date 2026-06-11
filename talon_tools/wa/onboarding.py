"""WhatsApp onboarding — wacli auth, initial sync, and self-JID discovery."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def _find_wacli() -> str | None:
    """Locate the wacli binary."""
    import os
    custom = os.environ.get("WACLI_PATH")
    if custom and Path(custom).is_file():
        return custom
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "wacli" / "wacli.exe",
            Path(os.environ.get("USERPROFILE", "")) / "scoop" / "shims" / "wacli.exe",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
    else:
        for d in ("~/go/bin", "/usr/local/bin", "~/.local/bin"):
            p = Path(d).expanduser() / "wacli"
            if p.is_file():
                return str(p)
    return shutil.which("wacli")


def _discover_self_jid(flock_dir: Path | None) -> None:
    """
    Briefly run wacli sync with a webhook to capture the user's self-chat JID
    (the @lid anonymous JID WhatsApp uses for 'Message yourself' chats).

    Asks the user to send a message to themselves, captures the Chat JID from
    the first webhook hit, then writes target + user_id into channels.yaml.
    """
    wacli = _find_wacli()
    if not wacli:
        print("  ✗ wacli not found — skipping JID discovery.")
        return

    # Find a free port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    captured_jid: list[str] = []
    server_ready = asyncio.Event() if False else None  # use threading instead

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            self.send_response(200)
            self.end_headers()
            try:
                event = json.loads(body)
                jid = event.get("Chat", "")
                from_me = event.get("FromMe", False)
                if from_me and jid and not captured_jid:
                    captured_jid.append(jid)
            except Exception:
                pass

        def log_message(self, fmt, *args):  # noqa: N802
            pass  # suppress access log

    httpd = HTTPServer(("127.0.0.1", port), _Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    print(f"\n  Starting temporary sync listener on port {port}...")
    proc = subprocess.Popen(
        [wacli, "sync", "--follow", "--webhook", f"http://127.0.0.1:{port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print("\n  ➜  Open WhatsApp on your phone and send ANY message to yourself")
    print('     (the "Saved messages" or "Message yourself" chat).')
    print("     Waiting up to 60 seconds...\n")

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not captured_jid:
        time.sleep(0.5)

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    httpd.shutdown()

    if not captured_jid:
        print("  ⚠  No self-message received. Skipping JID discovery.")
        print("     You can add your JID manually to channels.yaml later.")
        return

    self_jid = captured_jid[0]
    print(f"\n  ✓ Captured self-chat JID: {self_jid}")

    # Also get linked_jid from doctor for user_id
    linked_jid = ""
    try:
        result = subprocess.run(
            [wacli, "doctor", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        linked_jid = data.get("data", {}).get("linked_jid", "")
    except Exception:
        pass

    # Write to channels.yaml
    _write_channels_yaml(flock_dir, self_jid, linked_jid)


def _write_channels_yaml(flock_dir: Path | None, self_jid: str, linked_jid: str) -> None:
    """Write or update the whatsapp section in channels.yaml."""
    import yaml  # type: ignore[import]

    if flock_dir is None:
        print("  ⚠  Could not locate flock directory — please add the JID manually.")
        print(f"     target: {self_jid}")
        if linked_jid:
            print(f"     user_id: {linked_jid}")
        return

    yaml_path = Path(flock_dir) / "channels.yaml"
    if yaml_path.is_file():
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    else:
        data = {}

    channels = data.setdefault("channels", {})
    wa = channels.setdefault("whatsapp", {})

    # Build target: include existing entries + self_jid if not already there
    existing_target = wa.get("target", "") or ""
    existing_parts = [j.strip() for j in str(existing_target).split(",") if j.strip()]
    if self_jid not in existing_parts:
        existing_parts.append(self_jid)
    if linked_jid and linked_jid not in existing_parts:
        existing_parts.append(linked_jid)

    wa["target"] = ",".join(existing_parts)
    wa.setdefault("enabled", True)

    # Set user_id to linked_jid (classic @s.whatsapp.net) for outbound notifications
    if linked_jid and not wa.get("user_id"):
        wa["user_id"] = linked_jid

    yaml_path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    print(f"  ✓ Updated channels.yaml:")
    print(f"      target:  {wa['target']}")
    if wa.get("user_id"):
        print(f"      user_id: {wa['user_id']}")


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="wa",
        display_name="WhatsApp",
        setup_type="qr",
        category="channel",
        dependencies=["wacli"],
        steps=[
            OnboardingStep(
                title="Pair WhatsApp",
                instruction=(
                    "This will show a QR code. Scan it with your WhatsApp app:\n"
                    "  WhatsApp → Settings → Linked Devices → Link a Device"
                ),
                is_command=True,
                command=["wacli", "auth"],
                credential_key=None,
            ),
            OnboardingStep(
                title="Initial sync",
                instruction=(
                    "Run initial message sync to populate the local store.\n"
                    "This may take a minute depending on message history."
                ),
                is_command=True,
                command=["wacli", "sync"],
                credential_key=None,
            ),
            OnboardingStep(
                title="Discover your self-chat JID",
                instruction=(
                    "Talon needs your WhatsApp JID to allow self-chat (messaging yourself).\n"
                    "A temporary listener will start — you'll be asked to send a message to yourself."
                ),
                is_optional=True,
                oauth_handler=_discover_self_jid,
                credential_key=None,
            ),
        ],
    )
