const BASE = '/api'

export async function submitAudit(url, mode) {
  const res = await fetch(`${BASE}/audit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, mode }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export async function getAuditStatus(jobId) {
  const res = await fetch(`${BASE}/audit/${jobId}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Not found (${res.status})`)
  }
  return res.json()
}

export async function getHistory() {
  const res = await fetch(`${BASE}/audit/history`)
  if (!res.ok) return { audits: [], total: 0 }
  return res.json()
}

export async function deleteAudit(jobId) {
  const res = await fetch(`${BASE}/audit/${jobId}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error('Delete failed')
}
