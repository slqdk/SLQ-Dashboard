/** One entry in full, with its pictures and files. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../core/api'
import { fullDate, localDate } from '../../core/format'
import type { LifeEvent, LifeFile } from '../../core/types'
import { Dialog } from '../common'
import { sourceName } from './Timeline'

const API = '/api/s/logmylife'

export const bytes = (n: number): string => {
  if (n < 1024 ** 2) return `${Math.max(1, Math.round(n / 1024))} KB`
  const size = n < 1024 ** 3 ? n / 1024 ** 2 : n / 1024 ** 3
  return `${size.toLocaleString('da-DK', { maximumFractionDigits: size < 10 ? 1 : 0 })} ${n < 1024 ** 3 ? 'MB' : 'GB'}`
}

/** Files one at a time, so a long batch shows how far it has come and one bad file stops
 *  only itself. */
function useUpload(eventId: number, onDone: () => void) {
  const [progress, setProgress] = useState('')
  const [problem, setProblem] = useState('')
  const send = async (files: File[]) => {
    const failed: string[] = []
    for (const [i, file] of files.entries()) {
      setProgress(`Sender ${i + 1} af ${files.length}: ${file.name}`)
      try {
        const res = await fetch(`${API}/events/${eventId}/files?name=${encodeURIComponent(file.name)}`, {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
        })
        if (!res.ok) failed.push(res.status === 413 ? `${file.name} er for stor` : `${file.name} kom ikke med`)
      } catch {
        failed.push(`${file.name} kom ikke med`)
      }
    }
    setProgress('')
    setProblem(failed.join(', '))
    onDone()
  }
  return { progress, problem, send }
}

function Preview({ file }: { file: LifeFile }) {
  const original = `${API}/files/${file.id}/original`
  if (file.kind === 'image') return <a href={original} download={file.name} title="Hent originalen"><img className="life-big" src={`${API}/files/${file.id}/view`} alt={file.name} /></a>
  if (file.kind === 'video') return <video className="life-big" src={original} controls preload="metadata" />
  return <p><a href={original} download={file.name}>Hent {file.name}</a> <span className="meta">({bytes(file.bytes)})</span></p>
}

export function EntryDialog({ id, onClose, onChanged, onEdit }: {
  id: number; onClose: () => void; onChanged: () => void; onEdit: (e: LifeEvent) => void
}) {
  const [entry, setEntry] = useState<(LifeEvent & { files: LifeFile[] }) | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [sure, setSure] = useState(false)
  const [problem, setProblem] = useState('')
  const [over, setOver] = useState(false)
  const picker = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      setEntry(await api(`${API}/events/${id}`))
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Kunne ikke hente indlægget.')
    }
  }, [id])
  useEffect(() => { void load() }, [load])

  const upload = useUpload(id, () => {
    void load()
    onChanged()
  })
  const files = entry?.files ?? []
  const big = files.find((f) => f.id === selected) ?? files[0]

  const removeFile = async (file: LifeFile) => {
    if (!sure) {
      setSure(true)
      return
    }
    setSure(false)
    await api(`${API}/files/${file.id}`, { method: 'DELETE' })
    setSelected(null)
    await load()
    onChanged()
  }

  if (!entry) return <Dialog title="Indlæg" onClose={onClose}>{problem ? <p className="problem">{problem}</p> : <p className="note">Henter.</p>}</Dialog>

  const facts = [
    entry.end && entry.end.slice(0, 10) !== entry.day ? `til ${fullDate(localDate(entry.end.slice(0, 10)))}` : '',
    entry.location, entry.category, entry.mine ? sourceName(entry.source) : `Delt af ${entry.owner}`,
    entry.shared && entry.mine ? 'delt med familien' : '', entry.deletedAtSource ? 'slettet i kilden' : '',
  ].filter(Boolean).join(', ')

  return (
    <Dialog title={entry.title} wide onClose={onClose}>
      <div className={over ? 'life-detail over' : 'life-detail'}
        onDragOver={(e) => { if (entry.mine) { e.preventDefault(); setOver(true) } }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          if (entry.mine && e.dataTransfer.files.length) void upload.send([...e.dataTransfer.files])
        }}>
        <p className="meta"><time>{fullDate(localDate(entry.day))}</time>{facts ? `, ${facts}` : ''}</p>
        {entry.description && <p className="life-text">{entry.description}</p>}
        {big && <Preview file={big} />}
        {files.length > 1 && (
          <ul className="life-files">
            {files.map((f) => (
              <li key={f.id}>
                <button className={f.id === big?.id ? 'on' : ''} onClick={() => { setSelected(f.id); setSure(false) }} aria-label={f.name} title={f.name}>
                  {f.kind === 'image' ? <img src={`${API}/files/${f.id}/thumb`} alt="" loading="lazy" /> : <span>{f.name}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
        {big && <p className="meta">{big.name}, {bytes(big.bytes)}{big.taken ? `, taget ${big.taken.slice(0, 16).replace(':', '-').replace(':', '-')}` : ''}</p>}
        {upload.progress && <p className="note">{upload.progress}</p>}
        {(upload.problem || problem) && <p className="problem">{upload.problem || problem}</p>}
      </div>
      <div className="dialog-actions">
        {entry.mine && big && <button className="danger" onClick={() => void removeFile(big)}>{sure ? 'Ja, fjern filen' : 'Fjern filen'}</button>}
        {entry.mine && (
          <>
            <input ref={picker} type="file" multiple hidden onChange={(e) => { if (e.target.files?.length) void upload.send([...e.target.files]); e.target.value = '' }} />
            <button onClick={() => picker.current?.click()} disabled={!!upload.progress}>Tilføj billeder og filer</button>
            <button onClick={() => onEdit(entry)}>Ret</button>
          </>
        )}
        <button className="primary" onClick={onClose}>Luk</button>
      </div>
    </Dialog>
  )
}
