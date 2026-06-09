from django.contrib import admin

from core.models import Document, NewsEvent


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        "title", "status", "pages_count", "nodes_extracted",
        "relationships_extracted", "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["title"]
    readonly_fields = [
        "celery_task_id", "pages_count", "chunks_count",
        "nodes_extracted", "relationships_extracted",
        "created_at", "updated_at",
    ]


@admin.register(NewsEvent)
class NewsEventAdmin(admin.ModelAdmin):
    list_display = [
        "title", "event_type", "severity", "is_active",
        "source_name", "created_at",
    ]
    list_filter = ["event_type", "severity", "is_active", "created_at"]
    search_fields = ["title", "description"]
    readonly_fields = ["created_at", "updated_at"]
