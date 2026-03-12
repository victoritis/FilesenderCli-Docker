#!/usr/bin/env python3.11
"""Wrapper for the WEHI FileSenderCli that reads configuration from
filesender.ini and per-operation flags from config/*.flags.

Requires:
    pip install filesender-client

Usage:
    python3.11 filesender-wehi--config.py upload
    python3.11 filesender-wehi--config.py upload_voucher
    python3.11 filesender-wehi--config.py download
    python3.11 filesender-wehi--config.py invite

Flags file format:
    - Shell-style arguments separated by spaces or newlines
    - Supports single and double quotes
    - Lines starting with # are comments
    - Line continuation with trailing backslash
"""

from __future__ import annotations

import argparse
import configparser
import shlex
import subprocess
import sys
from pathlib import Path


# Modes that require --username and --apikey from the ini file
MODES_WITH_CREDS = {"upload", "invite"}


def _die(msg: str) -> None:
    from rich.console import Console
    from rich.panel import Panel
    Console(stderr=True).print(Panel(msg, title="[red]Configuration error[/red]", border_style="red"))
    raise SystemExit(2)


def _read_flags_file(path: Path) -> list[str]:
    if not path.exists():
        _die(f"Flags file not found: {path}")

    raw = path.read_text(encoding="utf-8")

    logical_lines: list[str] = []
    buf = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
            continue
        buf += stripped
        logical_lines.append(buf)
        buf = ""

    if buf:
        logical_lines.append(buf)

    merged = "\n".join(logical_lines)
    return shlex.split(merged, comments=True, posix=True)


def main() -> int:
    if sys.version_info < (3, 10):
        _die("Python 3.10+ required.")

    api_dir = Path(__file__).resolve().parent
    default_ini = api_dir / "filesender.ini"
    default_config_dir = api_dir / "config"

    parser = argparse.ArgumentParser(
        prog="filesender-wehi--config.py",
        description="Wrapper for WEHI FileSenderCli with flags from config/*.flags",
    )
    parser.add_argument(
        "mode",
        choices=["upload", "upload_voucher", "download", "invite"],
        help="Operation to run (maps to config/<mode>.flags)",
    )
    parser.add_argument(
        "--ini",
        default=str(default_ini),
        help="Path to filesender.ini (default: ./filesender.ini)",
    )
    parser.add_argument(
        "--flags-file",
        help="Override the flags file (default: ./config/<mode>.flags)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved command without executing it",
    )

    ns, extra = parser.parse_known_args()
    if extra[:1] == ["--"]:
        extra = extra[1:]

    # Read ini
    ini_path = Path(ns.ini)
    if not ini_path.exists():
        _die(
            f"Config file not found: {ini_path}\n"
            "Create filesender.ini with base_url, username, and apikey."
        )

    config = configparser.ConfigParser()
    config.read(ini_path)
    base_url = config.get("system", "base_url", fallback=None)
    username = config.get("user", "username", fallback=None)
    apikey   = config.get("user", "apikey",    fallback=None)

    if not base_url:
        _die("Missing base_url in [system] section of the ini file.")

    # WEHI command name (upload_voucher -> upload-voucher)
    wehi_command = ns.mode.replace("_", "-")

    # Read flags file
    if ns.flags_file:
        flags_path = Path(ns.flags_file)
    else:
        flags_path = (default_config_dir / f"{ns.mode}.flags").resolve()

    profile_args = _read_flags_file(flags_path)

    # Build command
    # --base-url is a global option (before the subcommand)
    # --username and --apikey are subcommand options (after the subcommand)
    global_args = ["--base-url", base_url]

    cred_args: list[str] = []
    if wehi_command in MODES_WITH_CREDS:
        if not username or not apikey:
            _die(
                f"Mode '{wehi_command}' requires username and apikey in {ini_path}"
            )
        cred_args = ["--username", username, "--apikey", apikey]

    final_args = profile_args + extra
    cmd = ["filesender"] + global_args + [wehi_command] + cred_args + final_args

    if ns.dry_run:
        print("Resolved command:")
        print("  " + " ".join(shlex.quote(a) for a in cmd))
        print(f"Flags file : {flags_path}")
        print(f"Ini file   : {ini_path}")
        return 0

    completed = subprocess.run(cmd, cwd=str(api_dir))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
