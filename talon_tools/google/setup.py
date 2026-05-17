"""
Google Cloud project setup — automates GCP OAuth bootstrap.

Automates the manual GCP setup steps:
    1. Verify gcloud CLI installed
    2. Authenticate with gcloud (or reuse existing session)
    3. Select/create a GCP project
    4. Enable Workspace APIs
    5. Configure OAuth consent screen via REST API
    6. Guide user to create OAuth client + paste credentials
    7. Save client_secret.json locally

Requires: gcloud CLI (https://cloud.google.com/sdk/docs/install)

Usage:
    python -m talon_tools.google.setup
    python -m talon_tools.google.setup --project my-project-id
    python -m talon_tools.google.setup --project my-project-id --login
"""

from __future__ import annotations

import json
import os
import platform
import random
import shutil
import string
import subprocess
import sys
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error


class _SetupCancelled(Exception):
    """Raised when the user presses Ctrl+C or provides empty input to cancel."""


def _prompt(msg: str, allow_empty: bool = True) -> str:
    """Prompt the user for input. Raises _SetupCancelled on Ctrl+C / EOFError."""
    try:
        value = input(msg)
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelled.")
        raise _SetupCancelled()
    return value


# APIs to enable for full Workspace access
WORKSPACE_APIS = [
    ("gmail.googleapis.com", "Gmail"),
    ("calendar-json.googleapis.com", "Google Calendar"),
    ("drive.googleapis.com", "Google Drive"),
    ("docs.googleapis.com", "Google Docs"),
    ("sheets.googleapis.com", "Google Sheets"),
    ("tasks.googleapis.com", "Google Tasks"),
    ("people.googleapis.com", "People (Contacts)"),
    ("photoslibrary.googleapis.com", "Google Photos"),
    ("youtube.googleapis.com", "YouTube"),
    ("keep.googleapis.com", "Google Keep"),
]


def _gcloud_bin() -> str:
    """Return the gcloud executable name (platform-aware)."""
    if platform.system() == "Windows":
        # Try gcloud.cmd first (standard install), fall back to gcloud
        if shutil.which("gcloud.cmd"):
            return "gcloud.cmd"
    return "gcloud"


def _gcloud_env(**overrides: str) -> dict[str, str]:
    """Build env dict for gcloud subprocesses.

    Always sets CLOUDSDK_PYTHON to the running interpreter so gcloud
    doesn't fall back to the Windows Store 'python' shim.
    """
    env = {
        **os.environ,
        "CLOUDSDK_PYTHON": sys.executable,
        "CLOUDSDK_CORE_DISABLE_PROMPTS": "1",
        **overrides,
    }
    return env


def _run_gcloud(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a gcloud command with prompts disabled."""
    cmd = [_gcloud_bin(), *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            env=_gcloud_env(),
        )
    except FileNotFoundError:
        # gcloud not installed — return a synthetic failure
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="gcloud not found")


# ── Step 0: Install gcloud ───────────────────────────────────────

GCLOUD_INSTALL_DIR = Path.home() / ".config" / "talon" / "google-cloud-sdk"

# Download URLs for the standalone archive (no admin needed)
_GCLOUD_URLS = {
    ("Windows", "AMD64"): "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-windows-x86_64.zip",
    ("Windows", "x86_64"): "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-windows-x86_64.zip",
    ("Linux", "x86_64"): "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz",
    ("Linux", "aarch64"): "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-arm.tar.gz",
    ("Darwin", "x86_64"): "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-x86_64.tar.gz",
    ("Darwin", "arm64"): "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-arm.tar.gz",
}


def _get_gcloud_download_url() -> str | None:
    """Get the download URL for the current platform."""
    system = platform.system()
    machine = platform.machine()
    return _GCLOUD_URLS.get((system, machine))


def install_gcloud() -> bool:
    """Download and install gcloud CLI to ~/.config/talon/google-cloud-sdk/.

    Returns True on success. Does NOT require admin/root.
    The binary is added to the current process PATH.
    """
    import io
    import tarfile
    import zipfile

    if check_gcloud_installed():
        print("  ✓ gcloud already installed")
        return True

    url = _get_gcloud_download_url()
    if not url:
        print(f"  ✗ No gcloud download available for {platform.system()} {platform.machine()}")
        print("  Install manually: https://cloud.google.com/sdk/docs/install")
        return False

    print(f"  Downloading Google Cloud SDK...")
    print(f"  (installing to {GCLOUD_INSTALL_DIR})")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "talon-tools"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError) as e:
        print(f"  ✗ Download failed: {e}")
        return False

    # Remove old install if present
    if GCLOUD_INSTALL_DIR.exists():
        shutil.rmtree(GCLOUD_INSTALL_DIR)
    GCLOUD_INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)

    # Extract — archive contains a google-cloud-sdk/ folder
    print("  Extracting...")
    try:
        if url.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                zf.extractall(GCLOUD_INSTALL_DIR.parent)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
                tf.extractall(GCLOUD_INSTALL_DIR.parent)
    except (zipfile.BadZipFile, tarfile.TarError) as e:
        print(f"  ✗ Extraction failed: {e}")
        return False

    if not GCLOUD_INSTALL_DIR.exists():
        print("  ✗ Expected google-cloud-sdk/ directory not found after extraction")
        return False

    # Run the install script (non-interactive, no PATH modification to rc files)
    print("  Running installer...")
    if platform.system() == "Windows":
        install_script = GCLOUD_INSTALL_DIR / "install.bat"
        if install_script.exists():
            subprocess.run(
                [str(install_script), "/S", "/noreporting"],
                cwd=str(GCLOUD_INSTALL_DIR),
                capture_output=True,
            )
    else:
        install_script = GCLOUD_INSTALL_DIR / "install.sh"
        if install_script.exists():
            subprocess.run(
                ["bash", str(install_script), "--quiet", "--path-update=false",
                 "--command-completion=false", "--usage-reporting=false"],
                capture_output=True,
            )

    # Add to PATH for current process
    _add_gcloud_to_path()

    if check_gcloud_installed():
        print(f"  ✓ gcloud installed to {GCLOUD_INSTALL_DIR}")
        return True
    else:
        print("  ✗ Installation completed but gcloud not found on PATH")
        print(f"  Try adding to PATH: {_gcloud_bin_dir()}")
        return False


def _gcloud_bin_dir() -> Path:
    """Return the bin directory of the local gcloud install."""
    return GCLOUD_INSTALL_DIR / "bin"


def _add_gcloud_to_path() -> None:
    """Add local gcloud install to PATH for the current process."""
    import os
    bin_dir = str(_gcloud_bin_dir())
    if bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


# ── Step 1: Check gcloud ────────────────────────────────────────


def check_gcloud_installed() -> bool:
    """Check if gcloud CLI is available (system or local install)."""
    # Check local install first
    _add_gcloud_to_path()
    return shutil.which(_gcloud_bin()) is not None


# ── Step 2: Authentication ───────────────────────────────────────


def get_gcloud_account() -> str | None:
    """Get the active gcloud account email."""
    result = _run_gcloud("config", "get-value", "account")
    if result.returncode != 0:
        return None
    val = result.stdout.strip()
    if not val or val == "(unset)":
        return None
    return val


def gcloud_auth_login() -> bool:
    """Run interactive gcloud auth login (opens browser)."""
    result = subprocess.run(
        [_gcloud_bin(), "auth", "login"],
        env=_gcloud_env(CLOUDSDK_CORE_DISABLE_PROMPTS="0"),
    )
    return result.returncode == 0


# ── Step 3: Project management ───────────────────────────────────


def get_gcloud_project() -> str | None:
    """Get the current gcloud project ID."""
    result = _run_gcloud("config", "get-value", "project")
    if result.returncode != 0:
        return None
    val = result.stdout.strip()
    if not val or val == "(unset)":
        return None
    return val


def list_gcloud_projects() -> list[tuple[str, str]]:
    """List accessible GCP projects. Returns [(project_id, name), ...]."""
    result = _run_gcloud(
        "projects", "list", "--format=value(projectId,name)", "--sort-by=projectId"
    )
    if result.returncode != 0:
        return []
    projects = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if parts and parts[0]:
            proj_id = parts[0]
            name = parts[1] if len(parts) > 1 else ""
            projects.append((proj_id, name))
    return projects


def create_gcloud_project(project_id: str) -> tuple[bool, str]:
    """Create a new GCP project. Returns (success, error_message)."""
    result = _run_gcloud("projects", "create", project_id)
    if result.returncode == 0:
        _run_gcloud("config", "set", "project", project_id)
        return True, ""
    error = result.stderr.strip() or result.stdout.strip()
    return False, error


def set_gcloud_project(project_id: str) -> bool:
    """Set the active gcloud project."""
    result = _run_gcloud("config", "set", "project", project_id)
    return result.returncode == 0


# ── Step 4: Enable APIs ──────────────────────────────────────────


def get_enabled_apis(project_id: str) -> list[str]:
    """Get list of already-enabled API service names."""
    result = _run_gcloud(
        "services", "list", "--enabled", "--project", project_id, "--format=json"
    )
    if result.returncode != 0:
        return []
    try:
        services = json.loads(result.stdout)
        return [
            s.get("config", {}).get("name", "")
            for s in services
            if s.get("config", {}).get("name")
        ]
    except (json.JSONDecodeError, TypeError):
        return []


def enable_api(project_id: str, api_id: str) -> tuple[bool, str]:
    """Enable a single API. Returns (success, error_message)."""
    result = _run_gcloud("services", "enable", api_id, "--project", project_id)
    if result.returncode == 0:
        return True, ""
    return False, result.stderr.strip()


def enable_apis(project_id: str, api_ids: list[str]) -> dict[str, Any]:
    """Enable multiple APIs. Returns summary dict."""
    already = get_enabled_apis(project_id)
    enabled = []
    skipped = []
    failed = []

    for api_id in api_ids:
        if api_id in already:
            skipped.append(api_id)
            continue
        ok, err = enable_api(project_id, api_id)
        if ok:
            enabled.append(api_id)
        else:
            failed.append((api_id, err))

    return {"enabled": enabled, "skipped": skipped, "failed": failed}


# ── Step 5: Consent screen ───────────────────────────────────────


def get_access_token() -> str | None:
    """Get a gcloud access token for REST API calls."""
    result = _run_gcloud("auth", "print-access-token")
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def configure_consent_screen(project_id: str, support_email: str) -> tuple[bool, str]:
    """Configure OAuth consent screen via REST API.

    Creates a brand (consent screen) if one doesn't already exist.
    Returns (success, message).
    """
    token = get_access_token()
    if not token:
        return False, "Could not get access token. Run gcloud auth login first."

    url = f"https://oauth2.googleapis.com/v1/projects/{project_id}/brands"

    # Check if consent screen already exists
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            brands = data.get("brands", [])
            if brands:
                return True, "Consent screen already configured"
    except urllib.error.HTTPError:
        pass  # Not found or no permission — try creating

    # Create consent screen
    body = json.dumps({
        "applicationTitle": "Talon AI Assistant",
        "supportEmail": support_email,
    }).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return True, "Consent screen configured"
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        if "ALREADY_EXISTS" in error_body or "already exists" in error_body:
            return True, "Consent screen already configured"
        # Summarise the error without raw HTML
        if e.code == 404:
            return False, "Consent screen API not available for this project (HTTP 404)"
        # Try to extract a JSON error message, fall back to status code
        try:
            err_json = json.loads(error_body)
            detail = err_json.get("error", {}).get("message", error_body[:200])
        except (json.JSONDecodeError, AttributeError):
            detail = error_body[:200] if not error_body.lstrip().startswith("<") else ""
        msg = f"HTTP {e.code}"
        if detail:
            msg += f": {detail}"
        return False, msg


# ── Step 6–7: Client credentials ─────────────────────────────────


def _google_dir(flock_dir: Path | None, agent_name: str | None = None) -> Path | None:
    """Return the target google/ dir for a flock+agent combination."""
    if not flock_dir:
        return None
    if agent_name:
        return flock_dir / agent_name / "google"
    return flock_dir / "google"


def save_client_credentials(
    client_id: str,
    client_secret: str,
    project_id: str,
    output_path: Path | None = None,
    flock_dir: Path | None = None,
    agent_name: str | None = None,
) -> Path:
    """Save OAuth client credentials as a client_secret JSON file.

    Format matches what Google Cloud Console provides when you download
    the OAuth client JSON — compatible with google-auth-oauthlib.

    Resolution order for output path:
        1. Explicit output_path argument
        2. flock_dir[/agent]/google/credentials.json (per-agent or per-flock)

    flock_dir is required when output_path is not given.
    """
    if output_path:
        path = output_path
    else:
        gdir = _google_dir(flock_dir, agent_name)
        if gdir:
            path = gdir / "credentials.json"
        else:
            raise ValueError(
                "Cannot save credentials without a flock directory.\n"
                "Use --flock to specify the target flock."
            )
    path.parent.mkdir(parents=True, exist_ok=True)

    credentials = {
        "installed": {
            "client_id": client_id,
            "project_id": project_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
        }
    }

    path.write_text(json.dumps(credentials, indent=2))

    # Restrict file permissions on Unix
    if platform.system() != "Windows":
        path.chmod(0o600)

    return path


# ── Existing credential detection ─────────────────────────────────


def _get_token_email(token_path: Path) -> str | None:
    """Read the email from an existing OAuth token file (encrypted or plaintext)."""
    from .credential_store import load_token

    token_json = load_token(token_path)
    if not token_json:
        return None
    try:
        data = json.loads(token_json)
        access_token = data.get("token")
        if access_token:
            req = urllib.request.Request(
                "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    info = json.loads(resp.read())
                    return info.get("email")
            except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                pass
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _check_existing_credentials(
    flock_dir: Path | None,
    agent_name: str | None = None,
) -> tuple[bool, str | None]:
    """Check if a flock/agent already has Google credentials configured.

    Returns (has_creds, email_or_none).
    """
    gdir = _google_dir(flock_dir, agent_name)
    if not gdir:
        return False, None
    creds_path = gdir / "credentials.json"
    token_path = gdir / "token.json"
    if not creds_path.exists():
        return False, None
    email = _get_token_email(token_path)
    return True, email


# ── Full setup orchestrator ──────────────────────────────────────────────


def run_setup(
    project: str | None = None,
    output_path: Path | None = None,
    flock_dir: Path | None = None,
    login_after: bool = False,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """Run the full interactive setup flow.

    Args:
        project: Specific GCP project ID to use (skips project selection).
        output_path: Explicit path to save client credentials JSON.
        flock_dir: Flock root directory (e.g. /path/to/my-flock).
                   Credentials saved to <flock_dir>[/<agent>]/google/credentials.json
                   and token to <flock_dir>[/<agent>]/google/token.json.
        login_after: If True, runs OAuth login flow after setup.
        agent_name: Agent name for per-agent credential isolation.

    Returns:
        Summary dict with status and details.
    """
    scope = f"agent '{agent_name}'" if agent_name else "flock" if flock_dir else "global"
    print(f"\n🔧 Talon Google Setup ({scope})")
    print("=" * 50)
    print("  (Press Ctrl+C at any prompt to cancel)\n")

    try:
        return _run_setup_steps(project, output_path, flock_dir, login_after, agent_name)
    except _SetupCancelled:
        return {"status": "cancelled", "error": "Setup cancelled by user"}


def _run_setup_steps(
    project: str | None,
    output_path: Path | None,
    flock_dir: Path | None,
    login_after: bool,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """Inner setup logic — separated so _SetupCancelled bubbles cleanly."""
    scope_label = f"agent '{agent_name}'" if agent_name else "this flock"

    # Step 0: Check for existing credentials
    has_creds, existing_email = _check_existing_credentials(flock_dir, agent_name)
    if has_creds:
        if existing_email:
            print(f"\n  {scope_label.capitalize()} is already authorised as {existing_email}")
        else:
            print(f"\n  {scope_label.capitalize()} already has Google credentials configured.")
        choice = _prompt("  Re-authorise or change account? [y/N]: ").strip().lower()
        if choice not in ("y", "yes"):
            print("  Keeping existing credentials.")
            return {"status": "skipped", "reason": "existing credentials kept"}

    # Step 1: Check gcloud
    print("\n[1/6] Checking for gcloud CLI...")
    if not check_gcloud_installed():
        print("  gcloud not found — installing...")
        if not install_gcloud():
            return {"status": "error", "error": "gcloud CLI not found and installation failed"}
    print("  ✓ gcloud CLI found")

    # Step 2: Authentication
    print("\n[2/6] Checking authentication...")
    account = get_gcloud_account()
    if account:
        print(f"  Logged in as {account}")
        choice = _prompt("  Use this account? [Y/n]: ").strip().lower()
        print(f"  [DEBUG] User chose: '{choice}'", flush=True)
        if choice in ("n", "no"):
            print("  → Opening browser for gcloud auth login...", flush=True)
            print(f"  [DEBUG] gcloud bin: {_gcloud_bin()}", flush=True)
            if not gcloud_auth_login():
                return {"status": "error", "error": "gcloud auth login failed"}
            account = get_gcloud_account()
            if not account:
                return {"status": "error", "error": "No active account after login"}
    else:
        print("  → Not logged in. Opening browser for gcloud auth login...")
        if not gcloud_auth_login():
            return {"status": "error", "error": "gcloud auth login failed"}
        account = get_gcloud_account()
        if not account:
            return {"status": "error", "error": "No active account after login"}
    print(f"  ✓ Authenticated as {account}")

    # Step 3: Project
    print("\n[3/6] Setting up GCP project...")
    if project:
        project_id = project
        set_gcloud_project(project_id)
        print(f"  ✓ Using project: {project_id}")
    else:
        project_id = _auto_create_or_select_project()
        if not project_id:
            return {"status": "error", "error": "No project selected"}
        print(f"  ✓ Project: {project_id}")

    # Step 4: Enable APIs
    print("\n[4/6] Enabling Workspace APIs...")
    selected = _interactive_api_picker(WORKSPACE_APIS)
    if selected is None:
        raise _SetupCancelled()
    if not selected:
        return {"status": "error", "error": "No APIs selected"}
    api_ids = [api_id for api_id, _ in selected]
    result = enable_apis(project_id, api_ids)
    n_enabled = len(result["enabled"])
    n_skipped = len(result["skipped"])
    n_failed = len(result["failed"])
    print(f"  ✓ {n_enabled} enabled, {n_skipped} already active", end="")
    if n_failed:
        print(f", {n_failed} failed")
        for api_id, err in result["failed"]:
            print(f"    ⚠ {api_id}: {err}")
    else:
        print()

    # Step 5: Consent screen
    print("\n[5/6] Configuring OAuth consent screen...")
    ok, msg = configure_consent_screen(project_id, account)
    if ok:
        print(f"  ✓ {msg}")
    else:
        print(f"  ⚠ {msg}")
        print("  Please configure the consent screen manually:")
        print(f"  https://console.cloud.google.com/auth/overview?project={project_id}")
        print("  → Click 'Get Started', select Audience: External, then follow the prompts.")

    # Step 6: OAuth client credentials
    print("\n[6/6] OAuth client credentials")
    print()
    print("  Step A — Consent screen (if not already configured):")
    print(f"  https://console.cloud.google.com/auth/overview?project={project_id}")
    print("  → Click 'Get Started', select Audience: External, then follow the prompts.")
    print()
    print("  Step B — Add yourself as a test user:")
    print(f"  https://console.cloud.google.com/auth/audience?project={project_id}")
    print("  → Under 'Test users', click 'Add users'")
    print("  → Enter your Gmail address and save")
    print()
    print("  Step C — Create an OAuth client:")
    print(f"  https://console.cloud.google.com/auth/clients?project={project_id}")
    print("  → Click 'Create Client'")
    print("  → Application type: Desktop app")
    print("  → Name: Talon (or any name)")
    print("  → Redirect URI: http://localhost (auto-negotiated; no manual entry needed)")
    print()
    print("  Copy the Client ID and Client Secret from the dialog, then paste them below.")
    print()

    client_id = _prompt("  Client ID: ").strip()
    if not client_id:
        return {"status": "error", "error": "Client ID cannot be empty"}
    client_secret = _prompt("  Client Secret: ").strip()
    if not client_secret:
        return {"status": "error", "error": "Client Secret cannot be empty"}

    creds_path = save_client_credentials(client_id, client_secret, project_id, output_path, flock_dir, agent_name)
    print(f"\n  ✓ Credentials saved to {creds_path}")

    # Determine token path (per-agent or per-flock)
    gdir = _google_dir(flock_dir, agent_name)
    if gdir:
        token_path = gdir / "token.json"
    elif output_path:
        token_path = output_path.parent / "token.json"
    else:
        token_path = None  # auth module uses its own default

    # Step 7: Optional login
    if login_after:
        print("\n🔑 Starting OAuth login flow...")
        _run_oauth_login(creds_path, token_path)
    else:
        do_login = _prompt("\n  Run OAuth login now? [Y/n]: ").strip().lower()
        if do_login in ("", "y", "yes"):
            _run_oauth_login(creds_path, token_path)
        else:
            print(f"\n  To login later, run:")
            print(f"    python -m talon_tools.google.auth")

    print("\n✅ Setup complete!")
    return {
        "status": "success",
        "account": account,
        "project": project_id,
        "credentials_file": str(creds_path),
        "apis_enabled": n_enabled,
        "apis_skipped": n_skipped,
        "apis_failed": n_failed,
    }


# ── Interactive API picker ──────────────────────────────────────────


def _read_key() -> str:
    """Read a single keypress. Returns 'up', 'down', 'space', 'enter', 'a', 'q'."""
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getwch()
        if ch == "\x1b":  # Escape
            return "escape"
        if ch == "\x03":  # Ctrl+C
            return "escape"
        if ch in ("\x00", "\xe0"):  # special key prefix
            ch2 = msvcrt.getwch()
            if ch2 == "H":
                return "up"
            if ch2 == "P":
                return "down"
            return ""
        if ch == " ":
            return "space"
        if ch in ("\r", "\n"):
            return "enter"
        return ch.lower()
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x03":  # Ctrl+C
                return "escape"
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        return "up"
                    if ch3 == "B":
                        return "down"
                return "escape"  # bare Escape
            if ch == " ":
                return "space"
            if ch in ("\r", "\n"):
                return "enter"
            return ch.lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _interactive_api_picker(apis: list[tuple[str, str]]) -> list[tuple[str, str]] | None:
    """Interactive multi-select picker for APIs.

    Arrow keys to move, Space to toggle, A to select/deselect all,
    Enter to confirm, Esc/Ctrl+C to cancel.
    All APIs are selected by default. Returns None if cancelled.
    """
    selected = [True] * len(apis)
    cursor = 0
    header = "  \u2191\u2193 move  Space toggle  A all  Enter confirm  Esc cancel"

    def render():
        # Clear footer line (cursor is on it, no trailing \n)
        sys.stdout.write("\r\033[2K")
        # Move up and clear each item line + header
        for _ in range(len(apis) + 1):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.write(f"{header}\n")
        for i, (_, name) in enumerate(apis):
            marker = "\u2713" if selected[i] else " "
            arrow = "\u25b6" if i == cursor else " "
            sys.stdout.write(f"    {arrow} [{marker}] {name}\n")
        count = sum(selected)
        sys.stdout.write(f"  {count}/{len(apis)} selected")
        sys.stdout.flush()

    # Initial render
    sys.stdout.write(f"{header}\n")
    for i, (_, name) in enumerate(apis):
        marker = "\u2713" if selected[i] else " "
        arrow = "\u25b6" if i == cursor else " "
        sys.stdout.write(f"    {arrow} [{marker}] {name}\n")
    count = sum(selected)
    sys.stdout.write(f"  {count}/{len(apis)} selected")
    sys.stdout.flush()

    while True:
        key = _read_key()
        if key == "up" and cursor > 0:
            cursor -= 1
        elif key == "down" and cursor < len(apis) - 1:
            cursor += 1
        elif key == "space":
            selected[cursor] = not selected[cursor]
        elif key == "a":
            if all(selected):
                selected = [False] * len(apis)
            else:
                selected = [True] * len(apis)
        elif key == "enter":
            sys.stdout.write("\n")
            return [apis[i] for i in range(len(apis)) if selected[i]]
        elif key == "escape":
            sys.stdout.write("\n")
            return None
        render()
        render()


def _generate_project_id() -> str:
    """Generate a random project ID like 'talon-abc12'."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    return f"talon-{suffix}"


def _auto_create_or_select_project() -> str | None:
    """Create a new Talon project by default, or let user pick an existing one."""
    print("  Loading projects...")
    projects = list_gcloud_projects()

    # Show what we're about to do, and list existing projects for power users
    project_id = _generate_project_id()
    print(f"  → Will create new project '{project_id}'")
    if projects:
        print()
        print("  Or use an existing project:")
        for i, (pid, name) in enumerate(projects, 1):
            label = f"    {i}. {pid}"
            if name:
                label += f" ({name})"
            print(label)
        print()
        choice = _prompt(f"  Press Enter to create '{project_id}', or pick [1-{len(projects)}]: ").strip()
        if choice:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(projects):
                    pid = projects[idx][0]
                    set_gcloud_project(pid)
                    return pid
            except ValueError:
                pass
            print("  Invalid selection, creating new project...")
    else:
        print()

    print(f"  Creating project '{project_id}'...")
    ok, err = create_gcloud_project(project_id)
    if ok:
        return project_id
    print(f"  ✗ Failed to create project: {err}")
    return None


def _interactive_project_selection() -> str | None:
    """Interactive project selection/creation (fallback)."""
    projects = list_gcloud_projects()

    if projects:
        print("  Existing projects:")
        for i, (pid, name) in enumerate(projects, 1):
            label = f"    {i}. {pid}"
            if name:
                label += f" ({name})"
            print(label)
        print(f"    {len(projects) + 1}. Create new project")
        print()

        choice = _prompt(f"  Select [1-{len(projects) + 1}]: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(projects):
                pid = projects[idx][0]
                set_gcloud_project(pid)
                return pid
        except ValueError:
            pass

    project_id = _prompt("  Enter new project ID: ").strip()
    if not project_id:
        return None
    ok, err = create_gcloud_project(project_id)
    if ok:
        return project_id
    print(f"  ✗ Failed to create project: {err}")
    return None


def _run_oauth_login(credentials_file: Path, token_file: Path | None = None) -> None:
    """Run the OAuth login flow using the saved credentials."""
    try:
        from talon_tools.google.auth import authorize_interactive
        import os
        os.environ["GOOGLE_CREDENTIALS_FILE"] = str(credentials_file)
        if token_file:
            os.environ["GOOGLE_TOKEN_FILE"] = str(token_file)
        authorize_interactive(token_file=token_file)
    except Exception as e:
        print(f"  ✗ Login failed: {e}")
        print(f"  You can retry with: python -m talon_tools.google.auth")


# ── CLI entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Set up Google Cloud project and OAuth credentials for Talon"
    )
    parser.add_argument(
        "--project",
        help="Use a specific GCP project ID (skip project selection)",
    )
    parser.add_argument(
        "--output",
        help="Path to save client credentials JSON (overrides --flock-dir)",
        type=Path,
    )
    parser.add_argument(
        "--flock-dir",
        help="Flock root directory (e.g. /path/to/my-flock)",
        type=Path,
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Run OAuth login flow after setup (skip prompt)",
    )
    args = parser.parse_args()

    flock_dir = args.flock_dir
    if not flock_dir and not args.output:
        # Auto-detect: use current directory if it looks like a flock
        cwd = Path.cwd()
        if (cwd / "AGENTS.md").exists() or (cwd / "agents").is_dir() or (cwd / "google").is_dir():
            flock_dir = cwd

    result = run_setup(
        project=args.project,
        output_path=args.output,
        flock_dir=flock_dir,
        login_after=args.login,
    )
    if result["status"] != "success":
        sys.exit(1)
