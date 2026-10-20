# Weather-Aware Truck Routing

Given an origin, destination, departure time and load weight, the app fetches up to three
driving routes, samples weather at regular checkpoints along each one, scores the risk the
truck would face at the time it actually reaches each point, and recommends the safest route.
A time slider shows a weather-risk heatmap for the next 48 hours.

Live app: <https://weather-aware-truck-routing-inky.vercel.app>

## Stack

- **Backend:** Django 6.1 + Django REST Framework 3.18 (`backend/`)
- **Frontend:** React 19 + Vite 7 + Leaflet (`frontend/`)
- **Data sources (no API keys needed):** OSRM (routes), Open-Meteo (hourly forecast, with the National Weather Service as fallback), Nominatim (geocoding)

## Run locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate              # keeps Django's bookkeeping happy; the API has no models
python manage.py runserver            # http://localhost:8000

# Frontend (second terminal)
cd frontend
cp .env.example .env                  # leave VITE_API_URL empty in dev; Vite proxies /api to :8000
npm install
npm run dev                           # http://localhost:5173
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
| POST | `/api/analyze` | Body: `origin`, `destination`, `departure` (ISO 8601, not in the past, within 14 days), `load_lbs` (0-150000), `interval_miles` (10, 25, 50). Returns routes, checkpoints, summaries, the recommendation and `weather_provider` (`open-meteo`, `nws`, or `nws+open-meteo` when the fallback covered only part of the route). |
| GET | `/api/geocode?q=` | Resolve a place name. |
| GET | `/api/health` | Liveness check. |

Provider failures return `502` with a readable message.

## Project layout

```
backend/
  config/            Django settings and URL root
  routing/
    apps.py          Django app config
    urls.py          /api route table
    risk.py          threshold rules (pure)
    geo.py           distance, sampling along a polyline
    providers.py     OSRM, Open-Meteo, NWS and Nominatim clients
    recommend.py     ranking and explanation
    analysis.py      orchestration of one trip analysis
    views.py         request validation and HTTP layer
    tests/
frontend/src/
  main.jsx           React entry point
  App.jsx            top-level layout and state
  api.js             API client
  lib/               risk palette, formatting, heatmap points
  components/        form, route cards, checkpoint table, map, heat layer, slider
```

## Environment variables

| Variable | Where | Default | Purpose |
| --- | --- | --- | --- |
| `DJANGO_SECRET_KEY` | backend | dev-only key | Required in production. |
| `DJANGO_DEBUG` | backend | `1` | Set to `0` in production. |
| `DJANGO_ALLOWED_HOSTS` | backend | `*` | Comma-separated hostnames. |
| `CORS_ALLOWED_ORIGINS` | backend | all origins | Comma-separated frontend origins. |
| `OSRM_BASE_URL` | backend | public OSRM | Point to a self-hosted router. |
| `NOMINATIM_BASE_URL` | backend | public Nominatim | Point to a self-hosted geocoder. |
| `OPEN_METEO_BASE_URL` | backend | `api.open-meteo.com` | Primary forecast endpoint. |
| `NWS_BASE_URL` | backend | `api.weather.gov` | Fallback forecast endpoint. |
| `HTTP_USER_AGENT` | backend | app identifier | User-Agent for every outbound request. |
| `NWS_USER_AGENT` | backend | falls back to `HTTP_USER_AGENT` | api.weather.gov asks for a contact address here. |
| `HTTP_TIMEOUT_SECONDS` | backend | `20` | Per-request timeout for provider calls. |
| `VITE_API_URL` | frontend | empty (uses dev proxy) | Backend URL in production builds, no trailing slash. |

## Deployment

- **Backend (Render):** `render.yaml` defines the service. Set `CORS_ALLOWED_ORIGINS` to the
  frontend URL. Environment: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`.
- **Frontend (Vercel/Netlify):** root directory `frontend`, build `npm run build`, output `dist`.
  Set `VITE_API_URL` to the backend URL.

## Trade-offs

- Public OSRM, Nominatim and Open-Meteo are rate-limited and best-effort; for production they
  would be self-hosted or replaced by paid tiers.
- Open-Meteo's free tier has a daily quota that counts every location of a batched request. To stay
  under it, checkpoints are snapped to a 0.1° grid (about 11 km), so weather is a little coarser
  than the checkpoint spacing, and the cache lasts 60 minutes, so a forecast can be up to an hour old.
- When Open-Meteo fails, the National Weather Service (api.weather.gov) is the fallback. It needs
  no key but covers only the United States, publishes about a week of forecast (a later departure
  gets a 502 if Open-Meteo is also down), and takes two requests per new cell (one to find the
  gridpoint, which is cached, and one for the forecast). Its values are converted to the same units
  and its precipitation is liquid-equivalent, so melted snow is subtracted from rain using a 10:1
  ratio; results can differ slightly from Open-Meteo. The `weather_provider` field of the response
  says which service produced the data, and `NWS_USER_AGENT` can add a contact address to the
  User-Agent that NWS asks clients to send.
- ETA is distance-proportional rather than segment-by-segment speed, which is accurate enough
  for hourly forecast resolution.
- The forecast cache is in-process; a shared cache (Redis) would be needed with multiple workers.
- Forecasts only exist for about two weeks, hence the departure limit.
