"""FastAPI backend for local Qwen-Image-2.1 (abliterated) generation.

Talks to stable-diffusion.cpp's `sd-server` (native /sdcpp/v1 API), persists results to `outputs/`,
and serves the built React frontend when `frontend/dist` exists.
"""
from __future__ import annotations

import asyncio
import collections
import time
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .engine import Engine, EngineRequestError, EngineUnavailable
from .store import Store

RGBA_PREFIX = "This is an RGBA image with transparency. "
RGBA_SUFFIX = " The image has alpha channel and the background is transparent."

# Aspect ratios from the Qwen-Image-2.1 model card, at the native 2K size and at a ~1MP size
# (all dimensions divisible by 32, as sd.cpp requires).
SIZE_PRESETS = [
    {"label": "1:1", "width": 1024, "height": 1024, "tier": "1K"},
    {"label": "4:3", "width": 1184, "height": 896, "tier": "1K"},
    {"label": "3:4", "width": 896, "height": 1184, "tier": "1K"},
    {"label": "3:2", "width": 1248, "height": 832, "tier": "1K"},
    {"label": "2:3", "width": 832, "height": 1248, "tier": "1K"},
    {"label": "16:9", "width": 1344, "height": 768, "tier": "1K"},
    {"label": "9:16", "width": 768, "height": 1344, "tier": "1K"},
    {"label": "1:1", "width": 2048, "height": 2048, "tier": "2K"},
    {"label": "4:3", "width": 2400, "height": 1792, "tier": "2K"},
    {"label": "3:4", "width": 1792, "height": 2400, "tier": "2K"},
    {"label": "3:2", "width": 2528, "height": 1696, "tier": "2K"},
    {"label": "2:3", "width": 1696, "height": 2528, "tier": "2K"},
    {"label": "16:9", "width": 2752, "height": 1536, "tier": "2K"},
    {"label": "9:16", "width": 1536, "height": 2752, "tier": "2K"},
]


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    negative_prompt: str = ""
    width: int = Field(default=settings.default_width, ge=256, le=4096)
    height: int = Field(default=settings.default_height, ge=256, le=4096)
    steps: int = Field(default=settings.default_steps, ge=1, le=100)
    cfg_scale: float = Field(default=settings.default_cfg, ge=1.0, le=20.0)
    seed: int = -1  # -1 = random
    sampler: str = settings.default_sampler
    scheduler: str | None = None
    batch_count: int = Field(default=1, ge=1, le=4)
    transparent: bool = False
    ref_images: list[str] = Field(default_factory=list, max_length=10)  # data URLs / base64
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    output_format: Literal["png", "jpeg", "webp"] = "png"


class JobRecord(BaseModel):
    job_id: str
    status: str
    created: float
    started: float | None = None
    completed: float | None = None
    queue_position: int = 0
    error: dict[str, Any] | None = None
    images: list[dict[str, Any]] = Field(default_factory=list)
    params: dict[str, Any]


engine = Engine(settings)
store = Store(settings.outputs_dir)
jobs: "collections.OrderedDict[str, JobRecord]" = collections.OrderedDict()
MAX_TRACKED_JOBS = 200


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.engine_autostart:
        await engine.start()
    try:
        yield
    finally:
        await engine.close()


app = FastAPI(title="Qwen-Image-2.1 local", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/outputs", StaticFiles(directory=str(settings.outputs_dir)), name="outputs")


# ------------------------------------------------------------------- helpers
def _bad_engine(exc: Exception) -> HTTPException:
    if isinstance(exc, EngineUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, EngineRequestError):
        return HTTPException(status_code=exc.status if 400 <= exc.status < 600 else 502, detail=str(exc))
    return HTTPException(status_code=502, detail=f"engine error: {exc}")


def _build_engine_body(req: GenerateRequest) -> dict[str, Any]:
    prompt = req.prompt.strip()
    if req.transparent and not prompt.startswith(RGBA_PREFIX.strip()):
        prompt = f"{RGBA_PREFIX}{prompt.rstrip('.')}.{RGBA_SUFFIX}"
    sample_params: dict[str, Any] = {
        "sample_method": req.sampler,
        "sample_steps": req.steps,
        "guidance": {"txt_cfg": req.cfg_scale},
    }
    if req.scheduler:
        sample_params["scheduler"] = req.scheduler
    body: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": req.negative_prompt,
        "width": req.width,
        "height": req.height,
        "seed": req.seed,
        "batch_count": req.batch_count,
        "sample_params": sample_params,
        "output_format": req.output_format,
        "embed_image_metadata": True,
    }
    if req.ref_images:
        body["ref_images"] = req.ref_images
        body["strength"] = req.strength
    return body


def _track(record: JobRecord) -> None:
    jobs[record.job_id] = record
    while len(jobs) > MAX_TRACKED_JOBS:
        jobs.popitem(last=False)


async def _refresh(record: JobRecord) -> JobRecord:
    """Pull the latest state from sd-server; persist images the first time a job completes."""
    if record.status in {"completed", "failed", "cancelled"}:
        return record
    status_code, data = await engine.job(record.job_id)
    if status_code == 410:
        record.status, record.error = "failed", {"code": "gone", "message": "job expired on the engine before it was collected"}
        return record
    if status_code == 404:
        record.status, record.error = "failed", {"code": "not_found", "message": "engine does not know this job (was it restarted?)"}
        return record
    if status_code != 200:
        raise HTTPException(status_code=502, detail=data.get("error", {}).get("message", "engine error"))

    record.status = data.get("status", record.status)
    record.started = data.get("started")
    record.completed = data.get("completed")
    record.queue_position = data.get("queue_position", 0) or 0
    record.error = data.get("error")
    if record.status == "completed" and data.get("result"):
        result = data["result"]
        fmt = result.get("output_format", record.params.get("output_format", "png"))
        images = []
        for img in result.get("images", []):
            seed = img.get("seed")
            if seed is None and record.params.get("seed", -1) >= 0:
                seed = record.params["seed"] + img.get("index", 0)
            images.append(
                store.save(b64=img["b64_json"], fmt=fmt, params=record.params, job_id=record.job_id, index=img.get("index", 0), seed=seed)
            )
        record.images = images
        engine.progress = None
    return record


# -------------------------------------------------------------------- routes
@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "engine": engine.status(), "time": time.time()}


@app.get("/api/config")
async def config() -> dict[str, Any]:
    return {
        "defaults": {
            "width": settings.default_width,
            "height": settings.default_height,
            "steps": settings.default_steps,
            "cfg_scale": settings.default_cfg,
            "sampler": settings.default_sampler,
        },
        "size_presets": SIZE_PRESETS,
        "models": engine.status()["models"],
    }


@app.get("/api/capabilities")
async def capabilities() -> dict[str, Any]:
    try:
        return await engine.capabilities()
    except Exception as exc:  # noqa: BLE001
        raise _bad_engine(exc) from exc


@app.post("/api/generate", status_code=202)
async def generate(req: GenerateRequest) -> JobRecord:
    if req.width % 32 or req.height % 32:
        raise HTTPException(status_code=422, detail="width and height must be divisible by 32")
    body = _build_engine_body(req)
    try:
        submitted = await engine.submit_img_gen(body)
    except Exception as exc:  # noqa: BLE001
        raise _bad_engine(exc) from exc
    params = req.model_dump(exclude={"ref_images"})
    params["ref_image_count"] = len(req.ref_images)
    params["resolved_prompt"] = body["prompt"]
    record = JobRecord(job_id=submitted["id"], status=submitted.get("status", "queued"), created=submitted.get("created", time.time()), params=params)
    _track(record)
    return record


@app.get("/api/jobs")
async def list_jobs() -> list[JobRecord]:
    return list(reversed(jobs.values()))


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> JobRecord:
    record = jobs.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown job")
    try:
        return await _refresh(record)
    except EngineUnavailable as exc:
        raise _bad_engine(exc) from exc


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> JobRecord:
    record = jobs.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown job")
    try:
        status_code, data = await engine.cancel(job_id)
    except Exception as exc:  # noqa: BLE001
        raise _bad_engine(exc) from exc
    if status_code >= 400 and status_code not in (409, 410):
        raise HTTPException(status_code=status_code, detail=data.get("error", {}).get("message", "cancel failed"))
    return await _refresh(record)


@app.get("/api/history")
async def history(limit: int = 60, offset: int = 0) -> dict[str, Any]:
    return store.list(limit=min(max(limit, 1), 500), offset=max(offset, 0))


@app.get("/api/history/{image_id}")
async def history_item(image_id: str) -> dict[str, Any]:
    record = store.get(image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="not found")
    return record


@app.delete("/api/history/{image_id}", status_code=204)
async def delete_history_item(image_id: str) -> None:
    if not store.delete(image_id):
        raise HTTPException(status_code=404, detail="not found")


@app.get("/api/engine/logs")
async def engine_logs(tail: int = 120) -> dict[str, Any]:
    lines = list(engine.logs)[-max(1, min(tail, 400)) :]
    return {"lines": lines, "status": engine.status()}


@app.post("/api/engine/start")
async def engine_start() -> dict[str, Any]:
    await engine.start()
    return engine.status()


@app.post("/api/engine/restart")
async def engine_restart() -> dict[str, Any]:
    await engine.restart()
    return engine.status()


@app.post("/api/engine/stop")
async def engine_stop() -> dict[str, Any]:
    await engine.stop()
    return engine.status()


# ---------------------------------------------------------- built frontend
if settings.frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(settings.frontend_dist / "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        candidate = settings.frontend_dist / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(settings.frontend_dist / "index.html")

else:

    @app.get("/", include_in_schema=False)
    async def index() -> JSONResponse:
        return JSONResponse({"message": "backend running; build the frontend (npm run build) or use the Vite dev server on :5173"})
