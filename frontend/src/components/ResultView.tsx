import { useEffect, useState } from 'react'
import type { EngineStatus, ImageRecord, Job } from '../api'

interface Props {
  job: Job | null
  engine: EngineStatus | null
  selected: ImageRecord | null
  onUseAsReference: (img: ImageRecord) => void
  onReuseSettings: (img: ImageRecord) => void
  onDelete: (img: ImageRecord) => void
}

function useElapsed(since: number | null | undefined, running: boolean) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(t)
  }, [running])
  if (!since) return 0
  return Math.max(0, now / 1000 - since)
}

export function ResultView({ job, engine, selected, onUseAsReference, onReuseSettings, onDelete }: Props) {
  const running = job?.status === 'queued' || job?.status === 'generating'
  const elapsed = useElapsed(job?.started ?? job?.created, !!running)
  const progress = running ? engine?.progress : null
  const pct = progress ? Math.round((progress.step / progress.total) * 100) : 0
  const eta = progress ? ((progress.total - progress.step) * (progress.unit === 's/it' ? progress.rate : 1 / progress.rate)) : null

  if (running) {
    return (
      <section className="result">
        <div className="progress-card">
          <div className="spinner" />
          <h2>{job?.status === 'queued' ? `Queued (position ${job.queue_position})` : 'Generating…'}</h2>
          <div className="bar">
            <i style={{ width: `${progress ? pct : 0}%` }} />
          </div>
          <p className="muted">
            {progress ? `step ${progress.step}/${progress.total} · ${progress.rate.toFixed(1)} ${progress.unit}` : 'encoding prompt…'} · {elapsed.toFixed(0)}s elapsed
            {eta != null && ` · ~${Math.round(eta)}s left`}
          </p>
          <p className="muted small">{String(job?.params?.resolved_prompt ?? job?.params?.prompt ?? '')}</p>
        </div>
      </section>
    )
  }

  if (!selected) {
    return (
      <section className="result empty">
        <p>Nothing here yet. Write a prompt and hit Generate.</p>
      </section>
    )
  }

  const p = selected.params
  return (
    <section className="result">
      <figure>
        <img src={selected.url} alt={String(p.prompt ?? '')} />
      </figure>
      <div className="meta">
        <p className="prompt">{String(p.prompt ?? '')}</p>
        {p.negative_prompt ? <p className="muted small">Negative: {String(p.negative_prompt)}</p> : null}
        <dl>
          <dt>Size</dt>
          <dd>
            {String(p.width)}×{String(p.height)}
          </dd>
          <dt>Steps</dt>
          <dd>{String(p.steps)}</dd>
          <dt>CFG</dt>
          <dd>{String(p.cfg_scale)}</dd>
          <dt>Seed</dt>
          <dd>{selected.seed ?? (p.seed === -1 ? 'random' : String(p.seed))}</dd>
          <dt>Sampler</dt>
          <dd>{String(p.sampler)}</dd>
          {p.ref_image_count ? (
            <>
              <dt>Refs</dt>
              <dd>{String(p.ref_image_count)}</dd>
            </>
          ) : null}
        </dl>
        <div className="row wrap">
          <a className="button" href={selected.url} download={selected.file}>
            Download
          </a>
          <button type="button" onClick={() => onReuseSettings(selected)}>
            Reuse settings
          </button>
          <button type="button" onClick={() => onUseAsReference(selected)}>
            Use as reference
          </button>
          <button type="button" className="danger ghost" onClick={() => onDelete(selected)}>
            Delete
          </button>
        </div>
      </div>
    </section>
  )
}
