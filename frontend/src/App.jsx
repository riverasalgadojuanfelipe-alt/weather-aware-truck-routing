import { useMemo, useState } from 'react'
import { ApiError, analyzeTrip } from './api'
import CheckpointTable from './components/CheckpointTable'
import ForecastSlider from './components/ForecastSlider'
import MapView from './components/MapView'
import RouteCard from './components/RouteCard'
import TripForm from './components/TripForm'
import { heatPoints, worstLevelAt } from './lib/heat'
import './index.css'

export default function App() {
  const [result, setResult] = useState(null)
  const [selectedId, setSelectedId] = useState(0)
  const [hour, setHour] = useState(0)
  const [showHeat, setShowHeat] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(payload) {
    setLoading(true)
    setError('')
    try {
      const data = await analyzeTrip(payload)
      setResult(data)
      setSelectedId(data.recommendation.route_id)
      setHour(0)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const routes = useMemo(() => result?.routes ?? [], [result])
  const points = useMemo(() => heatPoints(routes, hour), [routes, hour])
  const worst = useMemo(() => worstLevelAt(routes, hour), [routes, hour])
  const selected = routes.find((r) => r.id === selectedId)
  const ordered = useMemo(() => [...routes].sort((a, b) => a.summary.rank - b.summary.rank), [routes])

  return (
    <div className="layout">
      <aside className="sidebar">
        <header>
          <h1>Weather-aware routing</h1>
          <p className="muted">Pick the safest route for your load, not just the fastest.</p>
        </header>

        <TripForm onSubmit={handleSubmit} loading={loading} />
        {error && <div className="card error" role="alert">{error}</div>}

        {result && (
          <>
            <div className="card recommendation">
              <strong>Route {result.recommendation.route_id + 1} is recommended</strong>
              {result.recommendation.reasons.map((reason) => (
                <p key={reason}>{reason}</p>
              ))}
            </div>
            {ordered.map((route) => (
              <RouteCard key={route.id} route={route} selected={route.id === selectedId} onSelect={setSelectedId} />
            ))}
            {selected && <CheckpointTable route={selected} />}
          </>
        )}
      </aside>

      <main className="map-area">
        <MapView routes={routes} selectedId={selectedId} heatPoints={points} showHeat={showHeat} />
        {result && (
          <div className="map-overlay">
            <label className="toggle">
              <input type="checkbox" checked={showHeat} onChange={(e) => setShowHeat(e.target.checked)} /> Heatmap
            </label>
            <ForecastSlider hour={hour} max={result.heatmap_hours} departure={result.request.departure} worstLevel={worst} onChange={setHour} />
          </div>
        )}
        {loading && <div className="map-loading">Fetching routes and weather…</div>}
      </main>
    </div>
  )
}
