"""talon-tools CLI — interactive setup for tool onboarding.

Usage:
    talon-tools setup              # interactive tool picker
    talon-tools setup google       # onboard a specific tool
    talon-tools setup --status     # show what's configured
"""

from __future__ import annotations

import truststore
truststore.inject_into_ssl()

import argparse
import os
import subprocess
import sys
import time
from getpass import getpass
from pathlib import Path

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep, check_credential
from talon_tools.onboarding.registry import get_all_onboardings
from talon_tools.credentials import set_credential


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if sys.platform == "win32":
        return os.environ.get("TERM") == "xterm" or "WT_SESSION" in os.environ
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if _supports_color():
        return f"{code}{text}{_RESET}"
    return text


def _icon(ok: bool) -> str:
    return _c(_GREEN, "✓") if ok else _c(_RED, "✗")


def _header(text: str) -> None:
    print(f"\n{_c(_BOLD, text)}")
    print("─" * min(len(text) + 4, 60))


# ---------------------------------------------------------------------------
# Status command
# ---------------------------------------------------------------------------

def _show_status() -> None:
    """Show setup status for all tools."""
    registry = get_all_onboardings()
    _header("Tool Setup Status")

    by_type: dict[str, list[tuple[str, ToolOnboarding]]] = {}
    for name, ob in registry.items():
        by_type.setdefault(ob.setup_type, []).append((name, ob))

    type_labels = {
        "zero": "Zero-config (ready to use)",
        "manual": "Manual setup (API keys/tokens)",
        "oauth": "OAuth (browser authorization)",
        "qr": "QR/Link pairing",
    }

    for setup_type in ["zero", "manual", "oauth", "qr"]:
        tools = by_type.get(setup_type, [])
        if not tools:
            continue
        print(f"\n  {_c(_DIM, type_labels.get(setup_type, setup_type))}")
        for name, ob in tools:
            configured = ob.is_configured()
            status = _icon(configured)
            label = f"{ob.display_name} ({name})"
            print(f"    {status} {label}")


# ---------------------------------------------------------------------------
# Interactive picker
# ---------------------------------------------------------------------------

def _pick_tool(registry: dict[str, ToolOnboarding]) -> str | None:
    """Interactive tool selection. Returns tool name or None."""
    # Filter out zero-config tools
    configurable = {
        k: v for k, v in registry.items() if v.setup_type != "zero"
    }

    if not configurable:
        print("All tools are zero-config. Nothing to set up!")
        return None

    _header("Setup")
    items = list(configurable.items())

    # Group by category
    channels = [(name, ob) for name, ob in items if ob.category == "channel"]
    tools = [(name, ob) for name, ob in items if ob.category != "channel"]

    idx = 1
    numbered: list[tuple[str, ToolOnboarding]] = []

    if tools:
        print(f"\n  {_c(_DIM, 'Tools')}")
        for name, ob in tools:
            type_tag = _c(_DIM, f"[{ob.setup_type}]")
            print(f"  {idx:>2}. {ob.display_name} {type_tag}")
            numbered.append((name, ob))
            idx += 1

    if channels:
        print(f"\n  {_c(_DIM, 'Channels')}")
        for name, ob in channels:
            type_tag = _c(_DIM, f"[{ob.setup_type}]")
            print(f"  {idx:>2}. {ob.display_name} {type_tag}")
            numbered.append((name, ob))
            idx += 1

    print()
    while True:
        choice = input(f"Pick an item to set up (1-{len(numbered)}) or 'q' to quit: ").strip()
        if choice.lower() in ("q", "quit", "exit"):
            return None
        try:
            i = int(choice) - 1
            if 0 <= i < len(numbered):
                return numbered[i][0]
        except ValueError:
            # Try matching by name
            if choice.lower() in configurable:
                return choice.lower()
        print("  Invalid choice. Try again.")


# ---------------------------------------------------------------------------
# Auto-detect helpers
# ---------------------------------------------------------------------------

def _auto_detect_telegram_chat_id() -> str | None:
    """Call Telegram getUpdates to auto-detect the user's chat_id."""
    import urllib.request
    import json as _json

    from talon_tools.credentials import get as cred_get
    token = cred_get("TELEGRAM_TOKEN")
    if not token:
        return None

    print("    Send any message to your bot in Telegram, then press Enter here.")
    input("    Press Enter when you've sent a message... ")

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "talon-tools/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        if data.get("ok") and data.get("result"):
            last_update = data["result"][-1]
            message = last_update.get("message", {})
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            chat_name = (
                chat.get("first_name", "")
                + (" " + chat.get("last_name", "") if chat.get("last_name") else "")
            ).strip() or chat.get("username", "")
            if chat_id:
                print(f"    Detected: {chat_name} (chat_id: {chat_id})")
                return str(chat_id)
        print("    No messages found. Make sure you sent a message to the bot.")
    except Exception as e:
        print(f"    Auto-detect failed: {e}")
        print()
        print("    To get your chat_id manually:")
        print(f"    1. Open this URL in your browser:")
        print(f"       https://api.telegram.org/bot{token}/getUpdates")
        print(f'    2. Look for "chat":{{"id":YOUR_CHAT_ID, ...}} in the JSON')
        print(f"    3. Copy the numeric id value")
        print()
    return None


# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

def _run_step(step: OnboardingStep, ob: ToolOnboarding) -> bool:
    """Run a single onboarding step. Returns True if completed."""
    print(f"\n  {_c(_CYAN, f'Step: {step.title}')}")
    print()
    # Indent instruction
    for line in step.instruction.splitlines():
        print(f"    {line}")
    print()

    # Command-based step (QR pairing, etc.)
    if step.is_command and step.command:
        proceed = input("  Run this command now? [Y/n] ").strip().lower()
        if proceed in ("n", "no"):
            if not step.credential_key:
                print("  Skipped.")
                return False
            # Fall through to manual entry below
        else:
            success = _run_command_step(step)
            if success:
                return True
            if not step.credential_key:
                return False
            print("    Falling back to manual entry.")
        # Fall through to credential_key prompt

    # OAuth step — run the handler automatically (takes priority over credential_key)
    if step.oauth_handler:
        proceed = input("  Run OAuth flow now? (opens browser) [Y/n] ").strip().lower()
        if proceed in ("n", "no"):
            if not step.credential_key:
                print("  Skipped.")
                return False
            # Fall through to manual entry below
        else:
            try:
                step.oauth_handler()
                print(f"    {_icon(True)} Authorization complete.")
                return True
            except Exception as e:
                print(f"    {_icon(False)} Automation failed: {e}")
                if not step.credential_key:
                    return False
                print("    Falling back to manual entry.")
        # Fall through to credential_key prompt

    # Credential-based step
    if step.credential_key:
        if check_credential(step.credential_key):
            print(f"    {_icon(True)} {step.credential_key} is already set.")
            reenter = input("    Re-enter? [y/N] ").strip().lower()
            if reenter not in ("y", "yes"):
                return True

        # Auto-detect: TELEGRAM_CHAT_ID
        if step.credential_key == "TELEGRAM_CHAT_ID":
            auto = input("    Auto-detect chat_id? [Y/n] ").strip().lower()
            if auto not in ("n", "no"):
                chat_id = _auto_detect_telegram_chat_id()
                if chat_id:
                    confirm = input(f"    Use {chat_id}? [Y/n] ").strip().lower()
                    if confirm not in ("n", "no"):
                        set_credential(step.credential_key, chat_id)
                        print(f"    {_icon(True)} Saved.")
                        return True
                print("    Falling back to manual entry.")

        # Prompt for the value — use input() so paste works on Windows.
        # getpass() blocks paste in many Windows terminals (msvcrt).
        value = input(f"    Enter {step.credential_key}: ").strip()

        if not value:
            print("    Skipped (empty value).")
            return False

        set_credential(step.credential_key, value)
        print(f"    {_icon(True)} Saved.")
        return True

    # URL/OAuth step — informational only
    if step.is_url:
        input("    Press Enter when done...")
        return True

    # Informational step (no credential_key, no command)
    input("    Press Enter when done...")
    return True


def _resolve_signal_cli() -> str:
    """Find signal-cli binary: Talon-managed location or system PATH."""
    import shutil
    talon_dir = Path.home() / ".config" / "talon" / "signal-cli"
    for name in ["bin/signal-cli.bat", "bin/signal-cli"]:
        candidate = talon_dir / name
        if candidate.exists():
            return str(candidate)
    system = shutil.which("signal-cli")
    if system:
        return system
    return "signal-cli"  # let it fail with FileNotFoundError


def _run_command_step(step: OnboardingStep) -> bool:
    """Run a subprocess command and wait for completion."""
    cmd = list(step.command) if step.command else []
    if not cmd:
        return False

    # Resolve signal-cli from Talon-managed location if not on system PATH
    if cmd[0] == "signal-cli":
        cmd[0] = _resolve_signal_cli()

    print(f"    Running: {' '.join(cmd)}")
    print()
    try:
        result = subprocess.run(cmd, timeout=300)
        if result.returncode == 0:
            print(f"\n    {_icon(True)} Done.")
            return True
        else:
            print(f"\n    {_icon(False)} Command exited with code {result.returncode}.")
            return False
    except FileNotFoundError:
        print(f"\n    {_icon(False)} Command not found: {cmd[0]}")
        print(f"    Make sure it's installed and on your PATH.")
        return False
    except subprocess.TimeoutExpired:
        print(f"\n    {_icon(False)} Command timed out.")
        return False
    except KeyboardInterrupt:
        print(f"\n    Interrupted.")
        return False


# ---------------------------------------------------------------------------
# Dependency installation
# ---------------------------------------------------------------------------

def _install_dependencies(deps: list[str]) -> bool:
    """Check and install required dependencies. Returns True if all satisfied."""
    from talon_tools.onboarding.installer import get_dependency, is_installed, install_dependency

    print(f"\n  {_c(_CYAN, 'Checking dependencies...')}")
    all_ok = True

    for dep_name in deps:
        dep = get_dependency(dep_name)
        if not dep:
            # Unknown dependency — just check if binary exists
            if is_installed(dep_name):
                print(f"    {_icon(True)} {dep_name}")
            else:
                print(f"    {_icon(False)} {dep_name} not found on PATH.")
                all_ok = False
            continue

        if is_installed(dep_name):
            from talon_tools.onboarding.installer import get_version
            version = get_version(dep.version_command) if dep.version_command else None
            ver_str = f" ({version})" if version else ""
            print(f"    {_icon(True)} {dep.display_name}{ver_str}")
        else:
            print(f"    {_icon(False)} {dep.display_name} not found.")
            print()
            proceed = input(f"    Install {dep.display_name}? [Y/n] ").strip().lower()
            if proceed in ("n", "no"):
                all_ok = False
                continue
            if not install_dependency(dep):
                all_ok = False

    return all_ok


def _install_pip_extras(packages: list[str]) -> None:
    """Install Python packages needed for onboarding (e.g. browser-cookie3)."""
    # Check which packages are already importable
    missing: list[str] = []
    for pkg in packages:
        # Normalize: package name for import (e.g. "browser-cookie3" → "browser_cookie3")
        import_name = pkg.replace("-", "_").split(">=")[0].split("<")[0].split("==")[0]
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return

    print(f"\n  {_c(_CYAN, 'Installing dependencies: ' + ', '.join(missing))}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print(f"    {_icon(True)} Installed {', '.join(missing)}")
        else:
            print(f"    {_icon(False)} Failed to install {', '.join(missing)}")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[:5]:
                    print(f"      {line}")
    except Exception as e:
        print(f"    {_icon(False)} pip install failed: {e}")


# ---------------------------------------------------------------------------
# Onboard a specific tool
# ---------------------------------------------------------------------------

def _onboard_tool(name: str, registry: dict[str, ToolOnboarding]) -> None:
    """Walk through all steps for a specific tool."""
    ob = registry.get(name)
    if not ob:
        available = ", ".join(sorted(registry.keys()))
        print(f"Unknown tool: {name}")
        print(f"Available: {available}")
        sys.exit(1)

    if ob.setup_type == "zero":
        print(f"\n  {_icon(True)} {ob.display_name} requires no setup. Ready to use!")
        return

    _header(f"Setting up {ob.display_name}")

    if ob.is_configured():
        print(f"  {_icon(True)} Already configured.")
        redo = input("  Re-run setup anyway? [y/N] ").strip().lower()
        if redo not in ("y", "yes"):
            return

    # Install dependencies first
    if ob.dependencies:
        if not _install_dependencies(ob.dependencies):
            skip = input(f"\n  Continue without dependencies? [y/N] ").strip().lower()
            if skip not in ("y", "yes"):
                return

    # Install pip extras (Python packages needed by this tool)
    if ob.pip_extras:
        _install_pip_extras(ob.pip_extras)

    for i, step in enumerate(ob.steps, 1):
        total = len(ob.steps)
        print(f"\n  {_c(_DIM, f'[{i}/{total}]')}")
        _run_step(step, ob)

    # Verification
    if ob.verify:
        print(f"\n  Verifying connection...")
        try:
            result = ob.verify()
            print(f"  {_icon(True)} {result}")
        except Exception as e:
            print(f"  {_icon(False)} Verification failed: {e}")
    else:
        if ob.is_configured():
            print(f"\n  {_icon(True)} Setup complete!")
        else:
            print(f"\n  {_c(_YELLOW, '⚠')} Some steps may still be incomplete.")


# ---------------------------------------------------------------------------
# Credential persistence helpers
# ---------------------------------------------------------------------------

def _init_credentials(creds_path: str | None = None) -> None:
    """Initialize credentials storage.

    Args:
        creds_path: Explicit path to creds file. Format auto-detected from extension.
                    If None, checks for existing files or prompts the user.
    """
    from talon_tools.credentials import configure_storage

    if creds_path:
        # User specified a path — use it directly
        configure_storage(creds_path)
        print(f"  Using credentials file: {creds_path}")
        return

    # Auto-discover existing files
    env_path = Path.cwd() / ".env"
    yaml_candidates = [
        Path.cwd() / "credentials.yaml",
        Path.home() / ".config" / "talon-tools" / "credentials.yaml",
        Path.home() / ".config" / "talon" / "credentials.yaml",
    ]

    existing_env = env_path.exists()
    existing_yaml = next((p for p in yaml_candidates if p.exists()), None)

    # If an existing file is found, use it but inform the user
    if existing_env:
        configure_storage("env", path=str(env_path))
        print(f"  Using credentials: {env_path}")
        return
    if existing_yaml:
        configure_storage("yaml", path=str(existing_yaml))
        print(f"  Using credentials: {existing_yaml}")
        return

    # No existing file — ask the user where to store credentials
    _header("Credential Storage")
    print("  Where should credentials be saved?\n")
    print(f"  1. {_c(_CYAN, '.env')} file (recommended, dotenv format)")
    print(f"  2. {_c(_CYAN, 'credentials.yaml')} file (YAML format)")
    print(f"  3. Custom path")
    print()

    choice = input("  Choice [1]: ").strip() or "1"

    if choice == "2":
        path = Path.cwd() / "credentials.yaml"
        configure_storage("yaml", path=str(path))
        print(f"  → Credentials will be saved to: {path}")
    elif choice == "3":
        custom = input("  Enter path: ").strip()
        if not custom:
            custom = str(env_path)
        configure_storage(custom)
        print(f"  → Credentials will be saved to: {custom}")
    else:
        configure_storage("env", path=str(env_path))
        print(f"  → Credentials will be saved to: {env_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="talon-tools",
        description="talon-tools — setup and manage tool integrations",
    )
    subparsers = parser.add_subparsers(dest="command")

    # setup command
    setup_parser = subparsers.add_parser("setup", help="Set up tool integrations")
    setup_parser.add_argument("tool", nargs="?", help="Tool name to set up (optional)")
    setup_parser.add_argument("--status", action="store_true", help="Show setup status")
    setup_parser.add_argument(
        "--creds", metavar="PATH",
        help="Path to credentials file (.env or .yaml). Default: auto-discover.",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "setup":
        # Initialize credential storage
        _init_credentials(getattr(args, 'creds', None))

        registry = get_all_onboardings()

        if args.status:
            _show_status()
        elif args.tool:
            _onboard_tool(args.tool, registry)
        else:
            tool = _pick_tool(registry)
            if tool:
                _onboard_tool(tool, registry)


if __name__ == "__main__":
    main()
