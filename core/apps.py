from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Registra i signal handlers (post_save Apiario → backfill meteo).
        from . import signals  # noqa: F401
