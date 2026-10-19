const SUBDIVISIONS = 3 // extra points between neighbouring checkpoints, for a continuous corridor

/**
 * Heatmap points ([lat, lon, level]) for every route at `hour` hours after departure.
 * Between two checkpoints we interpolate position and risk so the corridor
 * looks continuous instead of a string of dots.
 */
export function heatPoints(routes, hour) {
  const points = []
  for (const route of routes) {
    const cps = route.checkpoints
    cps.forEach((cp, i) => {
      points.push([cp.lat, cp.lon, cp.hourly_risk[hour]])
      const next = cps[i + 1]
      if (!next) return
      const a = cp.hourly_risk[hour]
      const b = next.hourly_risk[hour]
      for (let s = 1; s <= SUBDIVISIONS; s += 1) {
        const t = s / (SUBDIVISIONS + 1)
        points.push([cp.lat + (next.lat - cp.lat) * t, cp.lon + (next.lon - cp.lon) * t, a + (b - a) * t])
      }
    })
  }
  return points
}

/** Worst risk level seen anywhere on any route at `hour`. */
export function worstLevelAt(routes, hour) {
  return Math.max(0, ...routes.flatMap((r) => r.checkpoints.map((c) => c.hourly_risk[hour])))
}
