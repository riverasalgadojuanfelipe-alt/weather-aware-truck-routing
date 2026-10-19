const BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export class ApiError extends Error {}

/** Ask the backend to analyze a trip. Throws ApiError with a readable message. */
export async function analyzeTrip(payload) {
  let response
  try {
    response = await fetch(`${BASE_URL}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new ApiError('Could not reach the server. Check your connection and try again.')
  }

  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new ApiError(describeError(body) || `Request failed (${response.status})`)
  return body
}

// Django REST Framework returns {detail: "..."} or {field: ["message"]}.
function describeError(body) {
  if (body.detail) return body.detail
  return Object.entries(body)
    .map(([field, messages]) => `${field}: ${[].concat(messages).join(' ')}`)
    .join(' · ')
}
