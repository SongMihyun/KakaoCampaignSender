# src/ui/pages/logs_page.py
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Callable, Dict, Any

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton,
    QTableView, QAbstractItemView, QComboBox, QLineEdit,
    QFileDialog, QMessageBox, QTextEdit, QSplitter
)

from app.data.send_logs_repo import SendLogsRepo
from app.paths import user_data_dir

# ✅ 캠페인 미리보기 재사용
from ui.pages.campaign_preview_dialog import CampaignPreviewDialog



class LogsPage(QWidget):
    """
    로그/리포트 화면
    - send_logs(DB) 조회/필터/CSV export/전체 삭제
    - 발송 리포트(JSON) 선택 시: 표(Table)에 리포트 수신자 결과를 표시
    - ✅ 리포트 표에서 행 클릭 시: 보낸 캠페인 미리보기 팝업
        - 리포트에 image_bytes가 없을 수 있으므로, campaigns_repo가 주입되면 DB에서 캠페인 아이템 재조회하여 표시
    - 전체 리셋(로컬 데이터 삭제 후 종료) 버튼 포함
    """

    def __init__(
            self,
            *,
            logs_repo: SendLogsRepo,
            campaigns_repo=None,
            on_reset_all: Optional[Callable[[], None]] = None
    ) -> None:
        super().__init__()
        self.setObjectName("Page")

        self.logs_repo = logs_repo
        self.campaigns_repo = campaigns_repo
        self._on_reset_all = on_reset_all

        self._active_source: str = "DB"

        self._report_path: Optional[Path] = None
        self._report_obj: Optional[Dict[str, Any]] = None
        self._report_rows: List[Dict[str, Any]] = []

        # ✅ 현재 표에 렌더된 rows (클릭 시 원본 접근)
        self._shown_rows: List[Dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("로그/리포트")
        title.setObjectName("PageTitle")
        desc = QLabel("성공/실패/NOT_FOUND/사유/재시도 대상 관리 및 결과 내보내기 + 로그 파일/리포트 내용 확인.")
        desc.setObjectName("PageDesc")

        root.addWidget(title)
        root.addWidget(desc)

        # -------------------------
        # Report file row
        # -------------------------
        report_row = QHBoxLayout()
        report_row.setSpacing(8)

        report_row.addWidget(QLabel("발송 리포트 파일"), 0)

        self.cbo_reports = QComboBox()
        self.cbo_reports.setMinimumWidth(520)

        self.btn_reports_refresh = QPushButton("리포트 새로고침")
        report_row.addWidget(self.cbo_reports, 1)
        report_row.addWidget(self.btn_reports_refresh, 0)

        root.addLayout(report_row)

        # -------------------------
        # Filter row
        # -------------------------
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.cbo_status = QComboBox()
        self.cbo_status.addItem("전체", None)
        self.cbo_status.addItem("성공(SUCCESS)", "SUCCESS")
        self.cbo_status.addItem("실패(FAIL)", "FAIL")
        self.cbo_status.addItem("대화방없음(NOT_FOUND)", "NOT_FOUND")
        self.cbo_status.addItem("스킵(SKIP)", "SKIP")
        self.cbo_status.addItem("말미재시도예약(TAIL_RETRY_SCHEDULED)", "TAIL_RETRY_SCHEDULED")
        self.cbo_status.addItem("말미재시도성공(SUCCESS(TAIL_RETRY))", "SUCCESS(TAIL_RETRY)")
        self.cbo_status.addItem("말미재시도실패(FAIL(TAIL_RETRY))", "FAIL(TAIL_RETRY)")

        self.txt_keyword = QLineEdit()
        self.txt_keyword.setPlaceholderText("검색: 수신자/사유/채널 키워드")

        self.btn_refresh = QPushButton("새로고침")
        self.btn_fail_only = QPushButton("실패건 보기")
        self.btn_export = QPushButton("CSV 내보내기")

        filter_row.addWidget(QLabel("상태"))
        filter_row.addWidget(self.cbo_status, 0)
        filter_row.addWidget(self.txt_keyword, 1)
        filter_row.addWidget(self.btn_refresh)
        filter_row.addWidget(self.btn_fail_only)
        filter_row.addWidget(self.btn_export)

        root.addLayout(filter_row)

        # -------------------------
        # Split: Table + Viewer
        # -------------------------
        splitter = QSplitter(Qt.Vertical)

        # ---- Table
        table_wrap = QWidget()
        tv = QVBoxLayout(table_wrap)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(8)

        self.tbl = QTableView()
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSortingEnabled(False)

        self.model = QStandardItemModel(0, 11, self)
        self.model.setHorizontalHeaderLabels([
            "ID", "시간", "캠페인ID", "배치ID", "채널", "수신자",
            "상태", "사유", "시도", "메시지길이", "이미지수"
        ])
        self.tbl.setModel(self.model)

        self.tbl.setColumnWidth(0, 60)
        self.tbl.setColumnWidth(1, 150)
        self.tbl.setColumnWidth(2, 90)
        self.tbl.setColumnWidth(3, 140)
        self.tbl.setColumnWidth(4, 120)
        self.tbl.setColumnWidth(5, 160)
        self.tbl.setColumnWidth(6, 140)
        self.tbl.setColumnWidth(7, 360)
        self.tbl.setColumnWidth(8, 60)
        self.tbl.setColumnWidth(9, 90)
        self.tbl.setColumnWidth(10, 70)
        self.tbl.horizontalHeader().setStretchLastSection(True)

        tv.addWidget(self.tbl, 1)
        splitter.addWidget(table_wrap)

        # ---- Viewer
        viewer_wrap = QWidget()
        vv = QVBoxLayout(viewer_wrap)
        vv.setContentsMargins(0, 0, 0, 0)
        vv.setSpacing(8)

        viewer_title_row = QHBoxLayout()
        viewer_title_row.setSpacing(8)

        viewer_title_row.addWidget(QLabel("내용 보기(리포트/파일/상세)"), 0)

        self.btn_open_log_file = QPushButton("로그 파일 열기")
        self.btn_open_wipe_log = QPushButton("전체삭제 로그 보기")
        self.btn_show_selected_detail = QPushButton("선택 행 상세 보기")
        viewer_title_row.addStretch(1)
        viewer_title_row.addWidget(self.btn_show_selected_detail)
        viewer_title_row.addWidget(self.btn_open_wipe_log)
        viewer_title_row.addWidget(self.btn_open_log_file)

        vv.addLayout(viewer_title_row)

        self.txt_log_view = QTextEdit()
        self.txt_log_view.setReadOnly(True)
        self.txt_log_view.setPlaceholderText(
            "1) 상단 '발송 리포트 파일' 선택 → 가운데 표에 리포트 상세 표시\n"
            "2) 표 행 클릭 → 보낸 캠페인 미리보기(팝업)\n"
            "3) '선택 행 상세 보기'로 행 상세 확인\n"
        )
        vv.addWidget(self.txt_log_view, 1)

        splitter.addWidget(viewer_wrap)

        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)

        root.addWidget(splitter, 1)

        # -------------------------
        # Footer buttons
        # -------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_retry = QPushButton("재시도(실패 대상 목록 추출)")
        btn_row.addWidget(self.btn_retry)

        btn_row.addStretch(1)

        self.reset_btn = QPushButton("전체 삭제 (send_logs + 리포트 초기화)")
        self.reset_btn.setStyleSheet("background:#fee2e2; color:#b91c1c;")
        btn_row.addWidget(self.reset_btn)

        self.btn_reset_all = QPushButton("전체 리셋 (로컬 데이터 삭제 후 종료)")
        self.btn_reset_all.setStyleSheet("background:#dc2626; color:#ffffff; font-weight:700;")
        self.btn_reset_all.setEnabled(self._on_reset_all is not None)
        btn_row.addWidget(self.btn_reset_all)

        root.addLayout(btn_row)

        # -------------------------
        # Wire (✅ tbl 생성 이후 연결)
        # -------------------------
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_fail_only.clicked.connect(self._set_fail_only)
        self.btn_export.clicked.connect(self.export_csv)
        self.reset_btn.clicked.connect(self.reset_logs_and_reports)
        self.btn_retry.clicked.connect(self.show_retry_targets)

        self.btn_open_log_file.clicked.connect(self.open_log_file)
        self.btn_open_wipe_log.clicked.connect(self.open_wipe_log)
        self.btn_show_selected_detail.clicked.connect(self.show_selected_detail)
        self.btn_reset_all.clicked.connect(self.reset_all_app)

        self.cbo_status.currentIndexChanged.connect(lambda _: self.refresh())
        self.txt_keyword.returnPressed.connect(self.refresh)
        self.tbl.selectionModel().selectionChanged.connect(lambda *_: self._auto_show_reason_preview())

        # ✅ 표 클릭 -> 캠페인 미리보기 팝업
        self.tbl.clicked.connect(self._on_table_clicked)

        # ✅ 더블클릭 -> 상세 팝업
        self.tbl.doubleClicked.connect(self._on_table_double_clicked)

        self.btn_reports_refresh.clicked.connect(self.refresh_reports)
        self.cbo_reports.currentIndexChanged.connect(lambda _: self.open_selected_report())

        self.refresh_reports()
        self.refresh()

    # -------------------------
    # Reports
    # -------------------------
    def _reports_dir(self) -> Path:
        # 스크린샷/실경로 기준 Reports 사용
        d = Path(user_data_dir()) / "Reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def refresh_reports(self) -> None:
        self.cbo_reports.blockSignals(True)
        self.cbo_reports.clear()
        self.cbo_reports.addItem("(리포트 선택: 선택 시 표에 상세 표시)", None)

        d = self._reports_dir()
        files = sorted(d.glob("send_report_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[:500]:
            try:
                ts = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                label = f"{p.name}  ({ts})"
            except Exception:
                label = p.name
            self.cbo_reports.addItem(label, str(p))

        self.cbo_reports.blockSignals(False)

    def _build_report_rows(self, obj: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []

        started_at = str(obj.get("started_at", "") or obj.get("created_at", "") or "")
        ended_at = str(obj.get("ended_at", "") or "")
        ts_base = ended_at or started_at

        lists = obj.get("lists", []) or []
        if not isinstance(lists, list):
            lists = []

        for lst in lists:
            if not isinstance(lst, dict):
                continue

            title = str(lst.get("title", "") or "")
            send_list_id = lst.get("send_list_id", "")
            group_name = str(lst.get("group_name", "") or "")
            campaign_id = lst.get("campaign_id", "")
            campaign_name = str(lst.get("campaign_name", "") or "")

            items = lst.get("campaign_items", []) or lst.get("items", []) or []
            if not isinstance(items, list):
                items = []

            message_len = 0
            image_count = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                if str(it.get("item_type", "")).upper() == "TEXT":
                    message_len += len(str(it.get("text", "") or ""))
                elif str(it.get("item_type", "")).upper() == "IMAGE":
                    image_count += 1

            batch_id = f"send_list:{send_list_id}" if send_list_id != "" else str(obj.get("run_id", "") or "")

            recipients = lst.get("recipients", []) or lst.get("results", []) or []
            if not isinstance(recipients, list):
                recipients = []

            list_meta = {
                "title": title,
                "send_list_id": send_list_id,
                "group_name": group_name,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "campaign_items": items,
            }

            for r in recipients:
                if not isinstance(r, dict):
                    continue

                name = str(r.get("name", "") or "")
                emp_id = str(r.get("emp_id", "") or "")
                phone = str(r.get("phone", "") or "")
                recipient = name
                if emp_id or phone:
                    recipient = f"{name} ({emp_id}/{phone})".strip()

                status = str(r.get("status", "") or "").upper()
                reason = str(r.get("reason", "") or "")
                attempt = int(r.get("attempt", 0) or 0)

                channel = group_name or title or campaign_name
                ts = str(r.get("ts", "") or ts_base)

                rows.append({
                    "id": "",
                    "ts": ts,
                    "campaign_id": campaign_id,
                    "batch_id": batch_id,
                    "channel": channel,
                    "recipient": recipient,
                    "status": status,
                    "reason": reason,
                    "attempt": attempt,
                    "message_len": message_len,
                    "image_count": image_count,
                    "_list_title": title,
                    "_campaign_name": campaign_name,
                    "_group_name": group_name,
                    "_list_meta": list_meta,
                })

        return rows

    def open_selected_report(self) -> None:
        # ✅ 콤보 변경 중 재진입 방지
        self.cbo_reports.blockSignals(True)
        try:
            path = self.cbo_reports.currentData()
        finally:
            self.cbo_reports.blockSignals(False)

        if not path:
            self._active_source = "DB"
            self._report_path = None
            self._report_obj = None
            self._report_rows = []
            self._shown_rows = []
            self.txt_log_view.setPlainText("DB 로그 모드로 전환되었습니다.")
            self.refresh()
            return

        p = Path(str(path))
        if not p.exists():
            QMessageBox.information(self, "안내", "리포트 파일이 존재하지 않습니다.")
            return

        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"리포트 로드 실패\n{p}\n\n{e}")
            return

        self._active_source = "REPORT"
        self._report_path = p
        self._report_obj = obj
        self._report_rows = self._build_report_rows(obj)

        # ✅ 전환 안내는 먼저 표시(이후 selectionChanged가 reason으로 덮을 수 있으니 refresh 후 다시 세팅)
        self.txt_log_view.setPlainText(
            f"[SEND REPORT]\n- file: {str(p)}\n\n"
            "✅ 표는 리포트 상세로 전환되었습니다.\n"
            "✅ 표 행 클릭 → 보낸 캠페인 미리보기(팝업)\n"
        )

        self.refresh()

        # ✅ refresh 이후에도 안내가 보이게 유지(첫 행 자동선택/preview 때문에 덮이는 케이스 방지)
        self.txt_log_view.setPlainText(
            f"[SEND REPORT]\n- file: {str(p)}\n\n"
            "✅ 표는 리포트 상세로 전환되었습니다.\n"
            "✅ 표 행 클릭 → 보낸 캠페인 미리보기(팝업)\n"
        )

    # -------------------------
    # Table helpers
    # -------------------------
    def _apply_filters_to_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        status = self.cbo_status.currentData()
        keyword = (self.txt_keyword.text() or "").strip().lower()

        out: List[Dict[str, Any]] = []
        for r in rows:
            st = str(r.get("status", "") or "").upper()

            if status:
                if not st.startswith(str(status).upper()):
                    continue

            if keyword:
                hay = " ".join([
                    str(r.get("channel", "") or ""),
                    str(r.get("recipient", "") or ""),
                    str(r.get("reason", "") or ""),
                    str(r.get("_list_title", "") or ""),
                    str(r.get("_campaign_name", "") or ""),
                    str(r.get("_group_name", "") or ""),
                ]).lower()
                if keyword not in hay:
                    continue

            out.append(r)
        return out

    def _render_rows_to_table(self, rows: List[Dict[str, Any]]) -> None:
        self.model.setRowCount(0)
        self._shown_rows = list(rows)

        def _it(v: object) -> QStandardItem:
            x = QStandardItem("" if v is None else str(v))
            x.setEditable(False)
            return x

        for r in rows:
            self.model.appendRow([
                _it(r.get("id", "")),
                _it(r.get("ts", "")),
                _it(r.get("campaign_id", "")),
                _it(r.get("batch_id", "")),
                _it(r.get("channel", "")),
                _it(r.get("recipient", "")),
                _it(r.get("status", "")),
                _it(r.get("reason", "")),
                _it(r.get("attempt", "")),
                _it(r.get("message_len", "")),
                _it(r.get("image_count", "")),
            ])

        self._auto_show_reason_preview()

    # -------------------------
    # ✅ 표 클릭 → 캠페인 미리보기
    # -------------------------
    def _on_table_clicked(self, index: QModelIndex) -> None:
        if self._active_source != "REPORT":
            return
        self._open_campaign_preview_for_row(index.row())

    def _on_table_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row = index.row()

        # 현재 표에 렌더된 원본 row 접근
        detail: dict = {}
        if self._active_source == "REPORT":
            if 0 <= row < len(self._shown_rows):
                r = dict(self._shown_rows[row])
                # 상세 팝업에 캠페인명/그룹명/아이템 스냅샷도 넣어주기
                list_meta = r.get("_list_meta") if isinstance(r.get("_list_meta"), dict) else {}
                detail = {
                    "ts": r.get("ts", ""),
                    "channel": r.get("channel", ""),
                    "recipient": r.get("recipient", ""),
                    "status": r.get("status", ""),
                    "reason": r.get("reason", ""),
                    "attempt": r.get("attempt", ""),
                    "message_len": r.get("message_len", ""),
                    "image_count": r.get("image_count", ""),
                    "campaign_id": r.get("campaign_id", ""),
                    "campaign_name": r.get("_campaign_name", ""),
                    "campaign_title": f"{r.get('_group_name', '')} + {r.get('_campaign_name', '')}".strip(" +"),
                    "campaign_items": (list_meta.get("campaign_items") or []),
                }
        else:
            # DB 모드: 현재 표 컬럼에서 읽기
            data = self._selected_row_values()
            if not data:
                return
            # DB 로그에 campaign_name이 없다면, channel이나 batch_id로 대체 표기
            detail = {
                "ts": data.get("ts", ""),
                "channel": data.get("channel", ""),
                "recipient": data.get("recipient", ""),
                "status": data.get("status", ""),
                "reason": data.get("reason", ""),
                "attempt": data.get("attempt", ""),
                "message_len": data.get("message_len", ""),
                "image_count": data.get("image_count", ""),
                "campaign_id": data.get("campaign_id", ""),
                "campaign_name": "(DB 로그) 캠페인명 미기록",
                "campaign_title": str(data.get("channel", "") or "캠페인"),
            }

        from ui.pages.log_detail_dialog import LogDetailDialog
        dlg = LogDetailDialog(
            title="발송 상세",
            detail=detail,
            campaigns_repo=self.campaigns_repo,  # 있으면 DB 재조회 가능
            parent=self,
        )
        dlg.exec()

    def _items_need_bytes(self, items: List[Any]) -> bool:
        """
        CampaignPreviewDialog이 이미지를 렌더링하려면 image_bytes가 필요.
        리포트에는 없는 경우가 많음 -> True면 DB 재조회 필요.

        ✅ dict 뿐 아니라, CampaignItemRow 같은 객체(item_type/image_bytes 속성)도 대응.
        """
        for it in items:
            # dict 경로(리포트)
            if isinstance(it, dict):
                if str(it.get("item_type", "")).upper() != "IMAGE":
                    continue
                b = it.get("image_bytes", None)
                if isinstance(b, (bytes, bytearray)) and len(b) > 0:
                    continue
                return True

            # object 경로(DB/Repo)
            typ = str(getattr(it, "item_type", "") or "").upper()
            if typ != "IMAGE":
                continue
            b2 = getattr(it, "image_bytes", None)
            if isinstance(b2, (bytes, bytearray)) and len(b2) > 0:
                continue
            return True

        return False

    def _open_campaign_preview_for_row(self, row: int) -> None:
        if row < 0 or row >= len(self._shown_rows):
            return

        r = self._shown_rows[row]
        list_meta = r.get("_list_meta")
        if not isinstance(list_meta, dict):
            QMessageBox.information(self, "안내", "캠페인 정보가 없습니다.")
            return

        items = list_meta.get("campaign_items") or []
        if not isinstance(items, list) or not items:
            QMessageBox.information(self, "안내", "리포트에 캠페인 내용이 없습니다.")
            return

        # ✅ 핵심: 이미지 bytes가 없으면 DB에서 캠페인 아이템 재조회
        campaign_id = list_meta.get("campaign_id")
        if self._items_need_bytes(items) and self.campaigns_repo and campaign_id is not None:
            try:
                items_db = self.campaigns_repo.get_campaign_items(int(campaign_id))
                # DB에서 받아온 items를 우선 사용
                if items_db:
                    items = items_db
            except Exception as e:
                QMessageBox.warning(self, "경고", f"캠페인 이미지 로드(재조회) 실패\n{e}")

        group_name = str(list_meta.get("group_name", "") or "전체")
        campaign_name = str(list_meta.get("campaign_name", "") or "(캠페인)")
        title = f"{group_name} + {campaign_name}".strip(" +")

        dlg = CampaignPreviewDialog(campaign_title=title, items=items, parent=self)
        dlg.exec()

    # -------------------------
    # 기존 기능들
    # -------------------------
    def _set_fail_only(self) -> None:
        for i in range(self.cbo_status.count()):
            if self.cbo_status.itemData(i) == "FAIL":
                self.cbo_status.setCurrentIndex(i)
                return

    def refresh(self) -> None:
        if self._active_source == "REPORT":
            rows = self._apply_filters_to_rows(self._report_rows)
            self._render_rows_to_table(rows)
            return

        status = self.cbo_status.currentData()
        keyword = (self.txt_keyword.text() or "").strip()

        try:
            rows = self.logs_repo.list_logs(
                status=str(status) if status else None,
                keyword=keyword,
                limit=2000,
                offset=0,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"로그 로드 실패\n{e}")
            return

        self.model.setRowCount(0)

        # ✅ DB 모드도 _shown_rows를 "표와 동일한 개념"으로 유지 (확장 대비)
        self._shown_rows = []
        for rr in (rows or []):
            self._shown_rows.append({
                "id": rr.id,
                "ts": rr.ts,
                "campaign_id": rr.campaign_id,
                "batch_id": rr.batch_id,
                "channel": rr.channel,
                "recipient": rr.recipient,
                "status": rr.status,
                "reason": rr.reason,
                "attempt": rr.attempt,
                "message_len": rr.message_len,
                "image_count": rr.image_count,
            })

        def _it(v: object) -> QStandardItem:
            x = QStandardItem("" if v is None else str(v))
            x.setEditable(False)
            return x

        for r in self._shown_rows:
            self.model.appendRow([
                _it(r.get("id")),
                _it(r.get("ts")),
                _it(r.get("campaign_id")),
                _it(r.get("batch_id")),
                _it(r.get("channel")),
                _it(r.get("recipient")),
                _it(r.get("status")),
                _it(r.get("reason")),
                _it(r.get("attempt")),
                _it(r.get("message_len")),
                _it(r.get("image_count")),
            ])

        # ✅ 선택행 reason 자동 표시(초기 상태에서도 동작)
        self._auto_show_reason_preview()

    def export_csv(self) -> None:
        # (이 부분은 이전 버전 그대로 사용 가능. 필요하면 그대로 붙여넣어도 됨)
        if self._active_source == "REPORT":
            rows = self._apply_filters_to_rows(self._report_rows)
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "CSV 저장(리포트)",
                str(Path.home() / "send_report_rows.csv"),
                "CSV Files (*.csv)"
            )
            if not file_path:
                return
            try:
                with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow([
                        "id", "ts", "campaign_id", "batch_id", "channel", "recipient",
                        "status", "reason", "attempt", "message_len", "image_count"
                    ])
                    for r in rows:
                        w.writerow([
                            r.get("id", ""),
                            r.get("ts", ""),
                            r.get("campaign_id", ""),
                            r.get("batch_id", ""),
                            r.get("channel", ""),
                            r.get("recipient", ""),
                            r.get("status", ""),
                            r.get("reason", ""),
                            r.get("attempt", 0),
                            r.get("message_len", 0),
                            r.get("image_count", 0),
                        ])
            except Exception as e:
                QMessageBox.critical(self, "오류", f"CSV 저장 실패\n{e}")
                return
            QMessageBox.information(self, "완료", f"CSV 저장 완료\n{file_path}")
            return

        status = self.cbo_status.currentData()
        keyword = (self.txt_keyword.text() or "").strip()

        try:
            rows = self.logs_repo.list_logs(
                status=str(status) if status else None,
                keyword=keyword,
                limit=50000,
                offset=0,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"CSV 내보내기용 로그 로드 실패\n{e}")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "CSV 저장",
            str(Path.home() / "send_logs.csv"),
            "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([
                    "id", "ts", "campaign_id", "batch_id", "channel", "recipient",
                    "status", "reason", "attempt", "message_len", "image_count"
                ])
                for r in rows:
                    w.writerow([
                        r.id, r.ts, r.campaign_id, r.batch_id, r.channel, r.recipient,
                        r.status, r.reason, r.attempt, r.message_len, r.image_count
                    ])
        except Exception as e:
            QMessageBox.critical(self, "오류", f"CSV 저장 실패\n{e}")
            return

        QMessageBox.information(self, "완료", f"CSV 저장 완료\n{file_path}")

    def show_retry_targets(self) -> None:
        if self._active_source == "REPORT":
            rows = self._apply_filters_to_rows(self._report_rows)
            fails = [r for r in rows if str(r.get("status", "")).upper().startswith("FAIL")]
            if not fails:
                QMessageBox.information(self, "안내", "리포트 기준 FAIL 대상이 없습니다.")
                return

            targets: List[str] = []
            for r in fails:
                targets.append(f"{r.get('recipient','')} | {r.get('reason','')}")
            preview = "\n".join(targets[:80])
            if len(targets) > 80:
                preview += f"\n… (+{len(targets) - 80}명)"

            QMessageBox.information(self, "재시도 대상(리포트 FAIL)", preview)
            return

        try:
            targets = self.logs_repo.get_retry_targets()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"재시도 대상 추출 실패\n{e}")
            return

        if not targets:
            QMessageBox.information(self, "안내", "재시도 대상(FAIL)이 없습니다.")
            return

        preview = "\n".join(targets[:80])
        if len(targets) > 80:
            preview += f"\n… (+{len(targets) - 80}명)"

        QMessageBox.information(self, "재시도 대상(FAIL)", preview)

    def reset_logs_and_reports(self) -> None:
        ok = QMessageBox.question(
            self,
            "전체 삭제",
            "1) send_logs 테이블 초기화\n"
            "2) send_report_*.json 리포트 파일 전체 삭제\n\n"
            "계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        # 1) DB 초기화
        try:
            self.logs_repo.reset_all()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"send_logs 초기화 실패\n{e}")
            return

        # 2) 리포트 파일 삭제
        deleted = 0
        failed: List[str] = []
        try:
            d = self._reports_dir()
            for p in list(d.glob("send_report_*.json")):
                try:
                    p.unlink(missing_ok=True)
                    deleted += 1
                except Exception:
                    failed.append(p.name)
        except Exception as e:
            QMessageBox.warning(self, "경고", f"리포트 파일 삭제 중 오류\n{e}")

        # 3) UI 상태 리셋
        self._active_source = "DB"
        self._report_path = None
        self._report_obj = None
        self._report_rows = []
        self._shown_rows = []

        # 콤보/표/뷰어 완전 초기화
        self.refresh_reports()
        self.cbo_reports.setCurrentIndex(0)

        self.model.setRowCount(0)
        self.txt_log_view.setPlainText("초기화 완료. DB 로그 모드입니다.")

        # DB 모드로 새로고침(빈 테이블)
        self.refresh()

        QMessageBox.information(
            self,
            "완료",
            f"초기화 완료\n- send_logs 초기화 완료\n- 리포트 삭제: {deleted}개"
            + (f"\n- 삭제 실패: {len(failed)}개" if failed else "")
        )

    # -------------------------
    # Viewer helpers
    # -------------------------
    def _selected_row_values(self) -> Optional[dict]:
        idx = self.tbl.currentIndex()
        if not idx.isValid():
            return None
        row = idx.row()

        def g(col: int) -> str:
            it = self.model.item(row, col)
            return "" if it is None else (it.text() or "")

        return {
            "id": g(0),
            "ts": g(1),
            "campaign_id": g(2),
            "batch_id": g(3),
            "channel": g(4),
            "recipient": g(5),
            "status": g(6),
            "reason": g(7),
            "attempt": g(8),
            "message_len": g(9),
            "image_count": g(10),
        }

    def _auto_show_reason_preview(self) -> None:
        data = self._selected_row_values()
        if not data:
            return

        reason = (data.get("reason") or "").strip()
        if reason:
            self.txt_log_view.setPlainText(reason)
            return

        # ✅ reason이 비어있을 때(특히 REPORT) 기본 안내
        if self._active_source == "REPORT":
            self.txt_log_view.setPlainText(
                "사유(reason)가 비어있습니다.\n"
                "행 더블클릭 → 상세 팝업에서 전체 스냅샷 확인 가능\n"
                "행 클릭 → 캠페인 미리보기(리포트에 이미지 bytes가 없으면 DB 재조회)\n"
            )

    def show_selected_detail(self) -> None:
        data = self._selected_row_values()
        if not data:
            QMessageBox.information(self, "안내", "상세를 볼 행을 선택하세요.")
            return

        detail = (
            f"[ROW DETAIL]\n"
            f"- source: {self._active_source}\n"
            f"- id: {data['id']}\n"
            f"- ts: {data['ts']}\n"
            f"- campaign_id: {data['campaign_id']}\n"
            f"- batch_id: {data['batch_id']}\n"
            f"- channel: {data['channel']}\n"
            f"- recipient: {data['recipient']}\n"
            f"- status: {data['status']}\n"
            f"- attempt: {data['attempt']}\n"
            f"- message_len: {data['message_len']}\n"
            f"- image_count: {data['image_count']}\n\n"
            f"[reason]\n{data['reason']}\n"
        )
        self.txt_log_view.setPlainText(detail)

    def open_log_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "로그 파일 열기",
            str(user_data_dir()),
            "Log Files (*.log *.txt *.jsonl *.json *.csv);;All Files (*)"
        )
        if not file_path:
            return
        self._load_text_file(Path(file_path))

    def open_wipe_log(self) -> None:
        try:
            import tempfile
            temp_dir = Path(tempfile.gettempdir())
            name = (user_data_dir().name or "app")
            wipe_log = temp_dir / f"{name}_wipe.log"
        except Exception as e:
            QMessageBox.critical(self, "오류", f"wipe 로그 경로 계산 실패\n{e}")
            return

        if not wipe_log.exists():
            QMessageBox.information(self, "안내", f"wipe 로그 파일이 없습니다.\n{wipe_log}")
            return

        self._load_text_file(wipe_log)

    def _load_text_file(self, path: Path) -> None:
        try:
            max_bytes = 5 * 1024 * 1024
            size = path.stat().st_size
            if size <= max_bytes:
                text = path.read_text(encoding="utf-8", errors="replace")
            else:
                with open(path, "rb") as f:
                    raw = f.read(max_bytes)
                text = raw.decode("utf-8", errors="replace")
                text += f"\n\n... (truncated, file_size={size} bytes)"
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 로드 실패\n{path}\n\n{e}")
            return

        header = f"[FILE]\n{str(path)}\n\n"
        self.txt_log_view.setPlainText(header + text)

    def reset_all_app(self) -> None:
        if not self._on_reset_all:
            QMessageBox.information(self, "안내", "전체 리셋 기능이 연결되어 있지 않습니다.")
            return
        try:
            self._on_reset_all()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"전체 리셋 실행 실패\n{e}")


__all__ = ["LogsPage"]
