"""
Django management command to check the health of all external services.

Usage:
    python manage.py health_check
"""

import logging
import requests
from django.core.management.base import BaseCommand, CommandError

from core.config import OLLAMA_BASE_URL, OLLAMA_MODEL, NEWSAPI_KEY

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check the health of Neo4j, Ollama, and other external services'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\n🔍 Health Check: FinTrace Services\n"))
        
        errors = []
        
        # ── Check Neo4j ──────────────────────────────────────────────
        self.stdout.write("• Neo4j...", ending=" ")
        try:
            from core.services.neo4j_connection import get_driver
            driver = get_driver()
            driver.verify_connectivity()
            self.stdout.write(self.style.SUCCESS("✓ OK"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ FAILED: {e}"))
            errors.append(f"Neo4j: {e}")
        
        # ── Check Ollama ─────────────────────────────────────────────
        self.stdout.write(f"• Ollama ({OLLAMA_MODEL})...", ending=" ")
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                
                if OLLAMA_MODEL in str(models):
                    self.stdout.write(self.style.SUCCESS(f"✓ OK ({len(models)} models)"))
                else:
                    self.stdout.write(self.style.WARNING(f"⚠ Model '{OLLAMA_MODEL}' not found. Available: {models}"))
                    errors.append(f"Ollama: {OLLAMA_MODEL} not pulled. Run: ollama pull {OLLAMA_MODEL}")
            else:
                raise Exception(f"HTTP {resp.status_code}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ FAILED: {e}"))
            errors.append(f"Ollama: {e}. Make sure 'ollama serve' is running at {OLLAMA_BASE_URL}")
        
        # ── Check NewsAPI ────────────────────────────────────────────
        self.stdout.write("• NewsAPI...", ending=" ")
        try:
            if not NEWSAPI_KEY:
                self.stdout.write(self.style.WARNING("⚠ NEWSAPI_KEY not set (news watcher disabled)"))
            else:
                resp = requests.get(
                    "https://newsapi.org/v2/top-headlines",
                    params={"apiKey": NEWSAPI_KEY, "country": "us", "pageSize": 1},
                    timeout=10
                )
                
                if resp.status_code == 200:
                    self.stdout.write(self.style.SUCCESS("✓ OK"))
                else:
                    raise Exception(f"HTTP {resp.status_code}: {resp.json().get('message', 'Unknown error')}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠ UNAVAILABLE: {e}"))
            errors.append(f"NewsAPI: {e}")
        
        # ── Summary ──────────────────────────────────────────────────
        self.stdout.write("")
        
        if errors:
            self.stdout.write(self.style.ERROR(f"\n❌ {len(errors)} issue(s) detected:\n"))
            for error in errors:
                self.stdout.write(self.style.ERROR(f"   • {error}"))
            self.stdout.write("")
            raise CommandError("Health check failed. See details above.")
        else:
            self.stdout.write(self.style.SUCCESS("✅ All services healthy!\n"))
