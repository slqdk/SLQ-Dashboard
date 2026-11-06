import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'

/** Load `path`, and again every `seconds` while the tab is visible. A failed
 *  refresh keeps the last good data and says so through `error`. */
export function usePoll<T>(path: string, seconds = 0, onAuthLost?: () => void) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const lost = useRef(onAuthLost)
  lost.current = onAuthLost

  const load = useCallback(async () => {
    try {
      setData(await api<T>(path))
      setError('')
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 401) lost.current?.()
      setError(exc instanceof Error ? exc.message : 'Kunne ikke hente data.')
    }
  }, [path])

  useEffect(() => {
    void load()
    if (!seconds) return
    const timer = setInterval(() => {
      if (!document.hidden) void load()
    }, seconds * 1000)
    const wake = () => {
      if (!document.hidden) void load()
    }
    document.addEventListener('visibilitychange', wake)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', wake)
    }
  }, [load, seconds])

  return { data, error, reload: load }
}

/** The current time, updated every `ms`. */
export function useNow(ms = 1000): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), ms)
    return () => clearInterval(timer)
  }, [ms])
  return now
}
