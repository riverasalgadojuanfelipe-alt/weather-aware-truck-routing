import { useState } from 'react'
import { nextFullHour, toLocalInputValue } from '../lib/format'

const INTERVALS = [10, 25, 50]

export default function TripForm({ onSubmit, loading }) {
  const [origin, setOrigin] = useState('Dallas, TX')
  const [destination, setDestination] = useState('Denver, CO')
  const [departure, setDeparture] = useState(toLocalInputValue(nextFullHour()))
  const [loadLbs, setLoadLbs] = useState(42000)
  const [interval, setInterval] = useState(25)

  function handleSubmit(event) {
    event.preventDefault()
    onSubmit({
      origin: origin.trim(),
      destination: destination.trim(),
      // datetime-local has no zone; new Date() reads it as local time and toISOString() makes it UTC.
      departure: new Date(departure).toISOString(),
      load_lbs: Number(loadLbs),
      interval_miles: interval,
    })
  }

  return (
    <form className="card form" onSubmit={handleSubmit}>
      <label>
        Origin
        <input value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="City, address or lat,lon" required />
      </label>
      <label>
        Destination
        <input value={destination} onChange={(e) => setDestination(e.target.value)} placeholder="City, address or lat,lon" required />
      </label>
      <div className="row">
        <label>
          Departure
          <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} required />
        </label>
        <label>
          Load (lb)
          <input type="number" min="0" max="150000" step="500" value={loadLbs} onChange={(e) => setLoadLbs(e.target.value)} required />
        </label>
      </div>
      <fieldset>
        <legend>Weather checkpoint every</legend>
        <div className="segmented">
          {INTERVALS.map((miles) => (
            <button key={miles} type="button" className={miles === interval ? 'active' : ''} onClick={() => setInterval(miles)}>
              {miles} mi
            </button>
          ))}
        </div>
      </fieldset>
      <button className="primary" type="submit" disabled={loading}>
        {loading ? 'Analyzing routes…' : 'Find safest route'}
      </button>
    </form>
  )
}
