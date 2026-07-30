from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from .config import ConfigService, ConfigValues
from .db import create_engine_and_session_factory, init_db
from .history import HistoryService, HistorySnapshot
from .timer import PomodoroTimer


class PomodoroApplication:
    def __init__(self, db_path: Path | None = None):
        engine, session_factory = create_engine_and_session_factory(db_path=db_path)
        init_db(engine)

        self._config_service = ConfigService(session_factory)
        self._history_service = HistoryService(session_factory)
        self.config = self._config_service.get_or_create()
        self.timer = PomodoroTimer(self.config.to_timer_settings())
        self.status_message = "Ready."

    def tick(self) -> None:
        records = self.timer.tick()
        for record in records:
            self._history_service.record(record)
            self.status_message = f"Completed {record.phase_type.value.replace('_', ' ')}."

    def toggle_timer(self) -> None:
        before = self.timer.snapshot()
        self.timer.toggle()
        after = self.timer.snapshot()
        if not before.running and not before.paused and after.running:
            self.status_message = "Timer started."
        elif before.running and after.paused:
            self.status_message = "Timer paused."
        elif before.paused and after.running:
            self.status_message = "Timer resumed."

    def skip_phase(self) -> None:
        record = self.timer.skip()
        if record is None:
            self.status_message = "Start the timer before skipping a phase."
            return
        self._history_service.record(record)
        self.status_message = "Phase skipped."

    def stop_timer(self, reason: str = "stopped") -> None:
        record = self.timer.stop(reason=reason)
        if record is not None:
            self._history_service.record(record)
        self.status_message = "Timer stopped."

    def build_config_draft(self) -> ConfigValues:
        return replace(self.config)

    def save_config(self, values: ConfigValues) -> None:
        self.config = self._config_service.save(values)
        self.timer.apply_settings(self.config.to_timer_settings())
        self.status_message = "Configuration saved."

    def history_snapshot(self) -> HistorySnapshot:
        return self._history_service.snapshot(self.config)
