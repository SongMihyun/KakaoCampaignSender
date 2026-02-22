# src/ui/pages/contacts_page.py
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QLineEdit,
    QTableView, QMessageBox, QDialog
)
from PySide6.QtCore import Qt, QTimer, QModelIndex

from ui.pages.contacts_model import ContactsTableModel, Contact
from ui.pages.contacts_dialog import ContactDialog
from app.data.contacts_repo import ContactsRepo
from app.importers.contacts_excel import import_contacts_xlsx
from app.exporters.contacts_excel_export import export_contacts_xlsx, create_template_xlsx
from ui.pages.import_preview_dialog import ImportPreviewDialog

from ui.widgets.checkable_header import CheckableHeader
from ui.widgets.contacts_sort_proxy import ContactsSortProxyModel

from ui.utils.worker import run_bg

# ✅ 요즘 스타일(Windows 네이티브) + STA 분리 파일피커
from app.platform.win_file_picker import pick_open_file, pick_save_file, Filter

# ✅ 앱 전역 이벤트(대상자 변경 시 그룹관리 자동 갱신)
from ui.app_events import app_events


class ContactsPage(QWidget):
    def __init__(
        self,
        repo: ContactsRepo,
        on_status: Optional[Callable[[str], None]] = None
    ) -> None:
        super().__init__()
        self.setObjectName("Page")
        self._on_status = on_status or (lambda _: None)
        self.repo = repo

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("대상자 관리")
        title.setObjectName("PageTitle")

        desc = QLabel("로컬 SQLite 저장/조회 기반 대상자 관리 (엑셀 Import/Export + 체크 삭제).")
        desc.setObjectName("PageDesc")

        # 검색
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("이름/사번/전화/대리점/지사 검색")
        btn_search_clear = QPushButton("초기화")
        search_row.addWidget(self.search, 1)
        search_row.addWidget(btn_search_clear)

        # 버튼
        btn_row = QHBoxLayout()
        self.btn_template = QPushButton("샘플 서식 다운로드")
        self.btn_import = QPushButton("엑셀 가져오기")
        self.btn_export = QPushButton("엑셀 내보내기")
        self.btn_add = QPushButton("신규 추가")
        self.btn_edit = QPushButton("수정")
        self.btn_delete = QPushButton("삭제")
        self.btn_reload = QPushButton("새로고침")

        btn_row.addWidget(self.btn_template)
        btn_row.addWidget(self.btn_import)
        btn_row.addWidget(self.btn_export)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_reload)
        btn_row.addStretch(1)

        from PySide6.QtWidgets import QAbstractItemView
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSortingEnabled(True)

        # ✅ 인라인 편집은 사번만 허용(모델에서 제어)
        # 너무 민감하면 AllEditTriggers 대신 아래처럼 운영 권장
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        self.model = ContactsTableModel(rows=[])
        self.proxy = ContactsSortProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.table.setModel(self.proxy)

        # ✅ 행번호(세로 헤더) 숨김 → 체크박스가 화면상 맨앞
        self.table.verticalHeader().setVisible(False)

        # ✅ 체크박스/No 컬럼 폭
        self.table.setColumnWidth(0, 36)  # 체크박스
        self.table.setColumnWidth(1, 56)  # No

        # ✅ 체크박스 셀 클릭 시 토글(프록시 환경에서 가장 확실)
        self.table.clicked.connect(self._on_table_clicked)

        # ✅ 커스텀 체크 헤더 적용
        hdr = CheckableHeader(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(hdr)

        hdr.setSortIndicatorShown(True)
        hdr.setSectionsClickable(True)
        hdr.setStretchLastSection(True)

        hdr.toggled.connect(self._toggle_all_checked)

        self.model.dataChanged.connect(lambda *_: self._sync_header_checkbox())
        self.model.layoutChanged.connect(lambda *_: self._sync_header_checkbox())

        # ✅ 사번(인라인 편집) DB 반영
        self.model.dataChanged.connect(self._on_source_model_data_changed)

        # ✅ 초기 정렬: No 오름차순
        self.table.sortByColumn(1, Qt.AscendingOrder)

        # 레이아웃
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addLayout(search_row)
        layout.addLayout(btn_row)
        layout.addWidget(self.table, 1)

        # events
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        btn_search_clear.clicked.connect(self._clear_search)

        self.btn_template.clicked.connect(self._download_template)
        self.btn_import.clicked.connect(self._import_excel)
        self.btn_export.clicked.connect(self._export_excel)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_delete.clicked.connect(self._delete_checked)
        self.btn_reload.clicked.connect(self.reload)

        # 초기 로드
        self.reload()
        QTimer.singleShot(0, self._sync_header_checkbox)

    # -------------------------
    # Normalize helpers
    # -------------------------
    @staticmethod
    def _norm_optional(v: str | None) -> str:
        # ✅ 선택값: None/공백 -> ""
        return (v or "").strip()

    @staticmethod
    def _norm_required(v: str | None) -> str:
        return (v or "").strip()

    # -------------------------
    # Busy / Error helpers
    # -------------------------
    def _set_busy(self, busy: bool) -> None:
        for b in [
            self.btn_template, self.btn_import, self.btn_export,
            self.btn_add, self.btn_edit, self.btn_delete, self.btn_reload
        ]:
            b.setEnabled(not busy)

    def _show_bg_error(self, tb: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "오류", tb)

    # -------------------------
    # Data
    # -------------------------
    def reload(self) -> None:
        rows = self.repo.list_all()
        contacts = [
            Contact(
                id=r.id,
                emp_id=(r.emp_id or ""),     # ✅ emp_id 비필수
                name=r.name,
                phone=r.phone or "",
                agency=r.agency or "",       # ✅ 비필수
                branch=r.branch or ""        # ✅ 비필수
            )
            for r in rows
        ]
        self.model.reset_rows(contacts)
        self._on_status(f"대상자 로드: {len(contacts)}건")
        self._sync_header_checkbox()

    def _clear_search(self) -> None:
        self.search.setText("")
        self._on_status("검색 조건 초기화")
        self._sync_header_checkbox()

    def _selected_source_rows(self) -> list[int]:
        rows = []
        for idx in self.table.selectionModel().selectedRows():
            src = self.proxy.mapToSource(idx)
            rows.append(src.row())
        return sorted(set(rows))

    # -------------------------
    # DB sync for inline edit (emp_id)
    # -------------------------
    def _on_source_model_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, roles=None) -> None:
        # ✅ 사번 컬럼(2) 변경 시 DB에 즉시 반영
        if not top_left.isValid():
            return

        # 여러 셀 범위 변경 가능성 방어
        for row in range(top_left.row(), bottom_right.row() + 1):
            for col in range(top_left.column(), bottom_right.column() + 1):
                if col != 2:
                    continue  # 사번만

                c = self.model.contact_at(row)

                # 사번/대리점/지사명은 선택값(빈값 허용)
                emp_id = self._norm_optional(c.emp_id)
                name = self._norm_required(c.name)
                phone = self._norm_optional(c.phone)
                agency = self._norm_optional(c.agency)
                branch = self._norm_optional(c.branch)

                # name이 비어있을 리는 없지만 방어
                if not name:
                    QMessageBox.warning(self, "입력 오류", "이름은 필수입니다.")
                    self.reload()
                    return

                try:
                    # 기존 update 시그니처 사용(전체 필드 전달)
                    self.repo.update(
                        row_id=c.id,
                        emp_id=emp_id,
                        name=name,
                        phone=phone,
                        agency=agency,
                        branch=branch,
                    )
                except ValueError as e:
                    # ✅ DB단 중복/검증 실패 시 롤백
                    QMessageBox.warning(self, "중복 오류", str(e))
                    self.reload()
                    return
                except Exception as e:
                    QMessageBox.critical(self, "오류", f"DB 저장 실패:\n{e}")
                    self.reload()
                    return

                # ✅ 대상자 변경 이벤트 -> 그룹관리 즉시 갱신
                app_events.contacts_changed.emit()
                self._on_status(f"사번 변경 저장: {c.name} ({emp_id})")

    # -------------------------
    # CRUD
    # -------------------------
    def _add(self) -> None:
        dlg = ContactDialog("대상자 추가", parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_contact()

            # ✅ 필수/선택 정규화
            data["name"] = self._norm_required(data.get("name"))
            data["emp_id"] = self._norm_optional(data.get("emp_id"))     # 비필수
            data["phone"] = self._norm_optional(data.get("phone"))
            data["agency"] = self._norm_optional(data.get("agency"))     # 비필수
            data["branch"] = self._norm_optional(data.get("branch"))     # 비필수

            if not data["name"]:
                QMessageBox.warning(self, "입력 오류", "이름은 필수입니다.")
                return

            try:
                new_id = self.repo.insert(
                    emp_id=data["emp_id"],
                    name=data["name"],
                    phone=data["phone"],
                    agency=data["agency"],
                    branch=data["branch"],
                )
            except ValueError as e:
                QMessageBox.warning(self, "중복 오류", str(e))
                return

            c = Contact(
                id=new_id,
                emp_id=data["emp_id"],
                name=data["name"],
                phone=data["phone"],
                agency=data["agency"],
                branch=data["branch"],
            )
            self.model.add_contact(c)

            # ✅ 대상자 변경 이벤트 발생 -> 그룹관리 즉시 갱신
            app_events.contacts_changed.emit()

            if self.search.text().strip():
                self.search.setText("")

            emp_disp = c.emp_id if c.emp_id else "(사번없음)"
            self._on_status(f"추가 완료: {c.name} ({emp_disp})")
            self._sync_header_checkbox()

    def _edit(self) -> None:
        rows = self._selected_source_rows()
        if len(rows) != 1:
            QMessageBox.information(self, "안내", "수정은 1건만 선택하세요.")
            return

        row = rows[0]
        preset = self.model.contact_at(row)

        dlg = ContactDialog(
            "대상자 수정",
            preset=type("Tmp", (), {
                "emp_id": preset.emp_id, "name": preset.name,
                "phone": preset.phone, "agency": preset.agency, "branch": preset.branch
            })(),
            parent=self
        )

        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_contact()

            # ✅ 필수/선택 정규화
            data["name"] = self._norm_required(data.get("name"))
            data["emp_id"] = self._norm_optional(data.get("emp_id"))     # 비필수
            data["phone"] = self._norm_optional(data.get("phone"))
            data["agency"] = self._norm_optional(data.get("agency"))     # 비필수
            data["branch"] = self._norm_optional(data.get("branch"))     # 비필수

            if not data["name"]:
                QMessageBox.warning(self, "입력 오류", "이름은 필수입니다.")
                return

            try:
                self.repo.update(
                    row_id=preset.id,
                    emp_id=data["emp_id"],
                    name=data["name"],
                    phone=data["phone"],
                    agency=data["agency"],
                    branch=data["branch"],
                )
            except ValueError as e:
                QMessageBox.warning(self, "중복 오류", str(e))
                return

            self.reload()

            # ✅ 대상자 변경 이벤트 발생 -> 그룹관리 즉시 갱신
            app_events.contacts_changed.emit()

            emp_disp = data["emp_id"] if data["emp_id"] else "(사번없음)"
            self._on_status(f"수정 완료: {data['name']} ({emp_disp})")

    def _delete_checked(self) -> None:
        ids = self.model.checked_ids()
        if not ids:
            QMessageBox.information(self, "안내", "삭제할 항목을 체크하세요.")
            return

        ok = QMessageBox.question(
            self,
            "삭제 확인",
            f"{len(ids)}건을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        self.repo.delete_many(ids)
        self.reload()

        # ✅ 대상자 변경 이벤트 발생 -> 그룹관리 즉시 갱신
        app_events.contacts_changed.emit()

        self._on_status(f"삭제 완료: {len(ids)}건")

    # -------------------------
    # Excel (Import)
    # -------------------------
    def _import_excel(self) -> None:
        # 1) 파일 선택 (UI 스레드)
        try:
            path = pick_open_file(
                title="대상자 엑셀 선택",
                filters=[Filter("Excel Files", "*.xlsx"), Filter("All Files", "*.*")],
                default_ext="xlsx",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기 실행 실패:\n{e}")
            return

        if not path:
            return

        self._set_busy(True)
        self._on_status("엑셀 읽는 중...")

        # 2) 엑셀 파싱 (BG)
        def parse_job():
            return import_contacts_xlsx(path)

        # 3) 파싱 완료 -> 미리보기( UI ) -> 저장 클릭 시 DB 저장(BG)
        def parse_done(result):
            if result.errors:
                self._set_busy(False)
                QMessageBox.warning(self, "엑셀 오류", "\n".join(result.errors))
                return

            if not result.rows:
                self._set_busy(False)
                QMessageBox.information(self, "안내", "등록할 데이터가 없습니다.")
                return

            preview = ImportPreviewDialog(result.rows, parent=self)
            r = preview.exec()

            if r != QDialog.Accepted:
                self._set_busy(False)
                self._on_status("엑셀 등록 취소")
                return

            self._on_status("DB 저장 중...")

            def db_job():
                return self.repo.insert_many(result.rows)

            def db_done(res):
                inserted, dup_skipped = res
                self.reload()

                # ✅ 대상자 변경 이벤트 발생 -> 그룹관리 즉시 갱신
                app_events.contacts_changed.emit()

                self._set_busy(False)

                msg = f"엑셀 등록 완료: {inserted}건"
                if dup_skipped:
                    msg += f" / 중복 스킵 {dup_skipped}건(사번/전화번호)"
                self._on_status(msg)
                QMessageBox.information(self, "완료", msg)

            run_bg(db_job, on_done=db_done, on_error=self._show_bg_error)

        run_bg(parse_job, on_done=parse_done, on_error=self._show_bg_error)

    # -------------------------
    # Excel (Template/Export)
    # -------------------------
    def _download_template(self) -> None:
        try:
            path = pick_save_file(
                title="샘플 서식 저장",
                filters=[Filter("Excel Files", "*.xlsx"), Filter("All Files", "*.*")],
                default_filename="contacts_template.xlsx",
                default_ext="xlsx",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 위치 선택기 실행 실패:\n{e}")
            return

        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            create_template_xlsx(path)
            self._on_status(f"샘플 서식 저장 완료: {path}")
            QMessageBox.information(self, "완료", "샘플 서식을 저장했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"샘플 서식 생성 실패:\n{e}")

    def _export_excel(self) -> None:
        try:
            path = pick_save_file(
                title="대상자 엑셀 내보내기",
                filters=[Filter("Excel Files", "*.xlsx"), Filter("All Files", "*.*")],
                default_filename="contacts_export.xlsx",
                default_ext="xlsx",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 위치 선택기 실행 실패:\n{e}")
            return

        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        self._set_busy(True)
        self._on_status("엑셀 내보내기 준비 중...")

        def job():
            export_rows = []
            for pr in range(self.proxy.rowCount()):
                idx = self.proxy.index(pr, 2)
                src_idx = self.proxy.mapToSource(idx)
                c = self.model.contact_at(src_idx.row())
                export_rows.append((c.emp_id, c.name, c.phone, c.agency, c.branch))

            export_contacts_xlsx(path, export_rows)
            return len(export_rows)

        def done(cnt: int):
            self._set_busy(False)
            self._on_status(f"엑셀 내보내기 완료: {cnt}건")
            QMessageBox.information(self, "완료", f"엑셀 내보내기 완료: {cnt}건")

        run_bg(job, on_done=done, on_error=self._show_bg_error)

    # -------------------------
    # Header checkbox logic
    # -------------------------
    def _toggle_all_checked(self, checked: bool) -> None:
        if checked:
            ids = []
            for pr in range(self.proxy.rowCount()):
                idx = self.proxy.index(pr, 2)
                src = self.proxy.mapToSource(idx)
                c = self.model.contact_at(src.row())
                ids.append(c.id)
            self.model.set_checked_ids(ids)
        else:
            self.model.clear_checked()
        self._sync_header_checkbox()

    def _sync_header_checkbox(self) -> None:
        header = self.table.horizontalHeader()
        if not isinstance(header, CheckableHeader):
            return

        total_visible = self.proxy.rowCount()
        if total_visible == 0:
            header.set_check_state(Qt.Unchecked)
            return

        checked_visible = 0
        checked_set = set(self.model.checked_ids())

        for pr in range(total_visible):
            idx = self.proxy.index(pr, 2)
            src = self.proxy.mapToSource(idx)
            c = self.model.contact_at(src.row())
            if c.id in checked_set:
                checked_visible += 1

        if checked_visible == 0:
            header.set_check_state(Qt.Unchecked)
        elif checked_visible == total_visible:
            header.set_check_state(Qt.Checked)
        else:
            header.set_check_state(Qt.PartiallyChecked)

    def _on_table_clicked(self, index) -> None:
        if index.column() != 0:
            return

        src = self.proxy.mapToSource(index)
        if not src.isValid():
            return

        current = self.model.data(src, Qt.CheckStateRole)
        new_state = Qt.Unchecked if current == Qt.Checked else Qt.Checked
        self.model.setData(src, new_state, Qt.CheckStateRole)
        self._sync_header_checkbox()
