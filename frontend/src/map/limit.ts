/** How far the map goes: Denmark and Germany down to Hamburg. MapLibre's own maxBounds keeps
 *  the whole canvas inside the bounds, but the canvas reaches far under the panels, so what
 *  is limited here is the free part in the middle. No map in here, so it can be tested. */

export type Corners = [[number, number], [number, number]]

export const AREA: Corners = [[7.5, 53.3], [13.0, 57.9]]        // what fills the free part at the start
export const LIMIT: Corners = [[7.5, 53.3], [15.4, 57.9]]       // and how far one can go, Bornholm included

const WORLD_TILE = 512

const mercatorX = (lng: number) => (180 + lng) / 360
const mercatorY = (lat: number) => (180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))) / 360
const lngFromX = (x: number) => x * 360 - 180
const latFromY = (y: number) => (360 / Math.PI) * Math.atan(Math.exp(((180 - y * 360) * Math.PI) / 180)) - 90

/** Inside [low, high], and where they have crossed, at home: the free part is then bigger
 *  than the limit, and the map stays put. */
const within = (value: number, low: number, high: number, home: number) =>
  Math.min(Math.max(value, Math.min(low, home)), Math.max(high, home))

/** Where the centre of the free part may be at a zoom, for a free part of that many pixels. */
export function limitCenter(center: { lng: number; lat: number }, zoom: number, width: number, height: number): { lng: number; lat: number } {
  const world = WORLD_TILE * 2 ** zoom
  const halfWidth = width / 2 / world, halfHeight = height / 2 / world
  const [[west, south], [east, north]] = LIMIT
  const homeX = (mercatorX(AREA[0][0]) + mercatorX(AREA[1][0])) / 2
  const homeY = (mercatorY(AREA[0][1]) + mercatorY(AREA[1][1])) / 2
  const x = within(mercatorX(center.lng), mercatorX(west) + halfWidth, mercatorX(east) - halfWidth, homeX)
  const y = within(mercatorY(center.lat), mercatorY(north) + halfHeight, mercatorY(south) - halfHeight, homeY)
  return { lng: lngFromX(x), lat: latFromY(y) }
}
