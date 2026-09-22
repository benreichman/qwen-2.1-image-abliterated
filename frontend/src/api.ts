// Typed client for the FastAPI backend (backend/app/main.py).

export interface EngineProgress {
  step: number
  total: number
  rate: number
  unit: 's/it' | 'it/s'
  at: number
}

export interface EngineStatus {
  state: 'stopped' | 'starting' | 'ready' | 'error'
  error: string | null
  pid: number | null
  started_at: number | null
  ready_at: number | null
  url: string
  progress: EngineProgress | null
  models: {
    diffusion_model: string
    text_encoder: string
    text_encoder_vision: string | null
    vae: string
  }
  missing_files: string[]
}

export interface SizePreset {
  label: string
  width: number
  height: number
  tier: '1K' | '2K'
}

export interface AppConfig {
  defaults: { width: number; height: number; steps: number; cfg_scale: number; sampler: string }
  size_presets: SizePreset[]
  models: EngineStatus['models']
}

export interface GenerateParams {
  prompt: string
  negative_prompt: string
  width: number
  height: number
  steps: number
  cfg_scale: number
  seed: number
  sampler: string
  batch_count: number
  transparent: boolean
  ref_images: string[]
  strength: number
  output_format: 'png' | 'jpeg' | 'webp'
}

export interface ImageRecord {
  id: string
  file: string
  url: string
  created: number
  job_id: string
  index: number
  seed: number | null
  params: Record<string, unknown> & Partial<GenerateParams> & { resolved_prompt?: string; ref_image_count?: number }
}

export interface Job {
  job_id: string
  status: 'queued' | 'generating' | 'completed' | 'failed' | 'cancelled'
  created: number
  started: number | null
  completed: number | null
  queue_position: number
  error: { code?: string; message?: string } | null
  images: ImageRecord[]
  params: ImageRecord['params']
}

export interface Capabilities {
  samplers: string[]
  schedulers: string[]
  limits?: { max_width: number; max_height: number; max_batch_count: number }
  model?: { name: string }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  health: () => request<{ ok: boolean; engine: EngineStatus; time: number }>('/api/health'),
  config: () => request<AppConfig>('/api/config'),
  capabilities: () => request<Capabilities>('/api/capabilities'),
  generate: (params: GenerateParams) => request<Job>('/api/generate', { method: 'POST', body: JSON.stringify(params) }),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  cancel: (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  history: (limit = 60, offset = 0) =>
    request<{ items: ImageRecord[]; total: number }>(`/api/history?limit=${limit}&offset=${offset}`),
  deleteImage: (id: string) => request<void>(`/api/history/${id}`, { method: 'DELETE' }),
  logs: (tail = 120) => request<{ lines: string[]; status: EngineStatus }>(`/api/engine/logs?tail=${tail}`),
  restartEngine: () => request<EngineStatus>('/api/engine/restart', { method: 'POST' }),
  startEngine: () => request<EngineStatus>('/api/engine/start', { method: 'POST' }),
}

/** Read a File as a data URL (what the backend/engine accepts for reference images). */
export function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}
