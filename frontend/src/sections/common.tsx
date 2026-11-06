import { useEffect, useRef } from 'react'

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
export function Dialog({ title, onClose, children }: {
  title: string; onClose: () => void; children: React.ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const node = ref.current
    if (node && !node.open) node.showModal()
  }, [])
  return (
    <dialog ref={ref} onClose={onClose} onCancel={onClose}>
      <h2>{title}</h2>
      {children}
    </dialog>
  )
}
