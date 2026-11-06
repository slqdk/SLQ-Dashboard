import { useEffect, useRef, useState } from 'react'

export function SectionHead({ title, text, children }: {
  title: string; text?: string; children?: React.ReactNode
}) {
  return (
    <header className="section-head">
      <div>
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {children && <div className="section-actions">{children}</div>}
    </header>
  )
}

/** A native <dialog>: focus, Esc and the backdrop come with it. */
export function Dialog({ title, wide, onClose, children }: {
  title: string; wide?: boolean; onClose: () => void; children: React.ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const node = ref.current
    if (node && !node.open) node.showModal()
  }, [])
  return (
    <dialog ref={ref} className={wide ? 'wide' : undefined} onClose={onClose} onCancel={onClose}>
      <h2>{title}</h2>
      {children}
    </dialog>
  )
}

/** A file sent as the request body to an import that answers how it went. */
export function FileImport({ title, url, label, accept, onClose, onDone, children }: {
  title: string; url: string; label: string; accept: string; onClose: () => void; onDone: () => void
  children: React.ReactNode
}) {
  const [problem, setProblem] = useState('')
  const [result, setResult] = useState('')
  const [busy, setBusy] = useState(false)

  const send = async (file: File | undefined) => {
    if (!file) return
    setBusy(true)
    setProblem('')
    setResult('')
    try {
      const res = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'text/csv' }, body: file })
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Importen lykkedes ikke.')
      setResult(`${data.added} nye, ${data.updated} opdaterede, ${data.same} havde du allerede.${data.skipped ? ` ${data.skipped} rækker kunne ikke læses.` : ''}`)
      onDone()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Importen lykkedes ikke.')
    }
    setBusy(false)
  }

  return (
    <Dialog title={title} onClose={onClose}>
      {children}
      <label>{label}
        <input type="file" accept={accept} disabled={busy} onChange={(e) => void send(e.target.files?.[0])} />
      </label>
      {busy && <p className="note">Importerer.</p>}
      {result && <p className="lead">{result}</p>}
      {problem && <p className="problem">{problem}</p>}
      <div className="dialog-actions">
        <button onClick={onClose}>Luk</button>
      </div>
    </Dialog>
  )
}
