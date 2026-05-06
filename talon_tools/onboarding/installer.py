"""Dependency installer — auto-installs external binaries needed by tools."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class InstallMethod:
    """A way to install a binary."""
    label: str
    command: list[str]
    check: str  # command to verify it exists after install (e.g. "wacli")


@dataclass
class Dependency:
    """An external binary dependency."""
    name: str  # binary name (e.g. "wacli", "signal-cli")
    display_name: str
    install_methods: list[InstallMethod]  # ordered by preference
    version_command: list[str] | None = None  # e.g. ["wacli", "version"]
    min_version: str | None = None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_installed(binary: str) -> bool:
    """Check if a binary is available (PATH or known managed locations)."""
    if shutil.which(binary):
        return True
    # Check Talon-managed install locations
    if binary == "signal-cli":
        talon_dir = Path.home() / ".config" / "talon" / "signal-cli"
        for name in ["bin/signal-cli.bat", "bin/signal-cli"]:
            if (talon_dir / name).exists():
                return True
    return False


def get_version(cmd: list[str]) -> str | None:
    """Run a version command and return output, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() or result.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _refresh_path() -> None:
    """Refresh the current process PATH from the user/system environment (Windows)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        # Read user PATH
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            user_path, _ = winreg.QueryValueEx(key, "Path")
        # Read system PATH
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as key:
            sys_path, _ = winreg.QueryValueEx(key, "Path")
        os.environ["PATH"] = f"{sys_path};{user_path}"
    except (OSError, FileNotFoundError):
        pass


def _find_in_common_paths(binary: str) -> Path | None:
    """Look for a binary in common install locations."""
    if sys.platform == "win32":
        exe = f"{binary}.exe"
    else:
        exe = binary

    candidates = [
        Path.home() / "AppData" / "Local" / "Programs" / binary / exe,
        Path.home() / "AppData" / "Local" / "Programs" / binary / binary / exe,
        Path.home() / "scoop" / "shims" / exe,
        Path.home() / "go" / "bin" / exe,
        Path.home() / ".local" / "bin" / exe,
        Path("/usr/local/bin") / exe,
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def _available_methods(dep: Dependency) -> list[InstallMethod]:
    """Filter install methods to those that can work on this system."""
    available = []
    for method in dep.install_methods:
        # Check if the installer tool itself exists
        installer = method.command[0]
        if installer in ("go", "brew", "scoop", "winget", "apt", "choco"):
            if shutil.which(installer):
                available.append(method)
        elif installer in ("powershell", "pwsh", "curl", "wget"):
            if shutil.which(installer):
                available.append(method)
        else:
            # Unknown installer — include it (manual fallback)
            available.append(method)
    return available


def install_dependency(dep: Dependency) -> bool:
    """Attempt to install a dependency. Returns True on success."""
    if is_installed(dep.name):
        version = get_version(dep.version_command) if dep.version_command else None
        print(f"    ✓ {dep.display_name} is already installed.", end="")
        if version:
            print(f" ({version})")
        else:
            print()
        return True

    methods = _available_methods(dep)
    if not methods:
        print(f"    ✗ No automatic install method available for {dep.display_name}.")
        if dep.name == "signal-cli":
            print(f"      Please install manually: https://github.com/AsamK/signal-cli/releases")
        elif dep.name == "wacli":
            print(f"      Please install manually: https://github.com/openclaw/wacli/releases")
        else:
            print(f"      Please install '{dep.name}' manually and ensure it's on your PATH.")
        return False

    # If only one method, use it directly
    if len(methods) == 1:
        method = methods[0]
    else:
        # Let user pick
        print(f"    {dep.display_name} is not installed. Available install methods:\n")
        for i, m in enumerate(methods, 1):
            cmd_str = " ".join(m.command)
            print(f"      {i}. {m.label}: {cmd_str}")
        print()
        while True:
            choice = input(f"    Pick method (1-{len(methods)}) or 's' to skip: ").strip()
            if choice.lower() == "s":
                return False
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(methods):
                    method = methods[idx]
                    break
            except ValueError:
                pass
            print("    Invalid choice.")

    # Check if method requires a prerequisite (e.g. "go install" needs Go)
    installer_bin = method.command[0]
    if installer_bin == "go" and not is_installed("go"):
        print(f"\n    Go is required for this install method but is not installed.")
        proceed = input(f"    Install Go first? [Y/n] ").strip().lower()
        if proceed in ("n", "no"):
            return False
        go_dep = go_dependency()
        if not install_dependency(go_dep):
            print(f"    ✗ Cannot install {dep.display_name} without Go.")
            return False
        # Refresh PATH awareness after Go install
        if not is_installed("go"):
            print(f"    ⚠ Go was installed but may require a new terminal session to be on PATH.")
            print(f"      Please restart your terminal and re-run this setup.")
            return False

    # Run the install
    cmd_str = " ".join(method.command)
    print(f"\n    Running: {cmd_str}")
    try:
        result = subprocess.run(method.command, timeout=300)
        if result.returncode == 0:
            # Refresh current process PATH from user environment (Windows)
            _refresh_path()
            if is_installed(dep.name):
                print(f"    ✓ {dep.display_name} installed successfully.")
                return True
            else:
                # Binary exists in known locations but shutil.which can't find it yet
                # Try common install dirs directly
                found = _find_in_common_paths(dep.name)
                if found:
                    # Add to current process PATH
                    os.environ["PATH"] = f"{found.parent}{os.pathsep}{os.environ.get('PATH', '')}"
                    print(f"    ✓ {dep.display_name} installed to {found.parent}")
                    return True
                print(f"    ⚠ Install completed but '{dep.name}' not found on PATH.")
                print(f"      You may need to restart your terminal for PATH changes to take effect.")
                return False
        else:
            print(f"    ✗ Install failed (exit code {result.returncode}).")
            return False
    except FileNotFoundError:
        print(f"    ✗ Command not found: {method.command[0]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"    ✗ Install timed out.")
        return False


# ---------------------------------------------------------------------------
# Dependency definitions
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    return sys.platform == "linux"


def go_dependency() -> Dependency:
    """Go programming language — required for 'go install' commands."""
    methods: list[InstallMethod] = []

    if _is_windows():
        methods.append(InstallMethod(
            label="winget",
            command=["winget", "install", "--id", "GoLang.Go", "--accept-source-agreements", "--accept-package-agreements"],
            check="go",
        ))
        methods.append(InstallMethod(
            label="Scoop",
            command=["scoop", "install", "go"],
            check="go",
        ))

    if _is_macos():
        methods.append(InstallMethod(
            label="Homebrew",
            command=["brew", "install", "go"],
            check="go",
        ))

    if _is_linux():
        methods.append(InstallMethod(
            label="apt",
            command=["sudo", "apt", "install", "-y", "golang"],
            check="go",
        ))

    return Dependency(
        name="go",
        display_name="Go",
        install_methods=methods,
        version_command=["go", "version"],
    )


def wacli_dependency() -> Dependency:
    """wacli — WhatsApp CLI."""
    methods: list[InstallMethod] = []

    if _is_macos():
        methods.append(InstallMethod(
            label="Homebrew (recommended)",
            command=["brew", "install", "steipete/tap/wacli"],
            check="wacli",
        ))

    if _is_windows():
        # Prefer prebuilt binary — go install requires CGO + C compiler
        methods.append(InstallMethod(
            label="Download from GitHub Releases (recommended)",
            command=[
                "powershell", "-NoProfile", "-Command",
                (
                    "$release = Invoke-RestMethod 'https://api.github.com/repos/openclaw/wacli/releases/latest';"
                    "$asset = $release.assets | Where-Object { $_.name -match 'windows.*amd64.*\\.zip$' } | Select-Object -First 1;"
                    "$zip = Join-Path $env:TEMP $asset.name;"
                    "Invoke-WebRequest $asset.browser_download_url -OutFile $zip;"
                    "$dest = Join-Path $env:LOCALAPPDATA 'Programs\\wacli';"
                    "New-Item -ItemType Directory -Force -Path $dest | Out-Null;"
                    "Expand-Archive -Path $zip -DestinationPath $dest -Force;"
                    "Remove-Item $zip;"
                    "$path = [Environment]::GetEnvironmentVariable('Path', 'User');"
                    "if ($path -notlike \"*$dest*\") { [Environment]::SetEnvironmentVariable('Path', \"$path;$dest\", 'User') };"
                    "$env:Path = \"$env:Path;$dest\";"
                    "Write-Host \"Installed to $dest\""
                ),
            ],
            check="wacli",
        ))
        methods.append(InstallMethod(
            label="Scoop",
            command=["scoop", "install", "wacli"],
            check="wacli",
        ))

    if _is_linux():
        # Go install with CGO works on Linux (gcc usually available)
        methods.append(InstallMethod(
            label="Go install (requires gcc)",
            command=["go", "install", "github.com/steipete/wacli/cmd/wacli@latest"],
            check="wacli",
        ))

    if _is_macos():
        # Fallback: go install works on macOS with Xcode CLI tools
        methods.append(InstallMethod(
            label="Go install",
            command=["go", "install", "github.com/steipete/wacli/cmd/wacli@latest"],
            check="wacli",
        ))

    return Dependency(
        name="wacli",
        display_name="wacli (WhatsApp CLI)",
        install_methods=methods,
        version_command=["wacli", "version"],
    )


def signal_cli_dependency() -> Dependency:
    """signal-cli — Signal messenger CLI."""
    methods: list[InstallMethod] = []

    if _is_macos():
        methods.append(InstallMethod(
            label="Homebrew",
            command=["brew", "install", "signal-cli"],
            check="signal-cli",
        ))

    if _is_windows():
        methods.append(InstallMethod(
            label="Scoop",
            command=["scoop", "install", "signal-cli"],
            check="signal-cli",
        ))

    if _is_linux():
        methods.append(InstallMethod(
            label="apt (via third-party PPA)",
            command=["sudo", "apt", "install", "-y", "signal-cli"],
            check="signal-cli",
        ))

    return Dependency(
        name="signal-cli",
        display_name="signal-cli (Signal messenger)",
        install_methods=methods,
        version_command=["signal-cli", "--version"],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DEPENDENCIES: dict[str, Dependency] = {
    "wacli": wacli_dependency(),
    "signal-cli": signal_cli_dependency(),
}


def get_dependency(name: str) -> Dependency | None:
    """Get a dependency definition by binary name."""
    return DEPENDENCIES.get(name)
