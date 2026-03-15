from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QLabel, QMessageBox

from backend.integrations.windows.win_file_picker import Filter, pick_save_file
from frontend.pages.contacts.excel_editor_dialog import ExcelEditorDialog


class TabularEditorDialog(ExcelEditorDialog):
    def __init__(
        self,
        grid,
        *,
        editor_title: str,
        editor_kind_label: str,
        save_func: Callable,
        suggest_save_path_func: Callable[[str], str],
        export_filters: list[Filter],
        export_default_ext: str,
        parent=None,
    ) -> None:
        try:
            super().__init__(grid, parent=parent)
        except TypeError:
            super().__init__(grid, grid.source_path, parent=parent)

        self._editor_title_text = editor_title
        self._editor_kind_label = editor_kind_label
        self._save_func = save_func
        self._current_save_path = suggest_save_path_func(grid.source_path)
        self._export_filters = export_filters
        self._export_default_ext = export_default_ext.lstrip(".")
        self._warned_value_only = False

        self._retitle_ui()

    def _retitle_ui(self) -> None:
        self.setWindowTitle(f"{self._editor_title_text} - {Path(self._grid.source_path).name}")
        for label in self.findChildren(QLabel):
            text = label.text().strip()
            if text == "엑셀 미리보기/편집":
                label.setText(self._editor_title_text)
            elif text.startswith("원본 파일:"):
                label.setText(
                    f"원본 파일: {self._grid.source_path}  |  값 기준 경량 편집 모드 ({self._editor_kind_label} 저장/내보내기)"
                )

    def _confirm_value_only_save(self) -> bool:
        if self._warned_value_only:
            return True
        msg = (
            f"현재 편집기는 {self._editor_kind_label} 값 기준 경량 편집 모드입니다.\n\n"
            "저장/내보내기 시 표/셀 값 중심으로 새 파일을 생성합니다.\n"
            "복잡한 서식/원본 구조는 일부 단순화될 수 있습니다.\n\n"
            "계속 진행하시겠습니까?"
        )
        ok = QMessageBox.question(self, "저장 방식 안내", msg, QMessageBox.Yes | QMessageBox.No)
        if ok == QMessageBox.Yes:
            self._warned_value_only = True
            return True
        return False

    def _save_to_default(self) -> None:
        if not self._confirm_value_only_save():
            return
        target = self._current_save_path
        try:
            self._save_func(self._grid, target)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패:\n{e}")
            return
        self._set_status(f"저장 완료: {target}")
        QMessageBox.information(self, "완료", f"저장 완료\n\n{target}")

    def _export_as(self) -> None:
        if not self._confirm_value_only_save():
            return
        default_name = f"{Path(self._current_save_path).stem}.{self._export_default_ext}"
        try:
            path = pick_save_file(
                title="편집 데이터 내보내기",
                filters=self._export_filters,
                default_filename=default_name,
                default_ext=self._export_default_ext,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 위치 선택기 실행 실패:\n{e}")
            return
        if not path:
            return
        expected = f".{self._export_default_ext}"
        if Path(path).suffix.lower() != expected.lower():
            path += expected
        try:
            self._save_func(self._grid, path)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"내보내기 실패:\n{e}")
            return
        self._current_save_path = path
        self._set_status(f"내보내기 완료: {path}")
        QMessageBox.information(self, "완료", f"내보내기 완료\n\n{path}")


class WordEditorDialog(TabularEditorDialog):
    def __init__(self, grid, save_func, suggest_save_path_func, parent=None) -> None:
        super().__init__(
            grid,
            editor_title="워드 미리보기/편집",
            editor_kind_label="워드",
            save_func=save_func,
            suggest_save_path_func=suggest_save_path_func,
            export_filters=[Filter("Word Files", "*.docx"), Filter("All Files", "*.*")],
            export_default_ext="docx",
            parent=parent,
        )


class TextEditorDialog(TabularEditorDialog):
    def __init__(self, grid, save_func, suggest_save_path_func, parent=None) -> None:
        super().__init__(
            grid,
            editor_title="메모장 미리보기/편집",
            editor_kind_label="메모장",
            save_func=save_func,
            suggest_save_path_func=suggest_save_path_func,
            export_filters=[
                Filter("Text Files", "*.txt"),
                Filter("CSV Files", "*.csv"),
                Filter("TSV Files", "*.tsv"),
                Filter("All Files", "*.*"),
            ],
            export_default_ext="txt",
            parent=parent,
        )
