"""Background worker for update checks."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from gui.update_checker import UpdateResult, check_for_update


class UpdateWorker(QThread):
    """Run update checks away from the UI thread."""

    finished_ok = Signal(object)  # UpdateResult

    def __init__(self, current_version: str, repository: str, channel: str, parent=None) -> None:
        super().__init__(parent)
        self._current_version = current_version
        self._repository = repository
        self._channel = channel

    def run(self) -> None:
        try:
            result: UpdateResult = check_for_update(
                current_version=self._current_version,
                repository=self._repository,
                channel=self._channel,
            )
        except Exception as exc:
            result = UpdateResult(
                current_version=self._current_version,
                latest=None,
                error=str(exc),
            )
        self.finished_ok.emit(result)
