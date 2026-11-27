"""Run file parsing off the GUI thread and deliver results to the window."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from svdstudio.application.project import open_svd


class _Worker(QThread):
    completed = Signal(object, object)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self._operation = operation

    def run(self):
        try:
            result = self._operation()
        except Exception as error:  # noqa: BLE001 - transfer failures across the thread boundary
            self.completed.emit(None, error)
        else:
            self.completed.emit(result, None)


class _FileJob(QObject):
    def __init__(self, window, operation, callback):
        super().__init__(window)
        self._callback = callback
        self.worker = _Worker(operation, self)
        self.worker.completed.connect(self.deliver)
        self.worker.finished.connect(self.deleteLater)

    @Slot(object, object)
    def deliver(self, result, error):
        self._callback(result, error)


def run_async(window, operation, callback, status: str, title: str):
    job = _FileJob(window, operation, callback)
    job.setObjectName(title)
    window.statusBar().showMessage(status)
    job.worker.start()


def load_svd_async(window, path, callback):
    def deliver(result, error):
        state, issues = result if result is not None else (None, [])
        callback(state, issues, error)

    run_async(window, lambda: open_svd(path), deliver, f"Loading {path}…", "Open SVD")


def wait_for_file_jobs(window):
    for job in window.findChildren(_FileJob):
        job.worker.wait()
