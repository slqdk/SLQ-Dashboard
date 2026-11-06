import { useEffect, useState } from 'react'
import { api } from '../core/api'
import { usePoll } from '../core/usePoll'
import type { User } from '../core/types'
import { Dialog, SectionHead } from '../sections/common'

interface AdminUser extends User {
  online: boolean
  familylogKey: string
}

interface Section {
  id: string
  title: string
  familyDefault: boolean
}

interface Setup {
  settings: Record<string, unknown> & { envPinned: Record<string, string>; newsFeeds: { name: string; url: string }[] }
  status: Record<string, { ok: boolean; text: string }>
  googleRedirectUri: string
  version: string
}

export function Admin({ me, onAuthLost }: { me: User; onAuthLost: () => void }) {
  const [tab, setTab] = useState<'users' | 'setup'>('users')
  return (
    <main className="page">
      <SectionHead title="Admin" text="Familiens brugere, og al opsætning af forbindelser.">
        <div className="segmented" role="group" aria-label="Admin">
          <button className={tab === 'users' ? 'on' : ''} onClick={() => setTab('users')}>Brugere</button>
          <button className={tab === 'setup' ? 'on' : ''} onClick={() => setTab('setup')}>Opsætning</button>
        </div>
      </SectionHead>
      {tab === 'users' ? <Users me={me} onAuthLost={onAuthLost} /> : <SetupPage onAuthLost={onAuthLost} />}
    </main>
  )
}

// ---- Brugere -----------------------------------------------------------------

function Users({ me, onAuthLost }: { me: User; onAuthLost: () => void }) {
  const users = usePoll<AdminUser[]>('/api/admin/users', 30, onAuthLost)
  const sections = usePoll<Section[]>('/api/admin/sections', 0, onAuthLost)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [problem, setProblem] = useState('')

  const toggle = async (u: AdminUser, id: string, on: boolean) => {
    const next = on ? [...u.sections, id] : u.sections.filter((s) => s !== id)
    try {
      await api(`/api/admin/users/${u.id}`, { method: 'PATCH', body: { sections: next } })
      await users.reload()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Det lykkedes ikke.')
    }
  }

  return (
    <>
      {problem && <p className="problem">{problem}</p>}
      <div className="table-wrap">
        <table className="users">
          <thead>
            <tr>
              <th scope="col">Bruger</th>
              <th scope="col">Rolle</th>
              {sections.data?.map((s) => <th key={s.id} scope="col" className="turn">{s.title}</th>)}
              <th scope="col"><span className="sr-only">Handlinger</span></th>
            </tr>
          </thead>
          <tbody>
            {users.data?.map((u) => (
              <tr key={u.id}>
                <th scope="row">
                  <span className={`dot dot-${u.online ? 'good' : 'none'}`} aria-hidden="true" />
                  {u.name || u.username}
                  {u.name && <span className="meta"> {u.username}</span>}
                </th>
                <td>{u.role === 'admin' ? 'Administrator' : 'Familie'}</td>
                {sections.data?.map((s) => (
                  <td key={s.id} className="cell-check">
                    <input type="checkbox" aria-label={`${u.username}: ${s.title}`} disabled={u.role === 'admin'}
                      checked={u.sections.includes(s.id)} onChange={(e) => void toggle(u, s.id, e.target.checked)} />
                  </td>
                ))}
                <td><button onClick={() => setEditing(u)}>Ret</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">Administratorer ser alle sektioner. En prik betyder, at brugeren er logget ind.</p>
      <p><button className="primary" onClick={() => setAdding(true)}>Ny bruger</button></p>

      {adding && <NewUser onClose={() => setAdding(false)} onSaved={() => { setAdding(false); void users.reload() }} />}
      {editing && (
        <EditUser user={editing} isMe={editing.id === me.id} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); void users.reload() }} />
      )}
    </>
  )
}

function NewUser({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ username: '', name: '', password: '', role: 'family' })
  const [problem, setProblem] = useState('')
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value })
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api('/api/admin/users', { method: 'POST', body: form })
      onSaved()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Kunne ikke oprette.')
    }
  }
  return (
    <Dialog title="Ny bruger" onClose={onClose}>
      <form onSubmit={save}>
        <label>Brugernavn<input required autoFocus autoComplete="off" value={form.username} onChange={set('username')} /></label>
        <label>Navn<input value={form.name} onChange={set('name')} /></label>
        <label>Adgangskode, mindst 10 tegn<input type="password" required autoComplete="new-password" value={form.password} onChange={set('password')} /></label>
        <label>Rolle
          <select value={form.role} onChange={set('role')}>
            <option value="family">Familie</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        {problem && <p className="problem">{problem}</p>}
        <div className="dialog-actions">
          <button type="button" onClick={onClose}>Annullér</button>
          <button type="submit" className="primary">Opret bruger</button>
        </div>
      </form>
    </Dialog>
  )
}

function EditUser({ user, isMe, onClose, onSaved }: {
  user: AdminUser; isMe: boolean; onClose: () => void; onSaved: () => void
}) {
  const [name, setName] = useState(user.name)
  const [role, setRole] = useState(user.role)
  const [password, setPassword] = useState('')
  const [key, setKey] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [problem, setProblem] = useState('')

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api(`/api/admin/users/${user.id}`, { method: 'PATCH', body: { name, role } })
      if (password) await api(`/api/admin/users/${user.id}/password`, { method: 'PATCH', body: { password } })
      if (key) await api(`/api/admin/users/${user.id}/familylog-key`, { method: 'PUT', body: { key } })
      onSaved()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Kunne ikke gemme.')
    }
  }
  const run = async (path: string, method: string, body?: unknown) => {
    try {
      await api(path, { method, body })
      onSaved()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Det lykkedes ikke.')
    }
  }

  return (
    <Dialog title={user.name || user.username} onClose={onClose}>
      <form onSubmit={save}>
        <label>Navn<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>Rolle
          <select value={role} disabled={isMe} onChange={(e) => setRole(e.target.value as User['role'])}>
            <option value="family">Familie</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        <label>Ny adgangskode<input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        <label>FamilyLog-læsenøgle{user.familylogKey ? ` (sat, slutter på ${user.familylogKey})` : ''}
          <input autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
        </label>
        {user.familylogKey && <button type="button" className="link" onClick={() => void run(`/api/admin/users/${user.id}/familylog-key`, 'PUT', { key: null })}>Fjern læsenøglen</button>}
        {problem && <p className="problem">{problem}</p>}
        <div className="dialog-actions">
          {!isMe && !confirm && <button type="button" className="danger" onClick={() => setConfirm(true)}>Slet</button>}
          {!isMe && confirm && <button type="button" className="danger" onClick={() => void run(`/api/admin/users/${user.id}`, 'DELETE')}>Slet brugeren og hele tidslinjen</button>}
          <button type="button" onClick={() => void run(`/api/admin/users/${user.id}/sign-out`, 'POST')}>Log ud overalt</button>
          <button type="button" onClick={onClose}>Annullér</button>
          <button type="submit" className="primary">Gem</button>
        </div>
      </form>
    </Dialog>
  )
}

// ---- Opsætning ----------------------------------------------------------------

function Field({ label, name, form, pins, onChange, hint, type }: {
  label: string; name: string; form: Record<string, unknown>; pins: Record<string, string>
  onChange: (key: string, value: unknown) => void; hint?: string; type?: string
}) {
  const pin = pins[name]
  return (
    <label>{label}
      <input type={type ?? 'text'} disabled={!!pin} value={String(form[name] ?? '')} onChange={(e) => onChange(name, e.target.value)} />
      {pin && <span className="meta">Låst af {pin} i containeren</span>}
      {hint && !pin && <span className="meta">{hint}</span>}
    </label>
  )
}

function Secret({ label, name, setup, value, onChange }: {
  label: string; name: string; setup: Setup; value: string; onChange: (key: string, value: unknown) => void
}) {
  const isSet = Boolean(setup.settings[`${name}Set`])
  const pin = setup.settings.envPinned[name]
  return (
    <label>{label}
      <input type="password" autoComplete="off" disabled={!!pin} value={value}
        placeholder={isSet ? `Sat, slutter på ${String(setup.settings[`${name}Hint`]).replace('…', '')}` : 'Ikke sat'}
        onChange={(e) => onChange(name, e.target.value)} />
      {pin && <span className="meta">Låst af {pin} i containeren</span>}
    </label>
  )
}

interface Device {
  id?: number
  [key: string]: unknown
}

interface DeviceSpec {
  section: string
  title: string
  noun: string
  fields: { key: string; label: string; hint?: string; secret?: boolean }[]
}

const PRINTERS: DeviceSpec = {
  section: 'printers',
  title: 'Printere',
  noun: 'printer',
  fields: [
    { key: 'name', label: 'Navn' },
    { key: 'host', label: 'IP-adresse' },
    { key: 'serial', label: 'Serienummer' },
    { key: 'code', label: 'LAN Access Code', secret: true },
  ],
}

const CAMERAS: DeviceSpec = {
  section: 'cameras',
  title: 'Kameraer',
  noun: 'kamera',
  fields: [
    { key: 'name', label: 'Navn' },
    { key: 'host', label: 'IP-adresse' },
    { key: 'username', label: 'Brugernavn fra Camera Account' },
    { key: 'password', label: 'Adgangskode fra Camera Account', secret: true },
  ],
}

/** The list saves by itself and asks every few seconds, so it can tell whether a
 *  new device answers without touching the rest of the setup form. */
function Devices({ spec, changed, onEdit, onAuthLost, children }: {
  spec: DeviceSpec; changed: number; onEdit: (device: Device) => void; onAuthLost: () => void; children: React.ReactNode
}) {
  const { data, reload } = usePoll<{ items: Device[]; status: { ok: boolean; text: string } }>(
    `/api/s/${spec.section}/config`, 5, onAuthLost)
  useEffect(() => {
    if (changed) void reload()
  }, [changed, reload])
  const s = data?.status
  return (
    <fieldset>
      <legend>{spec.title}</legend>
      {s && <p className={s.ok ? 'status ok' : 'status'}><span className={`dot dot-${s.ok ? 'good' : 'slow'}`} aria-hidden="true" />{s.text}</p>}
      {!!data?.items.length && (
        <ul className="devices">
          {data.items.map((d) => (
            <li key={d.id}>
              <span>{String(d.name)}</span>
              <span className="meta">{String(d.host)}</span>
              <button type="button" onClick={() => onEdit(d)}>Ret</button>
            </li>
          ))}
        </ul>
      )}
      <div><button type="button" onClick={() => onEdit({})}>Tilføj {spec.noun}</button></div>
      {children}
    </fieldset>
  )
}

function DeviceForm({ spec, device, onClose, onSaved }: {
  spec: DeviceSpec; device: Device; onClose: () => void; onSaved: () => void
}) {
  const [form, setForm] = useState<Record<string, string>>(
    Object.fromEntries(spec.fields.map((f) => [f.key, String(device[f.key] ?? '')])))
  const [problem, setProblem] = useState('')
  const base = `/api/s/${spec.section}/config`

  const run = async (path: string, method: string, body?: unknown) => {
    try {
      await api(path, { method, body })
      onSaved()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Det lykkedes ikke.')
    }
  }
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    void run(device.id ? `${base}/${device.id}` : base, device.id ? 'PUT' : 'POST', form)
  }

  return (
    <Dialog title={device.id ? `Ret ${String(device.name)}` : `Tilføj ${spec.noun}`} onClose={onClose}>
      <form onSubmit={submit}>
        {spec.fields.map((f) => (
          <label key={f.key}>{f.label}
            <input type={f.secret ? 'password' : 'text'} autoComplete="off" required={!f.secret || !device.id} value={form[f.key]}
              placeholder={f.secret && device.id ? 'Sat. Tom = uændret' : undefined}
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
          </label>
        ))}
        {problem && <p className="problem">{problem}</p>}
        <div className="dialog-actions">
          {!!device.id && <button type="button" className="danger" onClick={() => void run(`${base}/${device.id}`, 'DELETE')}>Fjern</button>}
          <button type="button" onClick={onClose}>Annullér</button>
          <button type="submit" className="primary">Gem</button>
        </div>
      </form>
    </Dialog>
  )
}

function SetupPage({ onAuthLost }: { onAuthLost: () => void }) {
  const { data, reload } = usePoll<Setup>('/api/admin/setup', 0, onAuthLost)
  const [form, setForm] = useState<Record<string, unknown>>({})
  const [feeds, setFeeds] = useState<{ name: string; url: string }[]>([])
  const [message, setMessage] = useState('')
  const [problem, setProblem] = useState('')
  const [editing, setEditing] = useState<{ spec: DeviceSpec; device: Device } | null>(null)
  const [changed, setChanged] = useState(0)

  useEffect(() => {
    if (data) {
      setForm(data.settings)
      setFeeds(data.settings.newsFeeds)
    }
  }, [data])

  if (!data) return null
  const pins = data.settings.envPinned
  const change = (key: string, value: unknown) => setForm({ ...form, [key]: value })
  const status = (id: string) => {
    const s = data.status[id]
    return s ? <p className={s.ok ? 'status ok' : 'status'}><span className={`dot dot-${s.ok ? 'good' : 'slow'}`} aria-hidden="true" />{s.text}</p> : null
  }

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    const keys = ['publicUrl', 'timezone', 'homeName', 'homeLat', 'homeLon', 'googleClientId',
      'dkliveUrl', 'dkliveLink', 'familylogUrl', 'go2rtcUrl', 'nordnetMode']
    const body: Record<string, unknown> = {}
    for (const key of keys) if (!pins[key]) body[key] = form[key]
    for (const key of ['googleClientSecret', 'youtubeApiKey']) {
      if (form[key] && !pins[key]) body[key] = form[key]
    }
    body.newsFeeds = feeds.filter((f) => f.url.trim())
    try {
      await api('/api/admin/setup', { method: 'PUT', body })
      setProblem('')
      setMessage('Gemt.')
      await reload()
    } catch (exc) {
      setMessage('')
      setProblem(exc instanceof Error ? exc.message : 'Kunne ikke gemme.')
    }
  }

  return (
    <>
    <form className="setup" onSubmit={save}>
      <fieldset>
        <legend>Dashboardet</legend>
        <Field label="Offentlig adresse" name="publicUrl" form={form} pins={pins} onChange={change} hint="Fx https://dashboard.slq.dk. Tom = den adresse, browseren bruger." />
        <Field label="Tidszone" name="timezone" form={form} pins={pins} onChange={change} />
        <div className="form-row three">
          <Field label="Hjemme" name="homeName" form={form} pins={pins} onChange={change} />
          <Field label="Breddegrad" name="homeLat" form={form} pins={pins} onChange={change} type="number" />
          <Field label="Længdegrad" name="homeLon" form={form} pins={pins} onChange={change} type="number" />
        </div>
        <p className="note">Hjemme bruges til vejret og til at vise, hvad der sker tæt på.</p>
      </fieldset>

      <fieldset>
        <legend>Google Kalender</legend>
        {status('calendar')}
        <Field label="Client ID" name="googleClientId" form={form} pins={pins} onChange={change} />
        <Secret label="Client secret" name="googleClientSecret" setup={data} value={String(form.googleClientSecret ?? '')} onChange={change} />
        <details>
          <summary>Sådan laves klienten i Google Cloud</summary>
          <ol>
            <li>Opret et projekt i Google Cloud Console, og slå Google Calendar API til.</li>
            <li>Sæt Google Auth Platform op som External, og tilføj scopet calendar.readonly under Data access.</li>
            <li>Tilføj jeres domæne under Authorised domains på Branding, og udfyld forside, privatlivspolitik og vilkår. Uden dem kan appen ikke publiceres. Brug denne adresse til de to sidste, og lad logoet stå tomt, for et logo kræver, at Google godkender appen:</li>
          </ol>
          <code className="copy">{data.googleRedirectUri.replace('/api/google/callback', '/privacy.html')}</code>
          <ol start={4}>
            <li>Tryk Publish app under Audience. I Testing udløber forbindelsen efter 7 dage.</li>
            <li>Opret en OAuth client af typen Web application med denne Authorized redirect URI:</li>
          </ol>
          <code className="copy">{data.googleRedirectUri}</code>
        </details>
      </fieldset>

      <fieldset>
        <legend>DK live</legend>
        {status('dklive')}
        <Field label="Adresse, som serveren læser" name="dkliveUrl" form={form} pins={pins} onChange={change} hint="Fx http://<lxc-ip>:4200" />
        <Field label="Adresse til kortet i browseren" name="dkliveLink" form={form} pins={pins} onChange={change} hint="Tom = samme adresse" />
      </fieldset>

      <fieldset>
        <legend>FamilyLog</legend>
        {status('familylog')}
        <Field label="Adresse" name="familylogUrl" form={form} pins={pins} onChange={change} hint="Fx http://30.11.0.108:8081. Læsenøgler sættes pr. bruger." />
      </fieldset>

      <fieldset>
        <legend>Nyheder</legend>
        {status('news')}
        {feeds.map((f, i) => (
          <div className="form-row feed" key={i}>
            <label>Navn<input value={f.name} onChange={(e) => setFeeds(feeds.map((x, n) => n === i ? { ...x, name: e.target.value } : x))} /></label>
            <label>RSS-adresse<input value={f.url} onChange={(e) => setFeeds(feeds.map((x, n) => n === i ? { ...x, url: e.target.value } : x))} /></label>
            <button type="button" onClick={() => setFeeds(feeds.filter((_, n) => n !== i))}>Fjern</button>
          </div>
        ))}
        <button type="button" onClick={() => setFeeds([...feeds, { name: '', url: '' }])}>Tilføj kilde</button>
      </fieldset>

      <fieldset>
        <legend>SLQ DL</legend>
        {status('latenight')}
        <Secret label="YouTube API-nøgle, valgfri" name="youtubeApiKey" setup={data} value={String(form.youtubeApiKey ?? '')} onChange={change} />
        <p className="note">Monologerne kommer fra YouTube. Uden nøgle bruges kanalernes RSS, som falder ud i perioder. Med en gratis nøgle fra samme Google Cloud-projekt som kalenderen (YouTube Data API v3) er det stabilt.</p>
      </fieldset>

      <fieldset>
        <legend>Formel 1</legend>
        {status('f1')}
        <p className="note">Sæsonplanen hentes fra Jolpica og kræver ingen opsætning.</p>
      </fieldset>

      <Devices spec={PRINTERS} changed={changed} onAuthLost={onAuthLost} onEdit={(device) => setEditing({ spec: PRINTERS, device })}>
        <p className="note">Bambu Lab-printere på jeres net. Dashboardet læser status direkte fra printeren og kan ikke styre den. IP-adresse, serienummer og LAN Access Code finder du i printerens indstillinger.</p>
      </Devices>

      <Devices spec={CAMERAS} changed={changed} onAuthLost={onAuthLost} onEdit={(device) => setEditing({ spec: CAMERAS, device })}>
        <Field label="Adresse til go2rtc" name="go2rtcUrl" form={form} pins={pins} onChange={change} />
        <p className="note">Tapo C200: opret en Camera Account i Tapo-appen under kameraet, Device Settings, Advanced Settings, Camera Account. Husk at give familien adgang under Brugere; sektionen er slået fra som standard.</p>
      </Devices>

      <fieldset>
        <legend>Nordnet</legend>
        {status('aktier')}
        <label>Forbindelse
          <select value={String(form.nordnetMode ?? 'off')} onChange={(e) => change('nordnetMode', e.target.value)}>
            <option value="off">Ikke forbundet</option>
            <option value="csv">Importeret udtræk</option>
          </select>
        </label>
        <p className="note">Hver person importerer sin egen CSV-fil fra Nordnet på siden Aktier. Nordnets API tager ikke imod nye kunder, så dashboardet bruger det ikke.</p>
      </fieldset>

      <div className="setup-actions">
        <button type="submit" className="primary">Gem opsætning</button>
        {message && <span className="status ok">{message}</span>}
        {problem && <span className="problem">{problem}</span>}
        <span className="meta">Version {data.version}</span>
      </div>
    </form>
    {editing && (
      <DeviceForm spec={editing.spec} device={editing.device} onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); setChanged((n) => n + 1) }} />
    )}
    </>
  )
}
