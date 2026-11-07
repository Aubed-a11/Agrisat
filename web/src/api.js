const KEY = 'agrisat_session'

export function loadSession() {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null') } catch { return null }
}
export function saveSession(s) {
  try { s ? localStorage.setItem(KEY, JSON.stringify(s)) : localStorage.removeItem(KEY) } catch { /* stockage indisponible */ }
}

let session = loadSession()
export const setSession = (s) => { session = s; saveSession(s) }
export const getSession = () => session

async function request(method, path, body, opts = {}) {
  const headers = {}
  if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`
  let payload = body
  if (body && !(body instanceof FormData) && !(body instanceof URLSearchParams)) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload })
  if (res.status === 401 && !path.startsWith('/auth')) { setSession(null); window.location.reload() }
  if (opts.blob) return res.blob()
  const ct = res.headers.get('content-type') || ''
  const data = ct.includes('json') ? await res.json() : await res.text()
  if (!res.ok) throw new Error(typeof data === 'string' ? data : (data.detail?.[0]?.msg || data.detail || 'Erreur'))
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b),
  put: (p, b) => request('PUT', p, b),
  blob: (p) => request('GET', p, null, { blob: true }),
}

export async function login(username, password) {
  const form = new URLSearchParams({ username, password })
  const data = await request('POST', '/auth/login', form)
  setSession(data)
  return data
}

export const fmt = (x, d = 0) => x == null || Number.isNaN(x) ? '' :
  Number(x).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d })
export const pct = (x, d = 1) => x == null ? '' : `${(x * 100).toLocaleString('fr-FR', { maximumFractionDigits: d, minimumFractionDigits: d })} %`
export const CROPS = { coton: 'Coton', mais: 'Maïs' }

export function doyToDate(year, doy) {
  const d = new Date(Date.UTC(year, 0, 1))
  d.setUTCDate(d.getUTCDate() + doy + (year % 4 === 0 && doy >= 59 ? 1 : 0))
  return d
}
export const dateLabel = (year, doy) => doyToDate(year, doy).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', timeZone: 'UTC' })
export const isoDate = (year, doy) => doyToDate(year, doy).toISOString().slice(0, 10)

export async function download(path, filename) {
  const blob = await api.blob(path)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}
