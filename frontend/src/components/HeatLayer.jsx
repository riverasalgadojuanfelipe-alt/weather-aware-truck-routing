import L from 'leaflet'
import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import { RISK } from '../lib/risk'

const RADIUS = 16
const FILL_OPACITY = 0.4

function styleFor(level) {
  return { fillColor: RISK[Math.round(level)].color, fillOpacity: FILL_OPACITY }
}

/**
 * Risk corridor drawn as semi-transparent, borderless circle markers colored
 * straight from RISK, so the color depends on the risk level and not on how
 * many points overlap. Markers are created once per set of positions; moving
 * the slider only calls setStyle on them.
 */
export default function HeatLayer({ points }) {
  const map = useMap()
  const groupRef = useRef(null)
  const markersRef = useRef([])

  useEffect(() => {
    const group = L.layerGroup().addTo(map)
    groupRef.current = group
    return () => {
      group.remove()
      groupRef.current = null
      markersRef.current = []
    }
  }, [map])

  useEffect(() => {
    const group = groupRef.current
    const markers = markersRef.current
    const samePositions =
      markers.length === points.length &&
      markers.every((m, i) => {
        const ll = m.getLatLng()
        return ll.lat === points[i][0] && ll.lng === points[i][1]
      })

    if (samePositions) {
      markers.forEach((m, i) => m.setStyle(styleFor(points[i][2])))
      return
    }
    group.clearLayers()
    markersRef.current = points.map(([lat, lon, level]) => {
      const marker = L.circleMarker([lat, lon], { radius: RADIUS, stroke: false, interactive: false, ...styleFor(level) })
      group.addLayer(marker)
      return marker
    })
  }, [points])

  return null
}
