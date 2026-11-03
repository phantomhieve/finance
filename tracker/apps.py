from django.apps import AppConfig


class TrackerConfig(AppConfig):
    name = 'tracker'

    def ready(self):
        import pftracker.db_optimizations  # noqa: F401
