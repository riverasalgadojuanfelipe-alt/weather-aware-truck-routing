// Mirrors the backend levels. `level` is the numeric value the API returns.
export const RISK = [
  { name: 'low', label: 'Low', color: '#16a34a' },
  { name: 'moderate', label: 'Moderate', color: '#eab308' },
  { name: 'high', label: 'High', color: '#f97316' },
  { name: 'severe', label: 'Severe', color: '#dc2626' },
  { name: 'no_travel', label: 'No travel', color: '#1f1b2e' },
]

export const riskByName = Object.fromEntries(RISK.map((r) => [r.name, r]))

export const ROUTE_COLORS = ['#2563eb', '#9333ea', '#0891b2']
