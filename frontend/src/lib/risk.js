// Mirrors the backend levels. `level` is the numeric value the API returns.
export const RISK = [
  { name: 'low', label: 'Low', color: '#16a34a' },
  { name: 'moderate', label: 'Moderate', color: '#eab308' },
  { name: 'high', label: 'High', color: '#f97316' },
  { name: 'severe', label: 'Severe', color: '#dc2626' },
  { name: 'no_travel', label: 'No travel', color: '#1f1b2e' },
]

export const riskByName = Object.fromEntries(RISK.map((r) => [r.name, r]))

// Heat intensity (0-1) per level. leaflet.heat blends overlapping points, so
// the scale is kept compact and the gradient below maps it back to the same colors.
export const HEAT_INTENSITY = [0.2, 0.4, 0.6, 0.8, 1]
export const HEAT_GRADIENT = { 0.2: '#16a34a', 0.4: '#eab308', 0.6: '#f97316', 0.8: '#dc2626', 1.0: '#1f1b2e' }

export const ROUTE_COLORS = ['#2563eb', '#9333ea', '#0891b2']
