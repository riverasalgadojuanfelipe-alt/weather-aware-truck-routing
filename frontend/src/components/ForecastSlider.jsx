import { useEffect, useState } from 'react'
import { formatDateTime } from '../lib/format'
import { RISK } from '../lib/risk'

const PLAY_INTERVAL_MS = 450

export default function ForecastSlider({ hour, max, departure, worstLevel, onChange }) {
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (!playing) return undefined
    const timer = setInterval(() => onChange((h) => (h >= max ? 0 : h + 1)), PLAY_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [playing, max, onChange])

  const when = new Date(new Date(departure).getTime() + hour * 3600 * 1000).toISOString()

  return (
    <div className="forecast-slider">
      <button type="button" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play'}>
        {playing ? '❚❚' : '▶'}
      </button>
      <div className="slider-body">
        <div className="slider-title">
          <strong>Weather heatmap</strong>
          <span>
            +{hour} h · {formatDateTime(when)}
          </span>
        </div>
        <input type="range" min="0" max={max} value={hour} onChange={(e) => onChange(Number(e.target.value))} aria-label="Forecast hour after departure" />
      </div>
      <span className="chip" style={{ background: RISK[worstLevel].color }} title="Worst conditions on the corridor at this hour">
        {RISK[worstLevel].label}
      </span>
    </div>
  )
}
