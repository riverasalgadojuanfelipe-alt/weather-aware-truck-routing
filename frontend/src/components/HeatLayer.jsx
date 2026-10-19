import L from 'leaflet'
import 'leaflet.heat'
import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import { HEAT_GRADIENT } from '../lib/risk'

/**
 * Thin wrapper around leaflet.heat. The layer is created once and only its
 * points are replaced when the slider moves, which keeps scrubbing smooth.
 */
export default function HeatLayer({ points }) {
  const map = useMap()
  const layerRef = useRef(null)

  useEffect(() => {
    const layer = L.heatLayer([], { radius: 28, blur: 22, max: 1, minOpacity: 0.35, gradient: HEAT_GRADIENT })
    layer.addTo(map)
    layerRef.current = layer
    return () => {
      // leaflet.heat schedules a redraw on animation frames and does not cancel it
      // when removed, which throws once the map is gone (e.g. React StrictMode remounts).
      L.Util.cancelAnimFrame(layer._frame)
      layer.remove()
      layerRef.current = null
    }
  }, [map])

  useEffect(() => {
    layerRef.current?.setLatLngs(points)
  }, [points])

  return null
}
