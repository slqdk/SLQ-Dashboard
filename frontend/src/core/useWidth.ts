import { useEffect, useRef, useState } from 'react'

/** The width of an element, kept up to date. */
export function useWidth(start = 1200) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(start)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  return { ref, width }
}
