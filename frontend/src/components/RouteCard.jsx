import { formatDateTime, formatDuration, formatMiles } from '../lib/format'
import { RISK, ROUTE_COLORS, riskByName } from '../lib/risk'

export default function RouteCard({ route, selected, onSelect }) {
  const { summary } = route
  const color = ROUTE_COLORS[route.id % ROUTE_COLORS.length]
  const total = Object.values(summary.miles_by_risk).reduce((a, b) => a + b, 0) || 1

  return (
    <button type="button" className={`card route-card ${selected ? 'selected' : ''}`} onClick={() => onSelect(route.id)} style={{ '--route-color': color }}>
      <div className="route-head">
        <span className="swatch" />
        <strong>Route {route.id + 1}</strong>
        {summary.recommended && <span className="badge">Recommended</span>}
        {summary.has_no_travel && <span className="badge danger">No-travel weather</span>}
        <span className="rank">#{summary.rank}</span>
      </div>

      <div className="stats">
        <span>{formatMiles(summary.distance_miles)}</span>
        <span>{formatDuration(summary.duration_hours)}</span>
        <span>Arrive {formatDateTime(summary.arrival)}</span>
      </div>

      <div className="risk-bar" role="img" aria-label="Miles by weather risk">
        {RISK.map(({ name, color: c, label }) => {
          const miles = summary.miles_by_risk[name]
          return miles > 0 ? <span key={name} style={{ width: `${(miles / total) * 100}%`, background: c }} title={`${label}: ${Math.round(miles)} mi`} /> : null
        })}
      </div>

      <div className="risk-legend">
        {RISK.slice(1).map(({ name, label, color: c }) => (
          <span key={name}>
            <i style={{ background: c }} />
            {label} {Math.round(summary.miles_by_risk[name])} mi
          </span>
        ))}
      </div>
      <div className="muted">
        Average risk {summary.avg_risk.toFixed(2)} / 4 · worst: {riskByName[summary.worst_risk].label}
      </div>
    </button>
  )
}
