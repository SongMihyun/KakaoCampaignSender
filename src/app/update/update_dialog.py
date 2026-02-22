# src/app/update/update_dialog.py
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QHBoxLayout, QMessageBox
)

from app.update.updater import Updater, LatestManifest, DownloadCancelled


@dataclass(frozen=True)
class UpdateDecision:
    accepted: bool


class _UpdateWorker(QObject):
    progress = Signal(int, int)     # downloaded, total
    stage = Signal(str)            # text
    done = Signal(bool, str)       # ok, installer_path_or_err

    def __init__(self, updater: Updater, manifest: LatestManifest) -> None:
        super().__init__()
        self._updater = updater
        self._m = manifest
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _cancel_flag(self) -> bool:
        return bool(self._cancel)

    def run(self) -> None:
        try:
            self.stage.emit("업데이트 파일 다운로드 중…")
            path = self._updater.download_installer(
                self._m.url,
                on_progress=lambda d, t: self.progress.emit(int(d), int(t)),
                cancel_flag=self._cancel_flag,
            )
            self.stage.emit("무결성 검증 중…")
            if not self._updater.verify_sha256(path, self._m.sha256):
                self.done.emit(False, "설치파일 무결성(sha256) 검증에 실패했습니다.")
                return

            self.done.emit(True, path)
        except DownloadCancelled:
            self.done.emit(False, "사용자 취소")
        except Exception as e:
            self.done.emit(False, f"다운로드 실패: {e}")


class UpdateDialog(QDialog):
    def __init__(self, parent, *, updater: Updater, manifest: LatestManifest) -> None:
        super().__init__(parent)
        self.setWindowTitle("업데이트")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(420)

        self._updater = updater
        self._manifest = manifest

        self._label = QLabel("")
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)

        self._btn_cancel = QPushButton("취소")
        self._btn_cancel.clicked.connect(self._on_cancel)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"새 버전 {manifest.version}이 있습니다. 다운로드 후 자동 설치합니다."))
        if manifest.notes:
            lay.addWidget(QLabel(f"변경사항: {manifest.notes}"))
        lay.addWidget(self._label)
        lay.addWidget(self._bar)

        hl = QHBoxLayout()
        hl.addStretch(1)
        hl.addWidget(self._btn_cancel)
        lay.addLayout(hl)

        self._thread: QThread | None = None
        self._worker: _UpdateWorker | None = None
        self._installer_path: str = ""

    def start(self) -> bool:
        self._thread = QThread(self)
        self._worker = _UpdateWorker(self._updater, self._manifest)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.stage.connect(self._label.setText)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)

        self._thread.start()
        return bool(self.exec() == QDialog.DialogCode.Accepted)

    def _on_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._bar.setValue(max(0, min(100, pct)))
            self._label.setText(f"다운로드 {pct}% ({downloaded//1024//1024}MB / {total//1024//1024}MB)")
        else:
            # total unknown
            self._bar.setRange(0, 0)
            self._label.setText(f"다운로드 중… ({downloaded//1024//1024}MB)")

    def _on_done(self, ok: bool, result: str) -> None:
        try:
            if self._thread:
                self._thread.quit()
                self._thread.wait(2000)
        except Exception:
            pass

        if not ok:
            if result != "사용자 취소":
                QMessageBox.warning(self, "업데이트", result)
            self.reject()
            return

        self._installer_path = result
        self.accept()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._btn_cancel.setEnabled(False)
        self._label.setText("취소 처리 중…")