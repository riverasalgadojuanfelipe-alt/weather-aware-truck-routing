"""HTTP API.

POST /api/analyze   run the full routing + weather + risk analysis
GET  /api/geocode   look up a place name (used by the form for validation)
GET  /api/health    liveness probe for the hosting platform
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests
from django.conf import settings
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .analysis import ALLOWED_INTERVALS, TripRequest, analyze
from .providers import Geocoder, ProviderError, RouteProvider, WeatherProvider

MAX_FORECAST_DAYS = 14  # Open-Meteo's forecast window is 16 days; leave a margin.
MAX_LOAD_LBS = 150_000


def _session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = settings.HTTP_USER_AGENT
    return session


# Shared across requests so the weather cache is actually reused.
_SESSION = _session()
_GEOCODER = Geocoder(_SESSION, settings.NOMINATIM_BASE_URL, settings.HTTP_TIMEOUT_SECONDS)
_ROUTES = RouteProvider(_SESSION, settings.OSRM_BASE_URL, settings.HTTP_TIMEOUT_SECONDS)
_WEATHER = WeatherProvider(_SESSION, settings.OPEN_METEO_BASE_URL, settings.HTTP_TIMEOUT_SECONDS)


class AnalyzeSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=200)
    destination = serializers.CharField(max_length=200)
    departure = serializers.DateTimeField()
    load_lbs = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LBS)
    interval_miles = serializers.ChoiceField(choices=ALLOWED_INTERVALS, default=25)

    def validate_departure(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if value < now.replace(minute=0, second=0, microsecond=0):
            raise serializers.ValidationError("Departure must not be in the past.")
        if (value - now).days > MAX_FORECAST_DAYS:
            raise serializers.ValidationError(f"Weather forecasts only reach {MAX_FORECAST_DAYS} days ahead.")
        return value


class AnalyzeView(APIView):
    def post(self, request):
        serializer = AnalyzeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            origin = _GEOCODER.geocode(data["origin"])
            destination = _GEOCODER.geocode(data["destination"])
            trip = TripRequest(
                origin=(origin.lat, origin.lon),
                destination=(destination.lat, destination.lon),
                departure=data["departure"],
                load_lbs=data["load_lbs"],
                interval_miles=int(data["interval_miles"]),
            )
            result = analyze(trip, _ROUTES, _WEATHER)
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        result["request"]["origin_label"] = origin.label
        result["request"]["destination_label"] = destination.label
        return Response(result)


class GeocodeView(APIView):
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"detail": "Missing q parameter."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            place = _GEOCODER.geocode(query)
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response({"lat": place.lat, "lon": place.lon, "label": place.label})


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})
