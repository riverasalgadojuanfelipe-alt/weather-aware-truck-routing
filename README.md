# Weather-Aware Truck Routing

Given an origin, destination, departure time and load weight, the app fetches up to three
driving routes, samples weather at regular checkpoints along each one, scores the risk the
truck would face at the time it actually reaches each point, and recommends the safest route.
A time slider shows a weather-risk heatmap for the next 48 hours.

- **Backend:** Django + Django REST Framework (`backend/`)
- **Frontend:** React + Vite + Leaflet (`frontend/`)
- **Data sources (no API keys needed):** OSRM (routes), Open-Meteo (hourly forecast, with the National Weather Service as fallback), Nominatim (geocoding)

## Run locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver            # http://localhost:8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                           # http://localhost:5173, /api is proxied to :8000
```

Tests: `cd backend && pytest`.

## How it works

1. **Geocode** origin and destination (free text or `lat,lon`).
2. **Routes:** OSRM returns alternatives; if fewer than three distinct roads come back, detour
   waypoints are used to fill the gap. Routes are sorted by duration.
3. **Checkpoints** are placed every 10, 25 or 50 miles (user choice), always including start and end.
4. **ETA** at each checkpoint is proportional to distance along the route.
5. **Weather:** checkpoints are snapped to a 0.1° grid and de-duplicated across all routes, then
   one batched Open-Meteo request per analysis gets hourly wind, rain, showers and snowfall for
   each cell; each checkpoint reads the hour matching its ETA. If Open-Meteo answers 429 or fails, the
   missing cells come from the National Weather Service (api.weather.gov, US only), converted to
   mph and inches per hour. Responses are cached per cell for 60 minutes.
6. **Risk** per checkpoint is the worst of wind, rain and snow (see below).
7. **Recommendation** ranks routes by, in order: miles under No Travel, miles under Severe,
   miles under High, mile-weighted average risk, then duration. Each criterion is rounded
   (0.1 mi, 0.01 risk, 1 min) so negligible differences fall through to the next one.
8. **Heatmap:** every checkpoint also carries its risk for each of the 48 hours after departure,
   so the slider is purely client-side and needs no further requests.

## Risk rules

Levels: Low (0), Moderate (1), High (2), Severe (3), No Travel (4).

The thresholds live in `backend/routing/risk.py`, a pure module with no I/O so they are easy to
read and test. Where a value sits exactly on a boundary shared by two levels, the **more dangerous
level wins**. No Travel is strict (rain above 1.00 in/h, snow above 3.0 in/h, wind of 55 mph or more).
Load weight adjusts the wind level, and the overall level is the maximum of the load-adjusted
wind level, the rain level and the snow level.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/analyze` | Body: `origin`, `destination`, `departure` (ISO 8601, not in the past, within 14 days), `load_lbs` (0-150000), `interval_miles` (10, 25, 50). Returns routes, checkpoints, summaries and the recommendation. |
| GET | `/api/geocode?q=` | Resolve a place name. |
| GET | `/api/health` | Liveness check. |

Provider failures return `502` with a readable message.

## Project layout

```
backend/
  config/            Django settings and URL root
  routing/
    risk.py          threshold rules (pure)
    geo.py           distance, sampling along a polyline
    providers.py     OSRM, Open-Meteo, NWS and Nominatim clients
    recommend.py     ranking and explanation
    analysis.py      orchestration of one trip analysis
    views.py         request validation and HTTP layer
    tests/
frontend/src/
  api.js             API client
  lib/               risk palette, formatting, heatmap points
  components/        form, route cards, checkpoint table, map, heat layer, slider
```

## Deployment

- **Backend (Render):** `render.yaml` defines the service. Set `CORS_ALLOWED_ORIGINS` to the
  frontend URL. Environment: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`.
- **Frontend (Vercel/Netlify):** root directory `frontend`, build `npm run build`, output `dist`.
  Set `VITE_API_URL` to the backend URL.

## Trade-offs

- Public OSRM, Nominatim and Open-Meteo are rate-limited and best-effort; for production they
  would be self-hosted or replaced by paid tiers.
- ETA is distance-proportional rather than segment-by-segment speed, which is accurate enough
  for hourly forecast resolution.
- The forecast cache is in-process; a shared cache (Redis) would be needed with multiple workers.
- Forecasts only exist for about two weeks, hence the departure limit.
