import { useEffect, useState } from 'react'
import { api, type EngineStatus } from '../api'

interface Props {
  status: EngineStatus | null
  offline: boolean
}

const LABEL: Record<EngineStatus['state'], string> = {
  stopped: 'engine stopped',
  starting: 'loading models…',
  ready: 'ready',
  error: 'engine error',
}

export function EngineBar({ status, offline }: Props) {
  const [showLogs, setShowLogs] = useState(false)
  const [lines, setLines] = useState<string[]>([])

  useEffect(() => {
    if (!showLogs) return
    let cancelled = false
    const tick = async () => {
      try {
        const r = await api.logs(150)
        if (!cancelled) setLines(r.lines)
      } catch {
        /* backend offline */
      }
    }
    tick()
    const t = window.setInterval(tick, 2000)
    return () => {
      cancelled = true
      window.clearInterval(t)
    }
  }, [showLogs])

  const state = offline ? 'error' : (status?.state ?? 'starting')
  const label = offline ? 'backend offline (start uvicorn on :8000)' : status ? LABEL[status.state] : 'connecting…'

  return (
    <header className="topbar">
      <div className="brand">
        <strong>Qwen-Image-2.1</strong>
        <span className="muted small">abliterated · local · stable-diffusion.cpp</span>
      </div>
      <div className="status">
        <span className={`dot ${state}`} />
        <span>{label}</span>
        {status?.error && <span className="muted small"> — {status.error}</span>}
        {status && (
          <span className="muted small models" title={`${status.models.diffusion_model}\n${status.models.text_encoder}\n${status.models.vae}`}>
            {status.models.diffusion_model.replace(/\.gguf$/, '')} · {status.models.text_encoder.replace(/\.gguf$/, '')}
          </span>
        )}
        <button type="button" className="ghost small" onClick={() => setShowLogs((v) => !v)}>
          logs
        </button>
        {(state === 'error' || state === 'stopped') && !offline && (
          <button type="button" className="ghost small" onClick={() => api.restartEngine()}>
            restart engine
          </button>
        )}
      </div>
      {showLogs && (
        <pre className="logs">
          {lines.join('\n')}
        </pre>
      )}
    </header>
  )
}
