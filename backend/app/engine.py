"""Supervises the stable-diffusion.cpp `sd-server` process and proxies its native async API."""
from __future__ import annotations

import asyncio
import collections
import contextlib
import re
import time
from typing import Any

import httpx

from .config import Settings

# sd.cpp prints sampling progress like:  |==========>       | 12/20 - 3.41s/it
_PROGRESS_RE = re.compile(r"\|\s*(\d+)/(\d+)\s*-\s*([\d.]+)(s/it|it/s)")


class Engine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.proc: asyncio.subprocess.Process | None = None
        self.state: str = "stopped"  # stopped | starting | ready | error
        self.error: str | None = None
        self.started_at: float | None = None
        self.ready_at: float | None = None
        self.logs: collections.deque[str] = collections.deque(maxlen=400)
        self.progress: dict[str, Any] | None = None  # {step, total, rate, unit, at}
        self._log_task: asyncio.Task | None = None
        self._client = httpx.AsyncClient(base_url=settings.engine_url, timeout=httpx.Timeout(30.0, read=120.0))
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "error": self.error,
            "pid": self.proc.pid if self.proc and self.proc.returncode is None else None,
            "started_at": self.started_at,
            "ready_at": self.ready_at,
            "url": self.settings.engine_url,
            "progress": self.progress,
            "models": {
                "diffusion_model": self.settings.diffusion_model.name,
                "text_encoder": self.settings.text_encoder.name,
                "text_encoder_vision": self.settings.text_encoder_vision.name if self.settings.text_encoder_vision else None,
                "vae": self.settings.vae.name,
            },
            "missing_files": self.settings.missing_files(),
        }

    # --------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        async with self._lock:
            if self.proc and self.proc.returncode is None:
                return
            missing = self.settings.missing_files()
            if missing:
                self.state, self.error = "error", "missing files: " + "; ".join(missing)
                return
            # An sd-server may already be running externally on the port: adopt it.
            if await self._probe():
                self.state, self.error, self.ready_at = "ready", None, time.time()
                self.logs.append("[backend] adopted an already-running sd-server")
                return

            self.state, self.error = "starting", None
            self.started_at, self.ready_at = time.time(), None
            args = self.settings.engine_args()
            self.logs.append("[backend] launching: " + " ".join(args))
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(self.settings.engine_binary.parent),
                )
            except OSError as exc:
                self.state, self.error = "error", f"failed to launch sd-server: {exc}"
                return
            self._log_task = asyncio.create_task(self._pump_logs())
            asyncio.create_task(self._wait_ready())

    async def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc and proc.returncode is None:
            proc.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=15)
            if proc.returncode is None:
                proc.kill()
        if self._log_task:
            self._log_task.cancel()
            self._log_task = None
        self.state = "stopped"
        self.progress = None

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def close(self) -> None:
        await self.stop()
        await self._client.aclose()

    async def _pump_logs(self) -> None:
        assert self.proc and self.proc.stdout
        try:
            buf = b""
            while True:
                chunk = await self.proc.stdout.read(4096)
                if not chunk:
                    break
                buf += chunk
                # sd.cpp redraws progress bars with '\r' (no newline), so split on both.
                parts = re.split(rb"[\r\n]", buf)
                buf = parts.pop()  # incomplete tail
                for raw in parts:
                    line = raw.decode("utf-8", "replace").replace("\x1b[K", "").strip()
                    if not line:
                        continue
                    self._ingest_line(line)
        finally:
            if self.proc and self.proc.returncode is not None and self.state != "stopped":
                self.state = "error"
                self.error = f"sd-server exited with code {self.proc.returncode}"
                self.logs.append(f"[backend] {self.error}")

    def _ingest_line(self, line: str) -> None:
        m = _PROGRESS_RE.search(line)
        if m:
            self.progress = {
                "step": int(m.group(1)),
                "total": int(m.group(2)),
                "rate": float(m.group(3)),
                "unit": m.group(4),
                "at": time.time(),
            }
        # progress bars redraw constantly; keep only the latest bar in the log ring
        if "|" in line and "/" in line and self.logs and _is_bar(self.logs[-1]) and _is_bar(line):
            self.logs.pop()
        self.logs.append(line)

    async def _wait_ready(self) -> None:
        deadline = time.time() + self.settings.engine_startup_timeout_s
        while time.time() < deadline:
            if self.proc is None or self.proc.returncode is not None:
                return  # _pump_logs records the failure
            if await self._probe():
                self.state, self.ready_at = "ready", time.time()
                self.logs.append(f"[backend] sd-server ready after {self.ready_at - (self.started_at or self.ready_at):.1f}s")
                return
            await asyncio.sleep(1.0)
        self.state, self.error = "error", "sd-server did not become ready in time"

    async def _probe(self) -> bool:
        try:
            r = await self._client.get("/sdcpp/v1/capabilities", timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    # -------------------------------------------------------------------- api
    def _ensure_ready(self) -> None:
        if self.state != "ready":
            raise EngineUnavailable(f"engine is {self.state}" + (f": {self.error}" if self.error else ""))

    async def capabilities(self) -> dict[str, Any]:
        self._ensure_ready()
        r = await self._client.get("/sdcpp/v1/capabilities")
        r.raise_for_status()
        return r.json()

    async def submit_img_gen(self, body: dict[str, Any]) -> dict[str, Any]:
        self._ensure_ready()
        r = await self._client.post("/sdcpp/v1/img_gen", json=body)
        if r.status_code >= 400:
            raise EngineRequestError(r.status_code, _error_message(r))
        self.progress = None
        return r.json()

    async def job(self, job_id: str) -> tuple[int, dict[str, Any]]:
        self._ensure_ready()
        r = await self._client.get(f"/sdcpp/v1/jobs/{job_id}")
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"error": {"message": r.text}}

    async def cancel(self, job_id: str) -> tuple[int, dict[str, Any]]:
        self._ensure_ready()
        r = await self._client.post(f"/sdcpp/v1/jobs/{job_id}/cancel")
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"error": {"message": r.text}}


def _is_bar(line: str) -> bool:
    return line.startswith("|") and "/" in line


class EngineUnavailable(RuntimeError):
    pass


class EngineRequestError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _error_message(r: httpx.Response) -> str:
    try:
        data = r.json()
    except ValueError:
        return r.text[:500]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        if err:
            return str(err)
    return str(data)[:500]
