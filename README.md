# Qwen-Image-2.1 (abliterated) — local image generation

Run [Qwen-Image-2.1](https://huggingface.co/Qwen/Qwen-Image-2.1) fully locally with the
[Heretic-abliterated text encoder](https://huggingface.co/pottokao/Qwen-Image-2.1-Text-Encoder-Heretic-GGUF),
behind a small FastAPI backend and a React + TypeScript web UI.

```
┌──────────────┐   /api/*    ┌──────────────────┐  /sdcpp/v1/*  ┌──────────────────────────┐
│ React + Vite │ ──────────▶ │ FastAPI backend  │ ────────────▶ │ sd-server                │
│ frontend     │ ◀────────── │ job proxy,       │ ◀──────────── │ (stable-diffusion.cpp)   │
│ :5180        │  /outputs/* │ gallery, logs    │               │ Metal / CUDA / Vulkan    │
└──────────────┘             │ :8000            │               │ :1234                    │
                             └──────────────────┘               └──────────────────────────┘
```

**Model components** (all downloaded by `scripts/download_models.py`, ~11.5 GB):

| Part | File | Source |
| --- | --- | --- |
| DiT (image model, 7B) | `qwen-image-2.1-UC-Q4_K_M.gguf` (4.6 GB) | [abenzerps/Qwen-Image-2.1-Uncensored-GGUF](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF) |
| Text encoder (Qwen3-VL-8B, refusal-ablated) | `qwen3vl_8b_heretic-Q4_K_M.gguf` (5.0 GB) | [pottokao/…-Text-Encoder-Heretic-GGUF](https://huggingface.co/pottokao/Qwen-Image-2.1-Text-Encoder-Heretic-GGUF) |
| Vision projector (needed for image editing) | `mmproj-qwen3vl_8b_heretic-f16.gguf` (1.2 GB) | same |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` (0.7 GB) | abenzerps repo (repack of Comfy-Org) |

Swap the DiT for the stock weights with `--dit base`, or a different quant with `--dit-quant Q6_K` / `Q8_0`.

## Requirements

- Python 3.11+ (3.12 recommended), Node 20+
- macOS (Apple Silicon, Metal) or Linux with an NVIDIA GPU (CUDA build of sd.cpp) — see `scripts/fetch_engine.sh`
- ~12 GB of GPU/unified memory for the default Q4_K_M set; ~20 GB free RAM total is comfortable

## Quick start

```bash
git clone <this repo> && cd qwen-2.1-image-abliterated
scripts/setup.sh          # venv + deps, frontend deps, sd.cpp binary, model download (~11.5 GB)
scripts/dev.sh            # backend :8000 (launches sd-server) + Vite dev server :5180
```

Open http://localhost:5180. The status bar turns green once sd-server has loaded the weights (~10 s on an M4 Pro, longer from cold disk cache).

Production-style single port (build the UI, serve it from FastAPI):

```bash
scripts/dev.sh --prod     # http://127.0.0.1:8000
```

### Linux / NVIDIA

`scripts/fetch_engine.sh` picks the macOS arm64 zip on Macs; on Linux it matches the `ubuntu` CUDA/Vulkan/AVX2 release zips
(edit the pattern in the script if you want a specific one), or build sd.cpp yourself with `-DSD_CUDA=ON` and drop
`sd-server` into `engine/bin/`. Everything else is identical. With 24 GB+ of VRAM you can use `--dit-quant Q8_0`
(7.6 GB) or `BF16` (14.2 GB) for better quality.

## Configuration

Copy `backend/.env.example` to `backend/.env`. Key options:

| Variable | Purpose |
| --- | --- |
| `QI_DIFFUSION_MODEL`, `QI_TEXT_ENCODER`, `QI_TEXT_ENCODER_VISION`, `QI_VAE` | model file paths |
| `QI_ENGINE_EXTRA_ARGS` | raw flags for `sd-server`, e.g. `--params-backend te=disk` to keep the text encoder off RAM |
| `QI_ENGINE_AUTOSTART=false` | run `sd-server` yourself; the backend adopts anything already listening on `:1234` |
| `QI_ENGINE_OFFLOAD_TO_CPU=true` | keep weights in system RAM, stream to GPU (discrete-GPU machines with little VRAM) |

## API

The backend is a thin, typed proxy over sd-server's native async API plus a persistent gallery.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/health` | engine state, step progress, loaded model names |
| `GET` | `/api/config` | defaults + aspect-ratio presets |
| `GET` | `/api/capabilities` | samplers/schedulers/limits from sd-server |
| `POST` | `/api/generate` | `{prompt, negative_prompt, width, height, steps, cfg_scale, seed, sampler, batch_count, transparent, ref_images[], strength, output_format}` → `202 {job_id}` |
| `GET` | `/api/jobs/{id}` | poll; on completion images are saved to `outputs/` and returned as records |
| `POST` | `/api/jobs/{id}/cancel` | |
| `GET` / `DELETE` | `/api/history[/{id}]` | gallery with parameters sidecars |
| `GET` | `/api/engine/logs` · `POST /api/engine/{start,stop,restart}` | |

Example:

```bash
curl -s -X POST localhost:8000/api/generate -H 'Content-Type: application/json' \
  -d '{"prompt":"a red fox in fresh snow","width":1024,"height":1024,"steps":20,"cfg_scale":4,"seed":42}'
curl -s localhost:8000/api/jobs/<job_id>
```

Editing: pass up to 10 `ref_images` (data URLs). Transparent PNGs: set `transparent: true`; the backend wraps the
prompt in the RGBA format the model card recommends.

## Quality vs. speed — getting the most out of the model

The defaults are tuned to *run* on a 24 GB Apple Silicon laptop, not to show the model at its best. Every knob below
trades quality for memory or time; turn them up as far as your hardware allows.

| Knob | Default (fits 24 GB Mac) | Full quality | What you gain |
| --- | --- | --- | --- |
| DiT weights | `Q4_K_M` (4.6 GB) | `BF16` (14.2 GB) — or `Q8_0` (7.6 GB), which is near-lossless | Fine detail, texture, sharper text rendering. 4-bit visibly softens. |
| Text encoder | `Q4_K_M` (5 GB) | Only GGUF the Heretic repo ships; bf16 exists only as a `transformers` checkpoint | Slight prompt-adherence gain; not worth chasing. |
| Resolution | 1024² presets (~1 MP) | 2048² presets (the model's native size; all model-card samples are 2K) | Biggest single difference. 4× the pixels, roughly 4–6× the time. |
| Steps | 20 | 40 (model card) | Cleaner detail, fewer artifacts. Time scales linearly. |
| CFG | 4.0 | 4–6 | Stronger prompt adherence; taste, not a compromise. |
| VAE | bf16 | bf16 | Already full quality. |
| Flash attention | on | on | No quality cost, keep it on. |

Memory budget for the whole set (weights only; add ~3–5 GB of compute buffers at 2K):

| DiT quant | DiT | + text encoder + mmproj + VAE | Total |
| --- | ---: | ---: | ---: |
| `Q4_K_M` | 4.6 GB | 6.9 GB | ~11.5 GB |
| `Q6_K` | 5.9 GB | 6.9 GB | ~12.8 GB |
| `Q8_0` | 7.6 GB | 6.9 GB | ~14.5 GB |
| `BF16` | 14.2 GB | 6.9 GB | ~21 GB |

### Step up the DiT quant

```bash
# near-lossless, fits a 24 GB Mac or a 16 GB+ GPU with the text encoder in RAM
backend/.venv/bin/python scripts/download_models.py --only dit --dit-quant Q8_0
# full precision, for 24 GB+ VRAM (or 32 GB+ unified memory)
backend/.venv/bin/python scripts/download_models.py --only dit --dit-quant BF16
```

Then point the backend at the new file in `backend/.env` and restart:

```bash
QI_DIFFUSION_MODEL=models/diffusion_models/qwen-image-2.1-UC-Q8_0.gguf   # or -UC-BF16.gguf
```

Prefer the stock (non-"UC") DiT? Add `--dit base` to the download command; file names lose the `-UC` part.

### Change the generation defaults

In the UI, pick the **2K** size tier and drag steps to 40. To make those the defaults, edit `default_steps`,
`default_width`, `default_height` (and `default_cfg`) in `backend/app/config.py`, and `DEFAULT_PARAMS` in
`frontend/src/App.tsx`. The frontend remembers your last-used settings in `localStorage`, so after the first change
they stick anyway.

### Low on memory (VRAM or unified)

- `QI_ENGINE_EXTRA_ARGS=--params-backend te=disk` streams the text encoder from disk each prompt (once per image,
  ~5 s) and keeps ~5.4 GB out of resident memory.
- On discrete GPUs with little VRAM, `QI_ENGINE_OFFLOAD_TO_CPU=true` keeps weights in system RAM and streams them.
- `--vae-tiling` (via `QI_ENGINE_EXTRA_ARGS`) cuts VAE decode memory at 2K at a small seam-risk cost.
- Dimensions must be divisible by 32. CFG > 1 doubles the work per step (conditional + unconditional pass).

### Speed reference

Speed on unified-memory Macs is memory-bound: close memory-hungry apps first. On an M4 Pro 24 GB running under heavy
swap, a 1024² / 20-step image took ~17 min; with free memory expect a few seconds per step at 1K. A 24 GB+ NVIDIA GPU
with the BF16 DiT does 2K / 40 steps in well under a minute.

## Project layout

```
backend/app/config.py   env-driven settings + sd-server argv
backend/app/engine.py   sd-server process supervisor, log/progress capture, API proxy
backend/app/store.py    outputs/ gallery (image + .json sidecar)
backend/app/main.py     FastAPI routes
frontend/src/           React UI (api.ts client, hooks.ts polling, components/)
scripts/                setup.sh, dev.sh, fetch_engine.sh, download_models.py
engine/bin/             sd-server / sd-cli (not committed)
models/                 weights (not committed)
```

## Licenses

Qwen-Image-2.1 weights: [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE).
Heretic text encoder: Apache-2.0. stable-diffusion.cpp: MIT. This repo's code: MIT.
