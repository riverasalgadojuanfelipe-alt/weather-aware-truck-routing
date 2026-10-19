import { formatDateTime } from '../lib/format'
import { riskByName } from '../lib/risk'

export default function CheckpointTable({ route }) {
  return (
    <div className="card">
      <h3>Route {route.id + 1} checkpoints</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp) => {
              const risk = riskByName[cp.risk]
              return (
                <tr key={cp.index} title={cp.reasons.join('\n')}>
                  <td>{Math.round(cp.mile)}</td>
                  <td>{formatDateTime(cp.eta)}</td>
                  <td>{cp.weather.wind_mph.toFixed(0)} mph</td>
                  <td>{cp.weather.rain_in_hr.toFixed(2)} in/h</td>
                  <td>{cp.weather.snow_in_hr.toFixed(2)} in/h</td>
                  <td>
                    <span className="chip" style={{ background: risk.color }}>
                      {risk.label}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
