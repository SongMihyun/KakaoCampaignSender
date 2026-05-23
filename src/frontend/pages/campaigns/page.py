from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from backend.domains.campaigns.dto import CampaignDraftItemDTO
from backend.domains.campaigns.service import CampaignsService
from backend.integrations.windows.win_file_picker import Filter, pick_open_file, pick_open_files
from frontend.app.app_events import app_events
from frontend.pages.campaigns.name_dialog import CampaignNameDialog
from frontend.pages.campaigns.text_item_dialog import TextItemDialog
from frontend.theme import style_button
from frontend.utils.worker import run_bg


@dataclass
class DraftItem:
    item_type: str  # "IMAGE" | "TEXT"
    text: str = ""
    image_name: str = ""
    image_bytes: bytes = b""


class CampaignComboBox(QComboBox):
    delete_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CampaignCombo")

        self.delete_button = QToolButton(self)
        self.delete_button.setObjectName("CampaignComboDeleteButton")
        self.delete_button.setText("X")
        self.delete_button.setToolTip("선택한 캠페인 삭제")
        self.delete_button.setCursor(Qt.PointingHandCursor)
        self.delete_button.setFixedSize(28, 28)
        self.delete_button.clicked.connect(self.delete_requested.emit)

    def set_delete_enabled(self, enabled: bool) -> None:
        self.delete_button.setEnabled(enabled)
        self.delete_button.setVisible(enabled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        x = self.width() - 56
        y = int((self.height() - self.delete_button.height()) / 2)
        self.delete_button.move(max(0, x), max(0, y))


class CampaignPage(QWidget):
    def __init__(self, service: CampaignsService, on_status: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.service = service
        self._on_status = on_status or (lambda _: None)

        self._draft: list[DraftItem] = []
        self._campaigns = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("캠페인 설정")
        title.setObjectName("PageTitle")
        desc = QLabel("이미지와 문구를 순서대로 구성해 캠페인으로 저장합니다.")
        desc.setObjectName("PageDesc")

        top = QHBoxLayout()
        top.setSpacing(8)

        camp_lbl = QLabel("캠페인")
        camp_lbl.setObjectName("SectionTitle")
        top.addWidget(camp_lbl)

        self.cbo_campaigns = CampaignComboBox()
        self.cbo_campaigns.setMinimumWidth(320)

        self.btn_new = style_button(QPushButton("새 캠페인"), "primary")
        self.btn_save_campaign = style_button(QPushButton("저장"), "secondary")

        top.addWidget(self.cbo_campaigns, 1)
        top.addWidget(self.btn_new)
        top.addWidget(self.btn_save_campaign)

        main = QHBoxLayout()
        main.setSpacing(12)

        left_card = QFrame()
        left_card.setObjectName("Card")
        lv = QVBoxLayout(left_card)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(8)

        section = QLabel("구성")
        section.setObjectName("SectionTitle")
        lv.addWidget(section)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self.chk_multi_attach = QCheckBox("이미지 묶음 전송")
        self.chk_multi_attach.setToolTip("연속된 이미지를 카카오톡에서 묶음 첨부 방식으로 전송합니다.")
        mode_row.addWidget(self.chk_multi_attach)
        mode_row.addStretch(1)
        lv.addLayout(mode_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_add_images = style_button(QPushButton("이미지 추가"), "primary")
        self.btn_add_text = style_button(QPushButton("문구 추가"), "secondary")
        self.btn_up = style_button(QPushButton("▲"), "icon")
        self.btn_down = style_button(QPushButton("▼"), "icon")

        btn_row.addWidget(self.btn_add_images)
        btn_row.addWidget(self.btn_add_text)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_up)
        btn_row.addWidget(self.btn_down)

        self.lst_items = QListWidget()
        self.lst_items.setObjectName("CampaignItems")
        self.lst_items.setIconSize(QSize(52, 52))
        self.lst_items.setMinimumWidth(760)

        lv.addLayout(btn_row)
        lv.addWidget(self.lst_items, 1)

        main.addWidget(left_card, 1)

        root.addWidget(title)
        root.addWidget(desc)
        root.addLayout(top)
        root.addLayout(main, 1)

        self.btn_new.clicked.connect(self._new_draft)
        self.btn_add_images.clicked.connect(self._add_images)
        self.btn_add_text.clicked.connect(self._add_text_item)
        self.btn_up.clicked.connect(lambda: self._move_selected(-1))
        self.btn_down.clicked.connect(lambda: self._move_selected(+1))
        self.btn_save_campaign.clicked.connect(self._save_campaign)
        self.cbo_campaigns.delete_requested.connect(self._delete_selected_campaign)
        self.cbo_campaigns.currentIndexChanged.connect(self._on_campaign_combo_changed)
        self.lst_items.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._reload_campaigns_combo(auto_load=True)

    def _reload_campaigns_combo(self, *, select_campaign_id: Optional[int] = None, auto_load: bool = False) -> None:
        self.cbo_campaigns.blockSignals(True)
        self.cbo_campaigns.clear()

        self._campaigns = self.service.list_campaigns()
        if not self._campaigns:
            self.cbo_campaigns.addItem("(저장된 캠페인 없음)", None)
        else:
            selected_index = 0
            for i, campaign in enumerate(self._campaigns):
                mode = str(getattr(campaign, "send_mode", "clipboard") or "clipboard")
                mode_tag = " | 묶음" if mode == "multi_attach" else ""
                self.cbo_campaigns.addItem(f"[{campaign.id}] {campaign.name}{mode_tag}", campaign.id)
                if select_campaign_id is not None and int(campaign.id) == int(select_campaign_id):
                    selected_index = i
            self.cbo_campaigns.setCurrentIndex(selected_index)

        self.cbo_campaigns.blockSignals(False)
        self.cbo_campaigns.set_delete_enabled(self._selected_campaign_id() is not None)

        if auto_load and self._selected_campaign_id() is not None:
            self._load_selected_campaign(show_empty_message=False)
        elif not self._campaigns:
            self._new_draft()

    def _selected_campaign_id(self) -> Optional[int]:
        value = self.cbo_campaigns.currentData()
        return int(value) if value is not None else None

    def _on_campaign_combo_changed(self) -> None:
        self.cbo_campaigns.set_delete_enabled(self._selected_campaign_id() is not None)
        if self._selected_campaign_id() is not None:
            self._load_selected_campaign(show_empty_message=False)

    def _new_draft(self) -> None:
        self._draft = []
        self.chk_multi_attach.setChecked(False)
        self.lst_items.setCurrentRow(-1)
        self._rebuild_list(select_index=-1)
        self._on_status("새 캠페인 작성을 시작했습니다.")

    def _add_images(self) -> None:
        try:
            paths = pick_open_files(
                title="캠페인 이미지 선택",
                filters=[
                    Filter("Images", "*.png;*.jpg;*.jpeg;*.webp"),
                    Filter("All Files", "*.*"),
                ],
                default_ext="",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기를 실행할 수 없습니다.\n{e}")
            return

        if not paths:
            return

        insert_at = self.lst_items.currentRow()
        insert_at = len(self._draft) if insert_at < 0 else insert_at + 1
        self._on_status("이미지를 불러오는 중입니다.")

        def job():
            new_items: list[DraftItem] = []
            ok = 0
            fail = 0
            for path in paths:
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    name = path.split("/")[-1].split("\\")[-1]
                    new_items.append(DraftItem(item_type="IMAGE", image_name=name, image_bytes=data))
                    ok += 1
                except Exception:
                    fail += 1
            return new_items, ok, fail, insert_at

        def done(result):
            new_items, ok, fail, insert_at_local = result
            if new_items:
                self._draft[insert_at_local:insert_at_local] = new_items
                self._rebuild_list(select_index=insert_at_local)
            self._on_status(f"이미지 추가: {ok}건, 실패 {fail}건")

        run_bg(job, on_done=done, on_error=lambda tb: QMessageBox.critical(self, "오류", tb))

    def _add_text_item(self) -> None:
        dlg = TextItemDialog(title="문구 추가", text="", parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        insert_at = self.lst_items.currentRow()
        insert_at = len(self._draft) if insert_at < 0 else insert_at + 1

        self._draft.insert(insert_at, DraftItem(item_type="TEXT", text=dlg.get_text()))
        self._rebuild_list(select_index=insert_at)
        self._on_status("문구를 추가했습니다.")

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        idx = self.lst_items.row(item)
        if idx < 0 or idx >= len(self._draft):
            return

        self._open_item_detail_dialog(idx)

    def _open_item_detail_dialog(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._draft):
            return

        item = self._draft[idx]
        is_text = item.item_type == "TEXT"

        dlg = QDialog(self)
        dlg.setWindowTitle("문구 미리보기" if is_text else "이미지 미리보기")
        dlg.setMinimumSize(620, 460)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("[문구]" if is_text else f"[이미지] {item.image_name}")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        if is_text:
            viewer = QTextEdit()
            viewer.setReadOnly(True)
            viewer.setPlainText(item.text or "")
            root.addWidget(viewer, 1)
        else:
            viewer = QLabel()
            viewer.setAlignment(Qt.AlignCenter)
            viewer.setStyleSheet(
                "background:#f9fafb; border:1px solid #e5e7eb; border-radius:8px; padding:12px;"
            )
            pix = QPixmap()
            if pix.loadFromData(item.image_bytes or b""):
                viewer.setPixmap(pix.scaled(QSize(560, 320), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                viewer.setText("이미지를 불러올 수 없습니다.")
            root.addWidget(viewer, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        if is_text:
            btn_edit = style_button(QPushButton("수정"), "primary")
            btn_edit.clicked.connect(lambda: (dlg.accept(), self._edit_text_item(idx)))
            buttons.addWidget(btn_edit)
        else:
            btn_replace = style_button(QPushButton("교체"), "primary")
            btn_replace.clicked.connect(lambda: (dlg.accept(), self._replace_image(idx)))
            buttons.addWidget(btn_replace)

        btn_delete = style_button(QPushButton("삭제"), "danger")
        btn_close = style_button(QPushButton("닫기"), "ghost")
        btn_delete.clicked.connect(lambda: (dlg.accept(), self._delete_item_at(idx)))
        btn_close.clicked.connect(dlg.reject)
        buttons.addWidget(btn_delete)
        buttons.addWidget(btn_close)
        root.addLayout(buttons)

        dlg.exec()

    def _edit_text_item(self, idx: int) -> None:
        item = self._draft[idx]
        dlg = TextItemDialog(title="문구 수정", text=item.text, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        item.text = dlg.get_text()
        self._rebuild_list(select_index=idx)
        self._on_status("문구를 수정했습니다.")

    def _replace_image(self, idx: int) -> None:
        try:
            path = pick_open_file(
                title="대체 이미지 선택",
                filters=[
                    Filter("Images", "*.png;*.jpg;*.jpeg;*.webp"),
                    Filter("All Files", "*.*"),
                ],
                default_ext="",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기를 실행할 수 없습니다.\n{e}")
            return

        if not path:
            return

        try:
            with open(path, "rb") as f:
                data = f.read()

            pix = QPixmap()
            if not pix.loadFromData(data):
                QMessageBox.warning(self, "오류", "이미지를 불러올 수 없습니다.")
                return

            item = self._draft[idx]
            item.image_name = path.split("/")[-1].split("\\")[-1]
            item.image_bytes = data
            self._rebuild_list(select_index=idx)
            self._on_status("이미지를 변경했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"이미지 변경 실패\n{e}")

    def _delete_selected_item(self) -> None:
        self._delete_item_at(self.lst_items.currentRow())

    def _delete_item_at(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._draft):
            return

        del self._draft[idx]
        self._rebuild_list(select_index=min(idx, len(self._draft) - 1))
        self._on_status("구성 항목을 삭제했습니다.")

    def _move_selected(self, direction: int) -> None:
        idx = self.lst_items.currentRow()
        if idx < 0 or idx >= len(self._draft):
            return

        next_idx = idx + direction
        if next_idx < 0 or next_idx >= len(self._draft):
            return

        self._draft[idx], self._draft[next_idx] = self._draft[next_idx], self._draft[idx]
        self._rebuild_list(select_index=next_idx)
        self._on_status("구성 순서를 변경했습니다.")

    def _rebuild_list(self, select_index: int = -1) -> None:
        self.lst_items.blockSignals(True)
        self.lst_items.clear()

        for idx, item_data in enumerate(self._draft):
            item = QListWidgetItem()
            item.setSizeHint(QSize(100, 58))
            item.setData(Qt.UserRole, idx)
            self.lst_items.addItem(item)
            self.lst_items.setItemWidget(item, self._build_item_row(idx, item_data))

        self.lst_items.blockSignals(False)

        if not self._draft:
            self.lst_items.setCurrentRow(-1)
            return

        if select_index < 0:
            select_index = 0
        select_index = max(0, min(select_index, len(self._draft) - 1))
        self.lst_items.setCurrentRow(select_index)

    def _build_item_row(self, idx: int, item_data: DraftItem) -> QWidget:
        row = QWidget()
        row.setObjectName("CampaignItemRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(10)

        number = QLabel(f"{idx + 1}.")
        number.setObjectName("MutedText")
        number.setFixedWidth(28)
        layout.addWidget(number)

        if item_data.item_type == "IMAGE":
            thumb = QLabel()
            thumb.setObjectName("CampaignThumb")
            thumb.setFixedSize(44, 44)
            pix = QPixmap()
            if pix.loadFromData(item_data.image_bytes):
                thumb.setPixmap(pix.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText("IMG")
                thumb.setAlignment(Qt.AlignCenter)
            layout.addWidget(thumb)

            text = QLabel(f"[이미지] {item_data.image_name}")
        else:
            preview = (item_data.text or "").replace("\n", " ")
            if len(preview) > 82:
                preview = preview[:82] + "..."
            text = QLabel(f"[문구] {preview}")

        text.setObjectName("CampaignItemText")
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(text, 1)

        btn_delete = QToolButton()
        btn_delete.setObjectName("InlineDeleteButton")
        btn_delete.setText("X")
        btn_delete.setToolTip("이 구성 삭제")
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setFixedSize(28, 28)
        btn_delete.clicked.connect(lambda _=False, row_idx=idx: self._delete_item_at(row_idx))
        layout.addWidget(btn_delete, 0, Qt.AlignRight)

        return row

    def _save_campaign(self) -> None:
        if not self._draft:
            QMessageBox.information(self, "안내", "저장할 내용이 없습니다. 이미지나 문구를 추가하세요.")
            return

        dlg = CampaignNameDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.get_name()

        draft_items = [
            CampaignDraftItemDTO(
                item_type=item.item_type,
                text=item.text,
                image_name=item.image_name,
                image_bytes=item.image_bytes,
            )
            for item in self._draft
        ]

        send_mode = "multi_attach" if self.chk_multi_attach.isChecked() else "clipboard"

        try:
            campaign_id = self.service.create_campaign(name, draft_items, send_mode=send_mode)
        except ValueError as e:
            QMessageBox.warning(self, "오류", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패\n{e}")
            return

        QMessageBox.information(self, "완료", f"캠페인을 저장했습니다.\nID: {campaign_id}\n이름: {name}")
        self._on_status(f"캠페인 저장: {name} (id={campaign_id})")
        self._reload_campaigns_combo(select_campaign_id=campaign_id, auto_load=False)

        try:
            app_events.campaigns_changed.emit()
        except Exception:
            pass

    def _load_selected_campaign(self, *, show_empty_message: bool = True) -> None:
        campaign_id = self._selected_campaign_id()
        if campaign_id is None:
            if show_empty_message:
                QMessageBox.information(self, "안내", "불러올 캠페인이 없습니다.")
            return

        try:
            campaign = self.service.get_campaign(campaign_id)
            rows = self.service.get_campaign_items(campaign_id)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"캠페인을 불러오지 못했습니다.\n{e}")
            return

        self._draft = []
        for row in rows:
            if str(row.item_type).upper() == "TEXT":
                self._draft.append(DraftItem(item_type="TEXT", text=row.text))
            else:
                self._draft.append(DraftItem(item_type="IMAGE", image_name=row.image_name, image_bytes=row.image_bytes))

        mode = str(getattr(campaign, "send_mode", "clipboard") or "clipboard") if campaign else "clipboard"
        self.chk_multi_attach.setChecked(mode == "multi_attach")
        self._rebuild_list(select_index=0)
        self._on_status(f"캠페인을 불러왔습니다. id={campaign_id}")

    def _delete_selected_campaign(self) -> None:
        campaign_id = self._selected_campaign_id()
        if campaign_id is None:
            QMessageBox.information(self, "안내", "삭제할 캠페인이 없습니다.")
            return

        reply = QMessageBox.question(
            self,
            "삭제 확인",
            f"캠페인 ID={campaign_id}를 삭제할까요?\n구성 항목도 함께 삭제됩니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.service.delete_campaign(campaign_id)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패\n{e}")
            return

        self._reload_campaigns_combo(auto_load=True)
        try:
            app_events.campaigns_changed.emit()
        except Exception:
            pass
        self._on_status(f"캠페인을 삭제했습니다. id={campaign_id}")
