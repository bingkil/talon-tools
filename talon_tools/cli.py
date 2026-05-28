"""talon-tools CLI — interactive setup for tool onboarding.

Usage:
    talon-tools setup              # interactive tool picker
    talon-tools setup google       # onboard a specific tool
    talon-tools setup --status     # show what's configured
    talon-tools tools              # list all modules and their tools
    talon-tools tools google       # list tools in a specific module
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

_SKIP_MODULES = {"onboarding", "providers", "__pycache__", "channels"}


def _discover_tool_modules() -> list[str]:
    """Return sorted list of module names that have a tools.py."""
    pkg_dir = Path(__file__).parent
    modules = []
    for child in sorted(pkg_dir.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if child.name in _SKIP_MODULES:
            continue
        if (child / "tools.py").exists():
            modules.append(child.name)
    return modules


def _load_tools(module_name: str) -> list[tuple[str, str]] | str:
    """Import build_tools() from a module and return [(name, description), ...].

    Returns an error string if the module can't be loaded.
    """
    try:
        import importlib, inspect
        mod = importlib.import_module(f"talon_tools.{module_name}.tools")
        fn = mod.build_tools
        sig = inspect.signature(fn)

        # Build dummy args for required parameters so we can get tool metadata
        dummy_args = {}
        for name, param in sig.parameters.items():
            if param.default is inspect.Parameter.empty and param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                ann = param.annotation
                if ann is Path or (isinstance(ann, str) and "Path" in ann):
                    dummy_args[name] = Path(".")
                elif ann is str or (isinstance(ann, str) and "str" in ann):
                    dummy_args[name] = ""
                else:
                    dummy_args[name] = None

        tools = fn(**dummy_args)
        return [(t.name, t.description) for t in tools]
    except ModuleNotFoundError as e:
        return f"missing package: {e.name}"
    except Exception as e:
        return str(e)


def _load_tools_from_source(module_name: str) -> list[tuple[str, str]]:
    """Extract Tool names from source using AST when import fails."""
    import ast
    src_path = Path(__file__).parent / module_name / "tools.py"
    if not src_path.exists():
        return []
    try:
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
        results: list[tuple[str, str]] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            # Match Tool(...) or _tool(...)
            func = node.func
            is_tool_call = (
                (isinstance(func, ast.Name) and func.id in ("Tool", "_tool"))
                or (isinstance(func, ast.Attribute) and func.attr == "Tool")
            )
            if not is_tool_call:
                continue

            name = ""
            desc = ""

            # Check keyword arg: name="..."
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    name = str(kw.value.value)
                elif kw.arg == "description" and isinstance(kw.value, ast.Constant):
                    desc = str(kw.value.value)

            # Check positional args: _tool("name", "description", ...)
            if not name and node.args:
                if isinstance(node.args[0], ast.Constant):
                    name = str(node.args[0].value)
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    desc = str(node.args[1].value)

            if name:
                results.append((name, desc))

        return results
    except Exception:
        return []


def _module_doc(module_name: str) -> str:
    """Return the first line of a tool module's docstring, or empty string."""
    try:
        import importlib
        mod = importlib.import_module(f"talon_tools.{module_name}.tools")
        doc = (mod.__doc__ or "").strip().split("\n")[0]
        return doc
    except Exception:
        # Fall back to reading the docstring from source
        try:
            import ast
            src = Path(__file__).parent / module_name / "tools.py"
            tree = ast.parse(src.read_text(encoding="utf-8"))
            doc = ast.get_docstring(tree) or ""
            return doc.strip().split("\n")[0]
        except Exception:
            return ""


def _list_tools(module_filter: str | None = None) -> None:
    """List available tools, optionally filtered to a single module."""
    modules = _discover_tool_modules()

    if module_filter:
        if module_filter not in modules:
            print(f"\n  Unknown module: {_c(_RED, module_filter)}")
            print(f"  Available: {', '.join(modules)}")
            sys.exit(1)
        modules = [module_filter]

    _header("Available Tools")

    total = 0
    for mod_name in modules:
        result = _load_tools(mod_name)
        doc = _module_doc(mod_name)

        if isinstance(result, str):
            # Try to get tools from source
            source_tools = _load_tools_from_source(mod_name)
            count = len(source_tools)
            total += count
            count_str = f"{count} tools, " if count else ""
            label = _c(_DIM, f"({count_str}{result})")
            print(f"\n  {_c(_BOLD, mod_name)} {label}")
            if doc:
                print(f"    {_c(_DIM, doc)}")
            for name, desc in source_tools:
                short = desc[:70] + "…" if len(desc) > 70 else desc
                print(f"    {_c(_CYAN, name):40s} {_c(_DIM, short)}")
            continue

        count = len(result)
        total += count
        print(f"\n  {_c(_BOLD, mod_name)} {_c(_DIM, f'({count} tools)')}")
        if doc:
            print(f"    {_c(_DIM, doc)}")
        for name, desc in result:
            # Truncate long descriptions
            short = desc[:70] + "…" if len(desc) > 70 else desc
            print(f"    {_c(_CYAN, name):40s} {short}")

    print(f"\n  {_c(_DIM, f'Total: {total} tools across {len(modules)} modules')}\n")

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

_DEFAULT_CREDS_PATH = Path("~/.talon-tools/credentials.yaml")


def _init_credentials(creds_path: str | None = None) -> None:
    """Initialize credentials storage with a file-backed provider.

    Args:
        creds_path: Explicit path to creds file. Format auto-detected from extension.
                    If None, uses default ~/.talon-tools/credentials.yaml.
    """
    from talon_tools.credentials import init

    resolved = _resolve_creds_path(creds_path)
    existed = resolved.exists()
    provider = _CredStoreProvider(resolved)
    init(provider)

    if existed:
        print(f"  Credentials: {resolved}")
    else:
        print(f"  Credentials: {resolved} (will be created on first save)")


def _resolve_creds_path(creds_path: str | None) -> Path:
    """Resolve which credentials file to use.

    Priority:
        1. Explicit --creds flag
        2. TALON_TOOLS_CREDENTIALS env var
        3. Existing file discovery (CWD .env, CWD credentials.yaml, legacy paths)
        4. Default: ~/.talon-tools/credentials.yaml
    """
    if creds_path:
        return Path(creds_path).expanduser()

    # Check env var
    env_val = os.environ.get("TALON_TOOLS_CREDENTIALS")
    if env_val:
        return Path(env_val).expanduser()

    # Auto-discover existing files (backward compat)
    existing_candidates = [
        Path.cwd() / ".env",
        Path.cwd() / "credentials.yaml",
        Path.home() / ".config" / "talon-tools" / "credentials.yaml",
        Path.home() / ".config" / "talon" / "credentials.yaml",
    ]
    existing = next((p for p in existing_candidates if p.exists()), None)
    if existing:
        return existing

    # Default
    return _DEFAULT_CREDS_PATH.expanduser()


class _CredStoreProvider:
    """Simple file-backed credential provider for the CLI.

    Supports .env (KEY=VALUE) and .yaml formats, with env var fallback.
    """

    def __init__(self, path: Path):
        self._path = path
        self._data: dict[str, str] = {}
        if path.exists():
            if path.suffix in (".yaml", ".yml"):
                self._load_yaml()
            else:
                self._load_env()

    def _load_yaml(self) -> None:
        import yaml
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        self._data = {k: str(v) for k, v in raw.items() if v is not None}

    def _load_env(self) -> None:
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key:
                    self._data[key] = value

    def get(self, key: str, default=None) -> str:
        val = self._data.get(key)
        if val is not None:
            return val
        val = os.environ.get(key)
        if val is not None:
            return val
        if default is not None:
            return default
        raise KeyError(key)

    def keys(self) -> set[str]:
        result = set(self._data.keys())
        result.update(k for k in os.environ if k == k.upper() and "_" in k)
        return result

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self._persist()

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.suffix in (".yaml", ".yml"):
            import yaml
            self._path.write_text(
                yaml.dump(self._data, default_flow_style=False),
                encoding="utf-8",
            )
        else:
            lines = [f"{k}={v}\n" for k, v in sorted(self._data.items())]
            self._path.write_text("".join(lines), encoding="utf-8")


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
        help="Path to credentials file (.env or .yaml). Default: ~/.talon-tools/credentials.yaml",
    )

    # tools command
    tools_parser = subparsers.add_parser("tools", help="List available tools per module")
    tools_parser.add_argument("module", nargs="?", help="Module name to inspect (optional)")

    # mcp command
    mcp_parser = subparsers.add_parser("mcp", help="Start MCP stdio server")
    mcp_parser.add_argument(
        "--tools",
        help="Comma-separated list of modules to load (e.g. atlassian,google,jenkins)",
    )
    mcp_parser.add_argument(
        "--creds", metavar="PATH",
        help="Path to credentials file (.env or .yaml)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "tools":
        _list_tools(getattr(args, "module", None))
    elif args.command == "mcp":
        from talon_tools.mcp_server import main as mcp_main
        mcp_args = []
        if args.tools:
            mcp_args += ["--tools", args.tools]
        if args.creds:
            mcp_args += ["--creds", args.creds]
        sys.argv = ["talon-tools-mcp"] + mcp_args
        mcp_main()
    elif args.command == "setup":
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
