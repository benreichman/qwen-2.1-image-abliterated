"""Runtime configuration, read from environment variables (optionally via backend/.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no extra dependency). Existing env vars win."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(ROOT / "backend" / ".env")


def _env_path(name: str, default: str) -> Path:
    value = os.environ.get(name, default)
    p = Path(value).expanduser()
    return p if p.is_absolute() else ROOT / p


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # --- model files -------------------------------------------------------
    diffusion_model: Path = field(
        default_factory=lambda: _env_path("QI_DIFFUSION_MODEL", "models/diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf")
    )
    text_encoder: Path = field(
        default_factory=lambda: _env_path("QI_TEXT_ENCODER", "models/text_encoders/qwen3vl_8b_heretic-Q4_K_M.gguf")
    )
    text_encoder_vision: Path | None = field(
        default_factory=lambda: _env_path("QI_TEXT_ENCODER_VISION", "models/text_encoders/mmproj-qwen3vl_8b_heretic-f16.gguf")
    )
    vae: Path = field(default_factory=lambda: _env_path("QI_VAE", "models/vae/qwen_image_2.1_vae_bf16.safetensors"))

    # --- engine (stable-diffusion.cpp sd-server) ---------------------------
    engine_binary: Path = field(default_factory=lambda: _env_path("QI_ENGINE_BINARY", "engine/bin/sd-server"))
    engine_host: str = field(default_factory=lambda: os.environ.get("QI_ENGINE_HOST", "127.0.0.1"))
    engine_port: int = field(default_factory=lambda: int(os.environ.get("QI_ENGINE_PORT", "1234")))
    engine_autostart: bool = field(default_factory=lambda: _env_bool("QI_ENGINE_AUTOSTART", True))
    engine_flash_attention: bool = field(default_factory=lambda: _env_bool("QI_ENGINE_FLASH_ATTN", True))
    engine_offload_to_cpu: bool = field(default_factory=lambda: _env_bool("QI_ENGINE_OFFLOAD_TO_CPU", False))
    engine_threads: int = field(default_factory=lambda: int(os.environ.get("QI_ENGINE_THREADS", "-1")))
    engine_extra_args: str = field(default_factory=lambda: os.environ.get("QI_ENGINE_EXTRA_ARGS", ""))
    engine_startup_timeout_s: int = field(default_factory=lambda: int(os.environ.get("QI_ENGINE_STARTUP_TIMEOUT", "900")))

    # --- backend -----------------------------------------------------------
    outputs_dir: Path = field(default_factory=lambda: _env_path("QI_OUTPUTS_DIR", "outputs"))
    frontend_dist: Path = field(default_factory=lambda: _env_path("QI_FRONTEND_DIST", "frontend/dist"))

    # --- generation defaults (Qwen-Image-2.1) -------------------------------
    default_steps: int = 20
    default_cfg: float = 4.0
    default_sampler: str = "euler"
    default_width: int = 1024
    default_height: int = 1024

    @property
    def engine_url(self) -> str:
        return f"http://{self.engine_host}:{self.engine_port}"

    def engine_args(self) -> list[str]:
        args = [
            str(self.engine_binary),
            "--listen-ip", self.engine_host,
            "--listen-port", str(self.engine_port),
            "--diffusion-model", str(self.diffusion_model),
            "--vae", str(self.vae),
            "--llm", str(self.text_encoder),
            "--sampling-method", self.default_sampler,
            "--cfg-scale", str(self.default_cfg),
            "--steps", str(self.default_steps),
            "-W", str(self.default_width),
            "-H", str(self.default_height),
            "--log-level", "info",
        ]
        if self.text_encoder_vision and self.text_encoder_vision.exists():
            args += ["--llm_vision", str(self.text_encoder_vision)]
        if self.engine_flash_attention:
            args.append("--diffusion-fa")
        if self.engine_offload_to_cpu:
            args.append("--offload-to-cpu")
        if self.engine_threads > 0:
            args += ["-t", str(self.engine_threads)]
        if self.engine_extra_args.strip():
            args += self.engine_extra_args.split()
        return args

    def missing_files(self) -> list[str]:
        required = {
            "engine binary": self.engine_binary,
            "diffusion model": self.diffusion_model,
            "text encoder": self.text_encoder,
            "vae": self.vae,
        }
        return [f"{label}: {path}" for label, path in required.items() if not path.exists()]


settings = Settings()
