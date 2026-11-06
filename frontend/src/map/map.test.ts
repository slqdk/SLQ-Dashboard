import { describe, expect, it } from 'vitest'
import { metres, model, secondLabel } from './aircraft'
import { limitCenter } from './limit'
import { flag, kind, typeName } from './shipInfo'
import { cap, compass, esc, link, rows, signed, webAddress } from './text'
import type { Aircraft } from './types'

const plane = (fields: Partial<Aircraft>): Aircraft => ({
  id: 'a1', callsign: null, reg: null, type: null, desc: null, operator: null, category: null, lat: 55, lon: 10, alt: null, onGround: false,
  gs: null, track: null, vr: null, squawk: null, emergency: null, military: false, seen: 0, route: null, ...fields,
})

describe('text for popups', () => {
  it('escapes what comes from a source', () => {
    expect(esc('<img src=x onerror="a">')).toBe('&lt;img src=x onerror=&quot;a&quot;&gt;')
    expect(rows([['Navn', '<b>'], ['Tom', null], ['Linje', 'a<br>b', true]])).toBe('<dt>Navn</dt><dd>&lt;b&gt;</dd><dt>Linje</dt><dd>a<br>b</dd>')
    expect(link('https://x/"y', 'Åbn')).toContain('href="https://x/&quot;y"')
  })

  it('links only to the web', () => {
    expect(link('javascript:alert(1)', 'Åbn')).toBe('')
    expect(webAddress('data:text/html,x')).toBeNull()
    expect(webAddress('http://x.dk/1.jpg')).toBe('http://x.dk/1.jpg')
  })

  it('keeps labels short', () => {
    expect(cap('kort')).toBe('kort')
    expect(cap('en meget lang etiket på et kort over Danmark')).toBe('en meget lang etiket på…')
  })

  it('names the wind and the sea level', () => {
    expect(compass(250)).toBe('VSV')
    expect(compass(359)).toBe('N')
    expect(signed(104.4)).toBe('+104')
    expect(signed(-3)).toBe('−3')
  })
})

describe('how far the map goes', () => {
  const home = { lng: 10.25, lat: 55.68 }
  const FREE = [1000, 500] as const

  it('stays put when the free part is bigger than the limit', () => {
    const at = limitCenter({ lng: 2, lat: 48 }, 5, ...FREE)
    expect(at.lng).toBeCloseTo(home.lng, 1)
    expect(at.lat).toBeCloseTo(home.lat, 1)
  })

  it('keeps the free part north of Hamburg when zoomed in', () => {
    const berlin = limitCenter({ lng: 13.4, lat: 52.5 }, 9, ...FREE)
    expect(berlin.lat).toBeGreaterThan(53.3)
    expect(berlin.lat).toBeLessThan(54)
  })

  it('reaches Skagen and Bornholm, and no further', () => {
    expect(limitCenter({ lng: 10.6, lat: 57.7 }, 11, ...FREE)).toEqual(expect.objectContaining({ lat: expect.closeTo(57.7, 5) }))
    expect(limitCenter({ lng: 14.9, lat: 55.1 }, 11, ...FREE).lng).toBeCloseTo(14.9, 5)
    expect(limitCenter({ lng: 20, lat: 55.1 }, 11, ...FREE).lng).toBeLessThan(15.4)
    expect(limitCenter({ lng: 10, lat: 70 }, 11, ...FREE).lat).toBeLessThan(57.9)
  })

  it('leaves a place inside the limit alone', () => {
    const odense = limitCenter({ lng: 10.39, lat: 55.4 }, 10, ...FREE)
    expect(odense.lng).toBeCloseTo(10.39, 5)
    expect(odense.lat).toBeCloseTo(55.4, 5)
  })
})

describe('aircraft', () => {
  it('reads the model from the type code, then the description', () => {
    expect(model(plane({ type: 'B738', desc: 'BOEING 737-800' }))).toBe('737-800')
    expect(model(plane({ desc: 'LOCKHEED MARTIN F-16C' }))).toBe('F-16')
    expect(model(plane({ desc: 'AIRBUS A-320' }))).toBe('A320')
    expect(model(plane({ desc: 'PILATUS PC-12' }))).toBe('PC-12')
    expect(model(plane({ type: 'XXXX' }))).toBe('XXXX')
    expect(model(plane({ reg: 'OY-ABC' }))).toBe('OY-ABC')
  })

  it('puts height and route on the second label', () => {
    expect(metres(1000)).toBe('305 m')
    expect(secondLabel(plane({ type: 'B738', onGround: true }))).toBe('737-800\npå jorden')
    const route = { from: 'CPH', to: 'AAL', fromName: null, toName: null }
    expect(secondLabel(plane({ type: 'B738', callsign: 'SAS1', alt: 10000, route }))).toBe('737-800\nSAS1, 3048 m, CPH→AAL')
  })
})

describe('what an MMSI says', () => {
  it('tells a ship from what else sends AIS', () => {
    expect(kind(219000001)).toBe('ship')
    expect(kind(111219001)).toBe('sar')
    expect(kind(992191234)).toBe('aton')
    expect(kind(970123456)).toBe('sart')
  })

  it('reads the flag, also past the first digits of a rescue helicopter', () => {
    expect(flag(219000001)).toBe('DK')
    expect(flag(111219001)).toBe('DK')
    expect(flag(100000000)).toBeNull()
  })

  it('names the ship type', () => {
    expect(typeName(70)).toBe('Fragt')
    expect(typeName(null)).toBe('ukendt')
    expect(typeName(99)).toBe('Type 99')
  })
})
