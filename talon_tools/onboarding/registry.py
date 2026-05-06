"""Tool onboarding registry — discovers onboarding from each tool module."""

from __future__ import annotations

from .base import ToolOnboarding, OnboardingStep


# ---------------------------------------------------------------------------
# Zero-config tools (no setup needed)
# ---------------------------------------------------------------------------

def _zero_config(service: str, display_name: str) -> ToolOnboarding:
    return ToolOnboarding(
        service=service,
        display_name=display_name,
        setup_type="zero",
        steps=[],
    )


# ---------------------------------------------------------------------------
# Channels (no tool module in talon-tools, onboarding lives here)
# ---------------------------------------------------------------------------

def _telegram_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="telegram",
        display_name="Telegram",
        setup_type="manual",
        category="channel",
        steps=[
            OnboardingStep(
                title="Create a Telegram Bot",
                instruction=(
                    "1. Open Telegram and search for @BotFather\n"
                    "2. Send /newbot and follow the prompts\n"
                    "3. Choose a name and username for your bot\n"
                    "4. BotFather will give you an API token"
                ),
                credential_key="TELEGRAM_TOKEN",
            ),
            OnboardingStep(
                title="Get your Chat ID",
                instruction=(
                    "1. Start a conversation with your new bot in Telegram\n"
                    "2. Send any message to it (e.g. 'hi')\n"
                    "3. We'll auto-detect your chat_id from the bot's updates"
                ),
                credential_key="TELEGRAM_CHAT_ID",
                is_optional=True,
            ),
        ],
    )


def _install_signal_cli() -> None:
    """Download and install signal-cli + Java to ~/.config/talon/."""
    import io
    import json
    import platform
    import shutil
    import tarfile
    import urllib.request
    import zipfile
    from pathlib import Path

    talon_dir = Path.home() / ".config" / "talon"
    signal_dir = talon_dir / "signal-cli"
    jre_dir = talon_dir / "jre"

    # --- Java check ---
    def _find_java() -> Path | None:
        """Find Java 21+ (signal-cli 0.13+ needs 21)."""
        # Check Talon-managed JRE
        if jre_dir.exists():
            for java in jre_dir.glob("*/bin/java.exe"):
                return java
            for java in jre_dir.glob("*/bin/java"):
                return java
        # Check system Java
        system = shutil.which("java")
        if system:
            return Path(system)
        return None

    def _install_java() -> None:
        """Download Temurin 21 JRE to ~/.config/talon/jre/."""
        arch = platform.machine().lower()
        if arch in ("x86_64", "amd64"):
            arch = "x64"
        elif arch in ("aarch64", "arm64"):
            arch = "aarch64"

        os_name = "windows" if platform.system() == "Windows" else "linux"
        ext = "zip" if os_name == "windows" else "tar.gz"

        api_url = (
            f"https://api.adoptium.net/v3/binary/latest/21/ga/"
            f"{os_name}/{arch}/jre/hotspot/normal/eclipse"
        )
        print(f"    Downloading Temurin 21 JRE...")
        jre_dir.mkdir(parents=True, exist_ok=True)

        req = urllib.request.Request(api_url, headers={"User-Agent": "talon-tools"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()

        if ext == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                zf.extractall(jre_dir)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
                tf.extractall(jre_dir)

        print(f"    ✓ Java installed to {jre_dir}")

    # --- signal-cli download ---
    def _install_signal_cli_binary() -> None:
        """Download latest signal-cli from GitHub releases."""
        print("    Fetching latest signal-cli release...")
        api_url = "https://api.github.com/repos/AsamK/signal-cli/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "talon-tools"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            release = json.loads(resp.read())

        tag = release["tag_name"]  # e.g. "v0.13.8"
        version = tag.lstrip("v")

        # signal-cli publishes a tar.gz archive
        archive_name = f"signal-cli-{version}.tar.gz"
        asset = next(
            (a for a in release["assets"] if a["name"] == archive_name),
            None,
        )
        if not asset:
            # Fallback: try any tar.gz
            asset = next(
                (a for a in release["assets"] if a["name"].endswith(".tar.gz")),
                None,
            )
        if not asset:
            raise RuntimeError(
                f"Could not find signal-cli archive in release {tag}.\n"
                f"    Download manually: https://github.com/AsamK/signal-cli/releases"
            )

        print(f"    Downloading signal-cli {version}...")
        req = urllib.request.Request(
            asset["browser_download_url"],
            headers={"User-Agent": "talon-tools"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()

        # Remove old install
        if signal_dir.exists():
            shutil.rmtree(signal_dir)

        # Extract — archive contains signal-cli-X.Y.Z/ folder
        signal_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            tf.extractall(talon_dir)

        # Rename extracted folder to signal-cli
        extracted = talon_dir / f"signal-cli-{version}"
        if extracted.exists() and extracted != signal_dir:
            if signal_dir.exists():
                shutil.rmtree(signal_dir)
            extracted.rename(signal_dir)

        # On Windows, create a .bat wrapper if not present
        if platform.system() == "Windows":
            bat = signal_dir / "bin" / "signal-cli.bat"
            if not bat.exists():
                # The tar.gz should include it, but create fallback
                bat.write_text(
                    f'@echo off\n"{_find_java()}" -jar "{signal_dir / "lib" / "signal-cli.jar"}" %*\n'
                )

        print(f"    ✓ signal-cli {version} installed to {signal_dir}")

    # --- Main flow ---
    java = _find_java()
    if not java:
        _install_java()
        java = _find_java()
        if not java:
            raise RuntimeError("Failed to install Java. Please install Java 21+ manually.")

    if not (signal_dir / "bin").exists():
        _install_signal_cli_binary()
    else:
        print(f"    ✓ signal-cli already installed at {signal_dir}")


def _signal_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="signal",
        display_name="Signal",
        setup_type="qr",
        category="channel",
        steps=[
            OnboardingStep(
                title="Install signal-cli and Java",
                instruction=(
                    "signal-cli will be downloaded to ~/.config/talon/signal-cli/\n"
                    "Java (Temurin 21 JRE) will be installed to ~/.config/talon/jre/ if needed.\n"
                    "\n"
                    "This does NOT modify your system PATH or Java installation."
                ),
                oauth_handler=_install_signal_cli,
            ),
            OnboardingStep(
                title="Link Signal as secondary device",
                instruction=(
                    "This will run 'signal-cli link' to generate a QR code.\n"
                    "Scan it with your Signal app:\n"
                    "  Signal → Settings → Linked Devices → Link New Device\n"
                    "\n"
                    "If you prefer, enter your phone number (E.164 format, e.g. +1234567890)."
                ),
                is_command=True,
                command=["signal-cli", "link", "-n", "Talon"],
                credential_key="SIGNAL_ACCOUNT",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def get_all_onboardings() -> dict[str, ToolOnboarding]:
    """Return all tool onboarding definitions.

    Each tool module provides its own `onboarding.py` with a `get_onboarding()`
    function. Channels without a tool module are defined above.
    """
    from talon_tools.atlassian.onboarding import get_onboarding as atlassian
    from talon_tools.notion.onboarding import get_onboarding as notion
    from talon_tools.servicenow.onboarding import get_onboarding as servicenow
    from talon_tools.google.onboarding import get_onboarding as google
    from talon_tools.microsoft.onboarding import get_onboarding as microsoft
    from talon_tools.spotify.onboarding import get_onboarding as spotify
    from talon_tools.x.onboarding import get_onboarding as x
    from talon_tools.facebook.onboarding import get_onboarding as facebook
    from talon_tools.wa.onboarding import get_onboarding as wa

    return {
        # Zero-config
        "search": _zero_config("search", "Web Search (DuckDuckGo)"),
        "terminal": _zero_config("terminal", "Terminal"),
        "workspace": _zero_config("workspace", "Workspace"),
        # Tools (onboarding from each module)
        "atlassian": atlassian(),
        "notion": notion(),
        "servicenow": servicenow(),
        "google": google(),
        "microsoft": microsoft(),
        "spotify": spotify(),
        "x": x(),
        "facebook": facebook(),
        # Channels
        "telegram": _telegram_onboarding(),
        "signal": _signal_onboarding(),
        "wa": wa(),
    }
