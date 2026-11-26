"""Headless Devin CLI wrapper.

Each pipeline agent is one ``devin -p`` (print) invocation with a prompt file,
running with cwd = the run workspace. Agent output is captured to a file and
only sanitized extracts ever reach the workflow log.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import log
from .config import Config

CREDS_PATH = Path(
    os.environ.get("DEVIN_CREDS_PATH")
    or (Path.home() / ".local" / "share" / "devin" / "credentials.toml")
)


class DevinError(Exception):
    pass


def ensure_credentials(cfg: Config) -> None:
    """Materialize credentials.toml from env secrets when provided.

    Priority:
      1. DEVIN_CREDENTIALS_TOML  — full file contents (most faithful)
      2. DEVIN_API_KEY           — windsurf_api_key + default endpoints
      3. pre-existing credentials.toml (local dev / DEVIN_ALLOW_STORED_CREDS)
    """
    if CREDS_PATH.exists() and not (cfg.devin_api_key or cfg.devin_credentials_toml):
        log.emit("devin: using existing credentials.toml")
        return
    if cfg.devin_credentials_toml:
        contents = cfg.devin_credentials_toml
    elif cfg.devin_api_key:
        contents = (
            f'windsurf_api_key = "{cfg.devin_api_key}"\n'
            f'api_server_url = "{cfg.devin_api_server_url}"\n'
            f'devin_webapp_host = "{cfg.devin_webapp_host}"\n'
            f'devin_api_url = "{cfg.devin_api_url}"\n'
        )
    else:
        raise DevinError(
            "no Devin credentials: set DEVIN_API_KEY, DEVIN_CREDENTIALS_TOML, "
            "or DEVIN_ALLOW_STORED_CREDS=1 with an existing credentials.toml"
        )
    CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDS_PATH.write_text(contents)
    CREDS_PATH.chmod(0o600)
    log.emit("devin: credentials.toml written from secret (values never logged)")


class DevinResult:
    def __init__(self, name: str, rc: int, output: str, out_file: Path):
        self.name = name
        self.rc = rc
        self.output = output          # full captured stdout+stderr (kept in memory, never logged raw)
        self.out_file = out_file      # temp file — deleted with the workdir

    @property
    def ok(self) -> bool:
        return self.rc == 0

    def tail(self, n: int = 400) -> str:
        return log.tail(self.output, n)


class DevinRunner:
    def __init__(self, cfg: Config, workdir: Path):
        self.cfg = cfg
        self.workdir = workdir
        self.prompt_dir = workdir / "prompts"
        self.out_dir = workdir / "devin-out"
        self.prompt_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _cmd(self, prompt_file: Path) -> list[str]:
        cmd = [
            self.cfg.devin_bin,
            "-p",
            "--prompt-file", str(prompt_file),
            "--permission-mode", self.cfg.devin_permission_mode,
            "--respect-workspace-trust", "false",
        ]
        if self.cfg.devin_sandbox:
            cmd.append("--sandbox")
        if self.cfg.devin_model:
            cmd += ["--model", self.cfg.devin_model]
        return cmd

    def run(self, name: str, prompt: str, timeout: int | None = None) -> DevinResult:
        """Invoke one headless devin session. Writes prompt+output under workdir."""
        prompt_file = self.prompt_dir / f"{name}.md"
        prompt_file.write_text(prompt)
        out_file = self.out_dir / f"{name}.log"
        cmd = self._cmd(prompt_file)
        log.emit(f"devin: running stage '{name}' (timeout {timeout or self.cfg.devin_timeout_sec}s)")
        # the CLI reads DEVIN_MODEL / DEVIN_PERMISSION_MODE / etc. straight from
        # env — an empty value errors ("Unknown model: ''"), so drop empties
        env = {k: v for k, v in os.environ.items() if v or not k.startswith("DEVIN_")}
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout or self.cfg.devin_timeout_sec,
                env=env,
            )
            output = proc.stdout or ""
            rc = proc.returncode
        except subprocess.TimeoutExpired as e:
            output = (e.stdout or "") if isinstance(e.stdout, str) else ""
            rc = 124
        except FileNotFoundError:
            raise DevinError(f"devin binary not found: {self.cfg.devin_bin}")
        out_file.write_text(output)
        if rc == 0:
            log.emit(f"devin: stage '{name}' finished ({len(output)} chars captured)")
        else:
            log.emit_err(f"devin: stage '{name}' exited rc={rc}; tail: {log.tail(output)}")
        if self.cfg.debug_verbose and output:
            log.emit(f"devin: '{name}' sanitized tail — {log.tail(output, 1200)}")
        return DevinResult(name, rc, output, out_file)
