import { useState } from 'react'
import { fileToDataUrl, type AppConfig, type Capabilities, type GenerateParams } from '../api'

interface Props {
  params: GenerateParams
  onChange: (next: GenerateParams) => void
  onGenerate: () => void
  onCancel: () => void
  busy: boolean
  disabled: boolean
  config: AppConfig | null
  caps: Capabilities | null
}

const FALLBACK_SAMPLERS = ['euler', 'euler_a', 'dpm++2m', 'res_multistep', 'lcm']

function imageDims(src: string): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight })
    img.onerror = () => resolve(null)
    img.src = src
  })
}

export function ControlPanel({ params, onChange, onGenerate, onCancel, busy, disabled, config, caps }: Props) {
  const [tier, setTier] = useState<'1K' | '2K'>('1K')
  const [advanced, setAdvanced] = useState(false)
  const set = <K extends keyof GenerateParams>(key: K, value: GenerateParams[K]) => onChange({ ...params, [key]: value })

  const presets = (config?.size_presets ?? []).filter((p) => p.tier === tier)
  const samplers = caps?.samplers?.length ? caps.samplers : FALLBACK_SAMPLERS
  const editing = params.ref_images.length > 0
  const models = config?.models ?? []
  const modelProfile = models.find((m) => m.id === params.model)
  const distilled = !!modelProfile && modelProfile.steps != null // official Turbo: fixed schedule, no CFG
  const accelerators = distilled ? [] : (config?.accelerators ?? [])
  const accel = accelerators.find((a) => a.id === params.accelerator)
  const turbo = distilled || (!!accel && accel.steps != null)
  const lockedSteps = distilled ? modelProfile!.steps! : accel?.steps ?? null
  const lockedCfg = distilled ? modelProfile!.cfg_scale! : accel?.cfg_scale ?? null

  const addRefs = async (files: FileList | null) => {
    if (!files) return
    const urls = await Promise.all(Array.from(files).slice(0, 10 - params.ref_images.length).map(fileToDataUrl))
    const next: GenerateParams = { ...params, ref_images: [...params.ref_images, ...urls] }
    // sd.cpp center-crops reference images to the output aspect ratio, so when the first
    // reference is added, snap the output size to the closest preset in the current tier.
    if (params.ref_images.length === 0 && urls.length > 0 && config) {
      const dims = await imageDims(urls[0])
      if (dims) {
        const target = dims.width / dims.height
        const best = config.size_presets
          .filter((p) => p.tier === tier)
          .reduce((a, b) => (Math.abs(b.width / b.height - target) < Math.abs(a.width / a.height - target) ? b : a))
        next.width = best.width
        next.height = best.height
      }
    }
    onChange(next)
  }

  return (
    <aside className="panel">
      <label className="field">
        <span className="label">Prompt</span>
        <textarea
          value={params.prompt}
          onChange={(e) => set('prompt', e.target.value)}
          rows={6}
          placeholder={editing ? 'Describe the edit, e.g. "Change the background to a sunset beach"' : 'Describe the image…'}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !busy && !disabled) onGenerate()
          }}
        />
      </label>

      {!turbo && (
        <label className="field">
          <span className="label">Negative prompt</span>
          <textarea value={params.negative_prompt} onChange={(e) => set('negative_prompt', e.target.value)} rows={2} placeholder="(optional)" />
        </label>
      )}

      <div className="field">
        <span className="label">
          Reference images <small>{params.ref_images.length}/10 · edit mode · output size snaps to the first image's aspect</small>
        </span>
        <div className="refs">
          {params.ref_images.map((src, i) => (
            <button key={i} type="button" className="ref" title="Remove" onClick={() => set('ref_images', params.ref_images.filter((_, j) => j !== i))}>
              <img src={src} alt={`reference ${i + 1}`} />
              <span>×</span>
            </button>
          ))}
          {params.ref_images.length < 10 && (
            <label className="ref add" title="Add reference image(s)">
              +
              <input type="file" accept="image/*" multiple hidden onChange={(e) => addRefs(e.target.files)} />
            </label>
          )}
        </div>
      </div>

      <div className="field">
        <span className="label">
          Size
          <span className="seg">
            {(['1K', '2K'] as const).map((t) => (
              <button key={t} type="button" className={tier === t ? 'on' : ''} onClick={() => setTier(t)}>
                {t}
              </button>
            ))}
          </span>
        </span>
        <div className="presets">
          {presets.map((p) => {
            const on = p.width === params.width && p.height === params.height
            return (
              <button
                key={`${p.width}x${p.height}`}
                type="button"
                className={on ? 'on' : ''}
                onClick={() => onChange({ ...params, width: p.width, height: p.height })}
                title={`${p.width}×${p.height}`}
              >
                <i style={{ aspectRatio: `${p.width} / ${p.height}` }} />
                {p.label}
              </button>
            )
          })}
        </div>
        <div className="row">
          <input type="number" step={32} min={256} max={4096} value={params.width} onChange={(e) => set('width', Number(e.target.value))} aria-label="width" />
          <span>×</span>
          <input type="number" step={32} min={256} max={4096} value={params.height} onChange={(e) => set('height', Number(e.target.value))} aria-label="height" />
        </div>
      </div>

      {models.length > 1 && (
        <div className="field">
          <span className="label">Model</span>
          <div className="modes">
            {models.map((m) => (
              <button
                key={m.id}
                type="button"
                className={params.model === m.id ? 'on' : ''}
                disabled={!m.available}
                title={m.available ? (m.note ?? '') : `${m.file} not downloaded — run scripts/download_models.py`}
                onClick={() => set('model', m.id)}
              >
                {m.label}
              </button>
            ))}
          </div>
          {modelProfile?.note && <small className="muted">{modelProfile.note}</small>}
        </div>
      )}

      {accelerators.length > 1 && (
        <div className="field">
          <span className="label">Mode</span>
          <div className="modes">
            {accelerators.map((a) => (
              <button
                key={a.id}
                type="button"
                className={params.accelerator === a.id ? 'on' : ''}
                disabled={!a.available}
                title={a.available ? (a.note ?? '') : `${a.file} not downloaded — run scripts/download_models.py --only lora --lora both`}
                onClick={() => set('accelerator', a.id)}
              >
                {a.label}
              </button>
            ))}
          </div>
          {accel?.note && <small className="muted">{accel.note}</small>}
        </div>
      )}

      <div className="grid2">
        <label className="field">
          <span className="label">
            Steps <b>{turbo ? lockedSteps : params.steps}</b>
          </span>
          <input type="range" min={4} max={50} value={turbo ? lockedSteps! : params.steps} disabled={turbo} onChange={(e) => set('steps', Number(e.target.value))} />
        </label>
        <label className="field">
          <span className="label">
            CFG <b>{(turbo ? lockedCfg! : params.cfg_scale).toFixed(1)}</b>
          </span>
          <input type="range" min={1} max={10} step={0.5} value={turbo ? lockedCfg! : params.cfg_scale} disabled={turbo} onChange={(e) => set('cfg_scale', Number(e.target.value))} />
        </label>
      </div>

      <div className="grid2">
        <label className="field">
          <span className="label">Seed</span>
          <div className="row">
            <input type="number" value={params.seed} onChange={(e) => set('seed', Number(e.target.value))} />
            <button type="button" className="ghost" title="Random seed (-1)" onClick={() => set('seed', -1)}>
              🎲
            </button>
          </div>
        </label>
        <label className="field">
          <span className="label">Batch</span>
          <input type="number" min={1} max={4} value={params.batch_count} onChange={(e) => set('batch_count', Number(e.target.value))} />
        </label>
      </div>

      <label className="check">
        <input type="checkbox" checked={params.transparent} onChange={(e) => set('transparent', e.target.checked)} />
        Transparent background (RGBA)
      </label>

      <button type="button" className="ghost small" onClick={() => setAdvanced((v) => !v)}>
        {advanced ? '▾' : '▸'} Advanced
      </button>
      {advanced && (
        <div className="advanced">
          <label className="field">
            <span className="label">Sampler</span>
            <select value={params.sampler} onChange={(e) => set('sampler', e.target.value)}>
              {samplers.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="label">Output format</span>
            <select value={params.output_format} onChange={(e) => set('output_format', e.target.value as GenerateParams['output_format'])}>
              <option value="png">png</option>
              <option value="webp">webp</option>
              <option value="jpeg">jpeg</option>
            </select>
          </label>
          {editing && (
            <label className="field">
              <span className="label">
                Edit strength <b>{params.strength.toFixed(2)}</b>
              </span>
              <input type="range" min={0} max={1} step={0.05} value={params.strength} onChange={(e) => set('strength', Number(e.target.value))} />
            </label>
          )}
        </div>
      )}

      <div className="actions">
        {busy ? (
          <button type="button" className="danger" onClick={onCancel}>
            Cancel
          </button>
        ) : (
          <button type="button" className="primary" onClick={onGenerate} disabled={disabled || !params.prompt.trim()}>
            {editing ? 'Edit image' : 'Generate'} <kbd>⌘↵</kbd>
          </button>
        )}
      </div>
    </aside>
  )
}
