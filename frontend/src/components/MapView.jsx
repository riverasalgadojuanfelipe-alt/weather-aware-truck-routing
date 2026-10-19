import { useEffect } from 'react'
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { formatDateTime } from '../lib/format'
import { ROUTE_COLORS, riskByName } from '../lib/risk'
import HeatLayer from './HeatLayer'

const DEFAULT_CENTER = [39.5, -98.35] // continental US

function FitToRoutes({ routes }) {
  const map = useMap()
  useEffect(() => {
    if (!routes.length) return
    const all = routes.flatMap((r) => r.geometry)
    map.fitBounds(all, { padding: [40, 40] })
  }, [routes, map])
  return null
}

export default function MapView({ routes, selectedId, heatPoints, showHeat }) {
  const selected = routes.find((r) => r.id === selectedId)
  // Draw the selected route last so it sits on top of the others.
  const drawOrder = [...routes].sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId))
  const first = routes[0]

  return (
    <MapContainer center={DEFAULT_CENTER} zoom={4} className="map" preferCanvas>
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <FitToRoutes routes={routes} />

      {showHeat && heatPoints.length > 0 && <HeatLayer points={heatPoints} />}

      {drawOrder.map((route) => {
        const color = ROUTE_COLORS[route.id % ROUTE_COLORS.length]
        const active = route.id === selectedId
        return (
          <Polyline key={route.id} positions={route.geometry} pathOptions={{ color, weight: active ? 6 : 4, opacity: active ? 0.95 : 0.5 }} />
        )
      })}

      {/* Checkpoints of the selected route, colored by risk at the truck's ETA. */}
      {selected?.checkpoints.map((cp) => {
        const risk = riskByName[cp.risk]
        return (
          <CircleMarker key={cp.index} center={[cp.lat, cp.lon]} radius={7} pathOptions={{ color: '#fff', weight: 2, fillColor: risk.color, fillOpacity: 1 }}>
            <Popup>
              <strong>Mile {Math.round(cp.mile)}</strong> · {risk.label}
              <br />
              ETA {formatDateTime(cp.eta)}
              <br />
              Wind {cp.weather.wind_mph.toFixed(0)} mph · Rain {cp.weather.rain_in_hr.toFixed(2)} in/h · Snow {cp.weather.snow_in_hr.toFixed(2)} in/h
              {cp.reasons.length > 0 && (
                <>
                  <br />
                  {cp.reasons.join('; ')}
                </>
              )}
            </Popup>
          </CircleMarker>
        )
      })}

      {first && (
        <>
          <CircleMarker center={first.geometry[0]} radius={9} pathOptions={{ color: '#111827', fillColor: '#fff', fillOpacity: 1, weight: 3 }}>
            <Tooltip permanent direction="top">
              Start
            </Tooltip>
          </CircleMarker>
          <CircleMarker center={first.geometry[first.geometry.length - 1]} radius={9} pathOptions={{ color: '#111827', fillColor: '#111827', fillOpacity: 1, weight: 3 }}>
            <Tooltip permanent direction="top">
              End
            </Tooltip>
          </CircleMarker>
        </>
      )}
    </MapContainer>
  )
}
