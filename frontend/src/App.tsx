import { useCallback, useEffect, useState } from 'react'
import { api, type AppConfig, type Capabilities, type GenerateParams, type ImageRecord } from './api'
import { ControlPanel } from './components/ControlPanel'
import { EngineBar } from './components/EngineBar'
import { Gallery } from './components/Gallery'
import { ResultView } from './components/ResultView'
import { useEngineStatus, useGeneration, useLocalStorage } from './hooks'

const DEFAULT_PARAMS: GenerateParams = {
  prompt: '',
  negative_prompt: '',
  width: 1024,
  height: 1024,
  steps: 20,
  cfg_scale: 4.0,
  seed: -1,
  sampler: 'euler',
  batch_count: 1,
  transparent: false,
  ref_images: [],
  strength: 1.0,
  output_format: 'png',
}

export default function App() {
  const [stored, setStored] = useLocalStorage<Omit<GenerateParams, 'ref_images'>>('qi21.params', DEFAULT_PARAMS)
  const [refImages, setRefImages] = useState<string[]>([])
  const params: GenerateParams = { ...stored, ref_images: refImages }
  const setParams = (next: GenerateParams) => {
    const { ref_images, ...rest } = next
    setRefImages(ref_images)
    setStored(rest)
  }

  const [config, setConfig] = useState<AppConfig | null>(null)
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [history, setHistory] = useState<ImageRecord[]>([])
  const [selected, setSelected] = useState<ImageRecord | null>(null)

  const onImages = useCallback((images: ImageRecord[]) => {
    if (images.length === 0) return
    setHistory((h) => [...images.slice().reverse(), ...h])
    setSelected(images[0])
  }, [])

  const { job, busy, error, generate, cancel, clearError } = useGeneration(onImages)
  const { status, offline } = useEngineStatus(busy)

  useEffect(() => {
    api.config().then(setConfig).catch(() => undefined)
    api
      .history(120)
      .then((r) => {
        setHistory(r.items)
        setSelected((s) => s ?? r.items[0] ?? null)
      })
      .catch(() => undefined)
  }, [])

  // Sampler list comes from the engine, which is only queryable once it is ready.
  useEffect(() => {
    if (status?.state === 'ready' && !caps) api.capabilities().then(setCaps).catch(() => undefined)
  }, [status?.state, caps])

  const reuseSettings = (img: ImageRecord) => {
    const p = img.params
    setParams({
      ...params,
      prompt: String(p.prompt ?? ''),
      negative_prompt: String(p.negative_prompt ?? ''),
      width: Number(p.width ?? params.width),
      height: Number(p.height ?? params.height),
      steps: Number(p.steps ?? params.steps),
      cfg_scale: Number(p.cfg_scale ?? params.cfg_scale),
      seed: img.seed ?? Number(p.seed ?? -1),
      sampler: String(p.sampler ?? params.sampler),
      transparent: Boolean(p.transparent),
    })
  }

  const useAsReference = async (img: ImageRecord) => {
    const blob = await (await fetch(img.url)).blob()
    const dataUrl = await new Promise<string>((res) => {
      const r = new FileReader()
      r.onload = () => res(r.result as string)
      r.readAsDataURL(blob)
    })
    setRefImages((r) => (r.length < 10 ? [...r, dataUrl] : r))
  }

  const remove = async (img: ImageRecord) => {
    await api.deleteImage(img.id).catch(() => undefined)
    setHistory((h) => {
      const next = h.filter((x) => x.id !== img.id)
      setSelected((s) => (s?.id === img.id ? next[0] ?? null : s))
      return next
    })
  }

  const engineReady = !offline && status?.state === 'ready'

  return (
    <div className="app">
      <EngineBar status={status} offline={offline} />
      <main className="layout">
        <ControlPanel
          params={params}
          onChange={setParams}
          onGenerate={() => generate(params)}
          onCancel={cancel}
          busy={busy}
          disabled={!engineReady}
          config={config}
          caps={caps}
        />
        <div className="stage">
          {error && (
            <div className="error" role="alert">
              {error}
              <button type="button" className="ghost small" onClick={clearError}>
                dismiss
              </button>
            </div>
          )}
          <ResultView job={job} engine={status} selected={selected} onUseAsReference={useAsReference} onReuseSettings={reuseSettings} onDelete={remove} />
          <Gallery items={history} selectedId={selected?.id ?? null} onSelect={setSelected} />
        </div>
      </main>
    </div>
  )
}
