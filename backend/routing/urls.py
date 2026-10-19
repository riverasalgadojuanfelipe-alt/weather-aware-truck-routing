from django.urls import path

from . import views

urlpatterns = [
    path("analyze", views.AnalyzeView.as_view(), name="analyze"),
    path("geocode", views.GeocodeView.as_view(), name="geocode"),
    path("health", views.HealthView.as_view(), name="health"),
]
