"""
FinTrace Django Models
========================
Database models for tracking document processing and news events.

- Document: Tracks uploaded PDF files and their processing status/stats.
- NewsEvent: Stores parsed disruption events detected from news feeds.
"""

from django.db import models


class Document(models.Model):
    """
    Tracks an uploaded PDF document through the processing pipeline.

    Status lifecycle: pending → processing → completed | failed
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    title = models.CharField(
        max_length=500,
        help_text="Original filename or user-provided title.",
    )
    file = models.FileField(
        upload_to="documents/%Y/%m/%d/",
        help_text="The uploaded PDF file.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
        help_text="Current processing status.",
    )
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Celery task ID for status polling.",
    )

    # Extraction statistics (populated after processing completes)
    pages_count = models.PositiveIntegerField(default=0)
    chunks_count = models.PositiveIntegerField(default=0)
    nodes_extracted = models.PositiveIntegerField(default=0)
    relationships_extracted = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class NewsEvent(models.Model):
    """
    A supply-chain disruption event parsed from a news article.

    Created by the news_watcher Celery-Beat task. Each event may be
    linked to affected entities in the Neo4j knowledge graph.
    """

    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
        ("informational", "Informational"),
    ]

    title = models.CharField(
        max_length=500,
        unique=True,
        help_text="Short title of the disruption event.",
    )
    event_type = models.CharField(
        max_length=50,
        help_text="Category of disruption (e.g. 'port_closure', 'sanctions').",
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default="medium",
        help_text="Estimated impact severity.",
    )
    description = models.TextField(
        help_text="Detailed description of the disruption event.",
    )

    # Structured extracted parameters (stored as JSON lists)
    locations = models.JSONField(
        default=list,
        blank=True,
        help_text="Affected geographic locations.",
    )
    materials = models.JSONField(
        default=list,
        blank=True,
        help_text="Affected materials/products/commodities.",
    )
    affected_entities = models.JSONField(
        default=list,
        blank=True,
        help_text="Names of affected companies/organizations.",
    )

    source_url = models.URLField(
        max_length=1000,
        blank=True,
        default="",
        help_text="URL of the source news article.",
    )
    source_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Name of the news source.",
    )
    event_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the event occurred or was reported.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this event is still considered active.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.title}"
