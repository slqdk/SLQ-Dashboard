import { useMemo, useState } from 'react'
import { api } from '../core/api'
import { usePoll } from '../core/usePoll'
import type { Folder, LinkItem } from '../core/types'
import { Dialog, SectionHead } from './common'

interface Tree {
  folders: Folder[]
  links: LinkItem[]
}

type Editing =
  | { kind: 'link'; link: Partial<LinkItem> }
  | { kind: 'folder'; folder: Partial<Folder> }
  | { kind: 'delete'; folder: Folder; folders: number; links: number }

const API = '/api/s/links'

function folderPath(folders: Folder[], id: number | null): string {
  const names: string[] = []
  let current = folders.find((f) => f.id === id)
  while (current) {
    names.unshift(current.name)
    const parent: number | null = current.parentId
    current = folders.find((f) => f.id === parent)
  }
  return names.join(' / ')
}

function Branch({ folders, links, parent, selected, depth, onSelect, onDrop }: {
  folders: Folder[]; links: LinkItem[]; parent: number | null; selected: number | null | 'all'; depth: number
  onSelect: (id: number) => void; onDrop: (linkId: number, folderId: number | null) => void
}) {
  const here = folders.filter((f) => f.parentId === parent).sort((a, b) => a.name.localeCompare(b.name, 'da'))
  if (!here.length) return null
  return (
    <ul>
      {here.map((f) => (
        <li key={f.id}>
          <button className={selected === f.id ? 'tree-item on' : 'tree-item'} style={{ paddingLeft: 10 + depth * 14 }}
            onClick={() => onSelect(f.id)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onDrop(Number(e.dataTransfer.getData('text/plain')), f.id)}>
            <span>{f.name}</span>
            <span className="meta">{links.filter((l) => l.folderId === f.id).length}</span>
          </button>
          <Branch folders={folders} links={links} parent={f.id} selected={selected} depth={depth + 1} onSelect={onSelect} onDrop={onDrop} />
        </li>
      ))}
    </ul>
  )
}

export function Links({ onAuthLost }: { onAuthLost: () => void }) {
  const { data, reload } = usePoll<Tree>(`${API}/tree`, 0, onAuthLost)
  const [selected, setSelected] = useState<number | null | 'all'>('all')
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState<Editing | null>(null)
  const [problem, setProblem] = useState('')
  const folders = useMemo(() => data?.folders ?? [], [data])
  const links = useMemo(() => data?.links ?? [], [data])

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (needle) {
      return links.filter((l) => `${l.title} ${l.url} ${l.note}`.toLowerCase().includes(needle))
    }
    return selected === 'all' ? links : links.filter((l) => l.folderId === selected)
  }, [links, selected, q])

  const run = async (work: () => Promise<unknown>) => {
    try {
      await work()
      setEditing(null)
      setProblem('')
      await reload()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Det lykkedes ikke.')
    }
  }

  const move = (id: number, folderId: number | null) =>
    run(() => api(`${API}/items/${id}`, { method: 'PATCH', body: { folderId } }))
  const pin = (l: LinkItem) =>
    run(() => api(`${API}/items/${l.id}`, { method: 'PATCH', body: { pinned: !l.pinned } }))

  const askDelete = async (folder: Folder) => {
    const size = await api<{ folders: number; links: number }>(`${API}/folders/${folder.id}/size`)
    setEditing({ kind: 'delete', folder, ...size })
  }

  const current = typeof selected === 'number' ? folders.find((f) => f.id === selected) ?? null : null

  return (
    <main className="page">
      <SectionHead title="Links" text="Dine links, i mapper. Fastgjorte links står på overblikket.">
        <input type="search" placeholder="Søg i alle links" aria-label="Søg i alle links" value={q} onChange={(e) => setQ(e.target.value)} />
        <button onClick={() => setEditing({ kind: 'folder', folder: { parentId: current?.id ?? null } })}>Ny mappe</button>
        <button className="primary" onClick={() => setEditing({ kind: 'link', link: { folderId: current?.id ?? null } })}>Nyt link</button>
      </SectionHead>
      {problem && !editing && <p className="problem">{problem}</p>}

      <div className="links-layout">
        <nav className="tree" aria-label="Mapper">
          <button className={selected === 'all' ? 'tree-item on' : 'tree-item'} onClick={() => setSelected('all')}>
            <span>Alle links</span><span className="meta">{links.length}</span>
          </button>
          <button className={selected === null ? 'tree-item on' : 'tree-item'} onClick={() => setSelected(null)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => move(Number(e.dataTransfer.getData('text/plain')), null)}>
            <span>Uden mappe</span><span className="meta">{links.filter((l) => l.folderId === null).length}</span>
          </button>
          <Branch folders={folders} links={links} parent={null} selected={selected} depth={0} onSelect={setSelected} onDrop={move} />
        </nav>

        <div>
          {current && !q && (
            <div className="folder-bar">
              <h2>{folderPath(folders, current.id)}</h2>
              <button onClick={() => setEditing({ kind: 'folder', folder: current })}>Omdøb eller flyt</button>
              <button className="danger" onClick={() => void askDelete(current)}>Slet mappe</button>
            </div>
          )}
          {shown.length ? (
            <ul className="link-list">
              {shown.map((l) => (
                <li key={l.id} draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', String(l.id))}>
                  <button className={l.pinned ? 'pin on' : 'pin'} aria-pressed={l.pinned}
                    aria-label={l.pinned ? 'Fjern fra overblikket' : 'Fastgør på overblikket'}
                    title={l.pinned ? 'Fjern fra overblikket' : 'Fastgør på overblikket'} onClick={() => void pin(l)}>★</button>
                  <div>
                    <a href={l.url} target="_blank" rel="noreferrer noopener">{l.title}</a>
                    <p className="meta">{l.url.replace(/^https?:\/\//, '')}{l.folderId !== null && (q || selected === 'all') ? `, ${folderPath(folders, l.folderId)}` : ''}</p>
                    {l.note && <p className="note">{l.note}</p>}
                  </div>
                  <button onClick={() => setEditing({ kind: 'link', link: l })}>Ret</button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">{q ? 'Ingen links matcher.' : 'Her er tomt. Tilføj et link med knappen øverst.'}</p>
          )}
        </div>
      </div>

      {editing?.kind === 'link' && (
        <LinkForm link={editing.link} folders={folders} problem={problem} onClose={() => { setEditing(null); setProblem('') }}
          onSave={(body) => run(() => editing.link.id
            ? api(`${API}/items/${editing.link.id}`, { method: 'PATCH', body })
            : api(`${API}/items`, { method: 'POST', body }))}
          onDelete={editing.link.id ? () => run(() => api(`${API}/items/${editing.link.id}`, { method: 'DELETE' })) : undefined} />
      )}
      {editing?.kind === 'folder' && (
        <FolderForm folder={editing.folder} folders={folders} problem={problem} onClose={() => { setEditing(null); setProblem('') }}
          onSave={(body) => run(() => editing.folder.id
            ? api(`${API}/folders/${editing.folder.id}`, { method: 'PATCH', body })
            : api(`${API}/folders`, { method: 'POST', body }))} />
      )}
      {editing?.kind === 'delete' && (
        <Dialog title={`Slet ${editing.folder.name}?`} onClose={() => setEditing(null)}>
          <p>{editing.links || editing.folders
            ? `${editing.links} links og ${editing.folders} undermapper bliver slettet sammen med mappen.`
            : 'Mappen er tom.'}</p>
          <div className="dialog-actions">
            <button onClick={() => setEditing(null)}>Annullér</button>
            <button className="danger" onClick={() => void run(async () => {
              await api(`${API}/folders/${editing.folder.id}`, { method: 'DELETE' })
              setSelected('all')
            })}>Slet mappen</button>
          </div>
        </Dialog>
      )}
    </main>
  )
}

function FolderSelect({ folders, value, exclude, onChange, label }: {
  folders: Folder[]; value: number | null; exclude?: number; onChange: (v: number | null) => void; label: string
}) {
  return (
    <label>{label}
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
        <option value="">Ingen mappe</option>
        {folders.filter((f) => f.id !== exclude).map((f) => (
          <option key={f.id} value={f.id}>{folderPath(folders, f.id)}</option>
        ))}
      </select>
    </label>
  )
}

function LinkForm({ link, folders, problem, onClose, onSave, onDelete }: {
  link: Partial<LinkItem>; folders: Folder[]; problem: string; onClose: () => void
  onSave: (body: object) => void; onDelete?: () => void
}) {
  const [title, setTitle] = useState(link.title ?? '')
  const [url, setUrl] = useState(link.url ?? '')
  const [note, setNote] = useState(link.note ?? '')
  const [folderId, setFolderId] = useState<number | null>(link.folderId ?? null)
  const [pinned, setPinned] = useState(link.pinned ?? false)
  return (
    <Dialog title={link.id ? 'Ret link' : 'Nyt link'} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSave({ title: title || url, url, note, folderId, pinned }) }}>
        <label>Adresse<input required autoFocus value={url} onChange={(e) => setUrl(e.target.value)} /></label>
        <label>Titel<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        <FolderSelect folders={folders} value={folderId} onChange={setFolderId} label="Mappe" />
        <label>Note<input value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <label className="check"><input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />Fastgør på overblikket</label>
        {problem && <p className="problem">{problem}</p>}
        <div className="dialog-actions">
          {onDelete && <button type="button" className="danger" onClick={onDelete}>Slet</button>}
          <button type="button" onClick={onClose}>Annullér</button>
          <button type="submit" className="primary">Gem</button>
        </div>
      </form>
    </Dialog>
  )
}

function FolderForm({ folder, folders, problem, onClose, onSave }: {
  folder: Partial<Folder>; folders: Folder[]; problem: string; onClose: () => void; onSave: (body: object) => void
}) {
  const [name, setName] = useState(folder.name ?? '')
  const [parentId, setParentId] = useState<number | null>(folder.parentId ?? null)
  return (
    <Dialog title={folder.id ? 'Ret mappe' : 'Ny mappe'} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSave({ name, parentId }) }}>
        <label>Navn<input required autoFocus value={name} onChange={(e) => setName(e.target.value)} /></label>
        <FolderSelect folders={folders} value={parentId} exclude={folder.id} onChange={setParentId} label="Ligger i" />
        {problem && <p className="problem">{problem}</p>}
        <div className="dialog-actions">
          <button type="button" onClick={onClose}>Annullér</button>
          <button type="submit" className="primary">Gem</button>
        </div>
      </form>
    </Dialog>
  )
}
