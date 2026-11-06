import { useEffect, useRef, useState } from 'react'
import { usePoll } from '../core/usePoll'
import type { CameraItem } from '../core/types'
import { Dialog, SectionHead } from './common'

const API = '/api/s/cameras'
const FRAME_SECONDS = 5

/** A picture from the camera. The next one is asked for only when this one has
 *  arrived, because a new address would cancel a picture still on its way.
 *  `seconds` 0 holds the picture. */
export function CameraFrame({ camera, size = 'lo', seconds = FRAME_SECONDS }: {
  camera: CameraItem; size?: 'lo' | 'hi'; seconds?: number
}) {
  const [turn, setTurn] = useState(0)
  const [finished, setFinished] = useState(0)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!seconds) return
    const timer = setInterval(() => {
      if (document.hidden) return
      clearInterval(timer)
      setTurn((n) => n + 1)
    }, seconds * 1000)
    return () => clearInterval(timer)
  }, [finished, seconds])

  const landed = (ok: boolean) => {
    setFailed(!ok)
    setFinished((n) => n + 1)
  }

  return (
    <div className="cam-frame">
      <img src={`${API}/${camera.id}/frame.jpg?size=${size}&t=${turn}`} alt={`Billede fra ${camera.name}`} hidden={failed}
        onLoad={() => landed(true)} onError={() => landed(false)} />
      {failed && <p>Intet billede lige nu.</p>}
    </div>
  )
}

/** Set up by hand, for two reasons: an endless stream never reaches the state
 *  autoplay waits for, and a video taken off the page goes on downloading, which
 *  would keep the camera busy. */
function LiveVideo({ camera, onStop }: { camera: CameraItem; onStop: () => void }) {
  const ref = useRef<HTMLVideoElement>(null)
  useEffect(() => {
    const video = ref.current
    if (!video) return
    video.src = `${API}/${camera.id}/live.mp4`
    return () => {
      video.pause()
      video.removeAttribute('src')
      video.load()
    }
  }, [camera.id])
  return (
    <video ref={ref} className="cam-live" muted playsInline aria-label={`Live-video fra ${camera.name}`}
      onCanPlay={(e) => void e.currentTarget.play().catch(() => undefined)} onError={onStop} onEnded={onStop} />
  )
}

function Live({ camera, onClose }: { camera: CameraItem; onClose: () => void }) {
  const [stopped, setStopped] = useState(false)
  return (
    <Dialog title={camera.name} wide onClose={onClose}>
      {stopped ? (
        <>
          <CameraFrame camera={camera} size="hi" />
          <p className="note">Live-videoen kører ikke. Billedet her opdateres hvert {FRAME_SECONDS}. sekund.</p>
        </>
      ) : <LiveVideo camera={camera} onStop={() => setStopped(true)} />}
      <div className="dialog-actions">
        {stopped && <button onClick={() => setStopped(false)}>Start live igen</button>}
        <button onClick={onClose}>Luk</button>
      </div>
    </Dialog>
  )
}

export function Cameras({ onAuthLost }: { onAuthLost: () => void }) {
  const { data, error } = usePoll<{ cameras: CameraItem[] }>(`${API}/list`, 0, onAuthLost)
  const [live, setLive] = useState<CameraItem | null>(null)
  const cameras = data?.cameras ?? []
  return (
    <main className="page">
      <SectionHead title="Kameraer" text={`Billederne opdateres hvert ${FRAME_SECONDS}. sekund. Vælg et kamera for at se det live, uden lyd.`} />
      {error && <p className="problem">{error}</p>}
      <div className="cameras">
        {cameras.map((c) => (
          <button key={c.id} className="cam" onClick={() => setLive(c)}>
            <CameraFrame camera={c} seconds={live ? 0 : FRAME_SECONDS} />
            <span>{c.name}</span>
          </button>
        ))}
      </div>
      {data && !cameras.length && <p className="empty">Ingen kameraer sat op endnu. Det gøres under Admin → Opsætning.</p>}
      {live && <Live camera={live} onClose={() => setLive(null)} />}
    </main>
  )
}
