#!/usr/bin/env python3
"""Download the model files needed to run Qwen-Image-2.1 (abliterated) locally.

Components (all GGUF/safetensors, loaded by stable-diffusion.cpp):

  * DiT (the image model itself)     -> models/diffusion_models/
  * Text encoder (Heretic-abliterated Qwen3-VL-8B) + vision projector -> models/text_encoders/
  * VAE                                -> models/vae/

Usage:
    python scripts/download_models.py                # defaults (Q4_K_M DiT, uncensored variant)
    python scripts/download_models.py --dit-quant Q6_K
    python scripts/download_models.py --dit base     # stock Qwen-Image-2.1 DiT instead of the UC one
    python scripts/download_models.py --no-vision    # skip mmproj (text-to-image only, no editing)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

# DiT sources. "uc" = abenzerps "Uncensored" GGUFs, "base" = leejet's conversion of the stock weights.
DIT_SOURCES = {
    "uc": {
        "repo": "abenzerps/Qwen-Image-2.1-Uncensored-GGUF",
        "revision": "main",
        "pattern": "qwen-image-2.1-UC-{quant}.gguf",
        "quants": ["Q4_0", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "BF16"],
    },
    "base": {
        "repo": "abenzerps/Qwen-Image-2.1-Uncensored-GGUF",
        "revision": "base",
        "pattern": "qwen-image-2.1-{quant}.gguf",
        "quants": ["Q4_0", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"],
    },
}

TEXT_ENCODER_REPO = "pottokao/Qwen-Image-2.1-Text-Encoder-Heretic-GGUF"
TEXT_ENCODER_FILE = "qwen3vl_8b_heretic-Q4_K_M.gguf"
TEXT_ENCODER_MMPROJ = "mmproj-qwen3vl_8b_heretic-f16.gguf"

VAE_REPO = "abenzerps/Qwen-Image-2.1-Uncensored-GGUF"
VAE_FILE = "vae/qwen_image_2.1_vae_bf16.safetensors"


def fetch(repo: str, filename: str, dest_dir: Path, revision: str = "main") -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / Path(filename).name
    if target.exists() and target.stat().st_size > 0:
        print(f"  [skip] {target.relative_to(ROOT)} already present")
        return target
    print(f"  [get ] {repo}@{revision}:{filename}")
    hf_hub_download(
        repo_id=repo,
        filename=filename,
        revision=revision,
        local_dir=dest_dir / ".hf",  # download into a staging dir, then move flat
    )
    staged = dest_dir / ".hf" / filename
    staged.replace(target)
    print(f"  [done] {target.relative_to(ROOT)} ({target.stat().st_size / 1e9:.2f} GB)")
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dit", choices=DIT_SOURCES.keys(), default="uc", help="DiT variant (default: uc)")
    ap.add_argument("--dit-quant", default="Q4_K_M", help="DiT quantization (default: Q4_K_M)")
    ap.add_argument("--no-vision", action="store_true", help="skip the vision projector (disables image editing)")
    ap.add_argument("--only", choices=["dit", "te", "vae"], help="download a single component")
    args = ap.parse_args()

    src = DIT_SOURCES[args.dit]
    if args.dit_quant not in src["quants"]:
        print(f"unknown quant {args.dit_quant!r}; choose from {src['quants']}", file=sys.stderr)
        return 2

    print(f"Downloading into {MODELS}\n")
    if args.only in (None, "dit"):
        print("DiT:")
        fetch(src["repo"], src["pattern"].format(quant=args.dit_quant), MODELS / "diffusion_models", src["revision"])
    if args.only in (None, "te"):
        print("Text encoder (Heretic abliterated Qwen3-VL-8B):")
        fetch(TEXT_ENCODER_REPO, TEXT_ENCODER_FILE, MODELS / "text_encoders")
        if not args.no_vision:
            fetch(TEXT_ENCODER_REPO, TEXT_ENCODER_MMPROJ, MODELS / "text_encoders")
    if args.only in (None, "vae"):
        print("VAE:")
        fetch(VAE_REPO, VAE_FILE, MODELS / "vae")

    print("\nAll done. Set the paths in backend/.env (see .env.example) if you changed variants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
