export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, options?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(path, {
    method: options?.method ?? 'GET',
    credentials: 'same-origin',
    headers: options?.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: options?.body !== undefined ? JSON.stringify(options.body) : undefined,
  })
  if (!res.ok) {
    let text = `Serveren svarede ${res.status}.`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') text = data.detail
    } catch {
      /* the status line is all we have */
    }
    throw new ApiError(text, res.status)
  }
  return res.json()
}
