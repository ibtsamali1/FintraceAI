"""
URL configuration for the core app — Graph Query + FinTrace API endpoints.
"""

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    # --- Dashboard ---
    path("", views.dashboard_view, name="dashboard"),
    
    # --- Health Check ---
    path("health/", views.health_check, name="health_check"),

    # --- Graph Query API ---
    path("api/graph/node/", views.api_get_node, name="api_get_node"),
    path("api/graph/neighbors/", views.api_get_neighbors, name="api_get_neighbors"),
    path("api/graph/path/", views.api_find_path, name="api_find_path"),
    path("api/graph/impacted/", views.api_find_impacted, name="api_find_impacted"),
    path("api/graph/stats/", views.api_graph_stats, name="api_graph_stats"),

    # --- PDF Upload & Status Polling (no Celery/Redis required) ---
    path("api/upload/", views.api_upload_pdf, name="api_upload_pdf"),
    path("api/doc/<int:doc_id>/status/", views.api_document_status, name="api_document_status"),

    # --- Risk Query Agent ---
    path("api/query/", views.api_query_agent, name="api_query_agent"),
]
