import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type EngineStatus, type GenerateParams, type ImageRecord, type Job } from './api'

/** Polls /api/health. Fast while the engine is starting or a job is running, slow otherwise. */
export function useEngineStatus(active: boolean) {
  const [status, setStatus] = useState<EngineStatus | null>(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    let timer: number | undefined
    let cancelled = false
    const tick = async () => {
      try {
        const h = await api.health()
        if (!cancelled) {
          setStatus(h.engine)
          setOffline(false)
        }
      } catch {
        if (!cancelled) setOffline(true)
      }
      const busy = active || !status || status.state === 'starting'
      timer = window.setTimeout(tick, busy ? 1500 : 5000)
    }
    tick()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, status?.state])

  return { status, offline }
}

/** Submits jobs and polls them to completion. */
export function useGeneration(onImages: (images: ImageRecord[]) => void) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<number | undefined>(undefined)

  const stopPolling = () => window.clearTimeout(pollRef.current)

  const poll = useCallback(
    (id: string) => {
      const run = async () => {
        try {
          const j = await api.job(id)
          setJob(j)
          if (j.status === 'completed') {
            onImages(j.images)
            return
          }
          if (j.status === 'failed' || j.status === 'cancelled') {
            if (j.status === 'failed') setError(j.error?.message ?? 'generation failed')
            return
          }
        } catch (e) {
          setError((e as Error).message)
          return
        }
        pollRef.current = window.setTimeout(run, 1000)
      }
      run()
    },
    [onImages],
  )

  const generate = useCallback(
    async (params: GenerateParams) => {
      setError(null)
      stopPolling()
      try {
        const j = await api.generate(params)
        setJob(j)
        poll(j.job_id)
      } catch (e) {
        setError((e as Error).message)
      }
    },
    [poll],
  )

  const cancel = useCallback(async () => {
    if (!job) return
    try {
      const j = await api.cancel(job.job_id)
      setJob(j)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [job])

  useEffect(() => stopPolling, [])

  const busy = job !== null && (job.status === 'queued' || job.status === 'generating')
  return { job, busy, error, generate, cancel, clearError: () => setError(null) }
}

/** Persist a piece of state in localStorage. */
export function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key)
      return raw ? { ...initial, ...(JSON.parse(raw) as T) } : initial
    } catch {
      return initial
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* ignore quota / private mode */
    }
  }, [key, value])
  return [value, setValue] as const
}
