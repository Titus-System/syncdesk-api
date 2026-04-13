import time

from pymongo import monitoring

from app.core.metrics import mongo_command_latency


class MongoMetricsListener(monitoring.CommandListener):
    def __init__(self) -> None:
        self._start_times: dict[int, float] = {}
        self._collections: dict[int, str] = {}

    def started(self, event: monitoring.CommandStartedEvent) -> None:
        self._start_times[event.request_id] = time.perf_counter()
        self._collections[event.request_id] = str(
            event.command.get(event.command_name, "unknown")
        )

    def succeeded(self, event: monitoring.CommandSucceededEvent) -> None:
        start = self._start_times.pop(event.request_id, None)
        collection = self._collections.pop(event.request_id, "unknown")
        if start:
            elapsed = time.perf_counter() - start
            mongo_command_latency.labels(
                command=event.command_name,
                collection=collection,
            ).observe(elapsed)

    def failed(self, event: monitoring.CommandFailedEvent) -> None:
        self._start_times.pop(event.request_id, None)
        self._collections.pop(event.request_id, None)
