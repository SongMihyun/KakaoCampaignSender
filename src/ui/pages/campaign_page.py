# ui/pages/campaign_page.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QFrame, QListWidget, QListWidgetItem,
    QComboBox, QDialog
)

from app.data.campaigns_repo import CampaignsRepo, CampaignRow, ItemType
from ui.pages.campaign_name_dialog import CampaignNameDialog
from ui.pages.text_item_dialog import TextItemDialog
from ui.pages.image_preview_dialog import ImagePreviewDialog
from ui.utils.worker import run_bg

from app.platform.win_file_picker import pick_open_files, pick_open_file, Filter
from ui.app_events import app_events


@dataclass
class DraftItem:
    item_type: ItemType           # "IMAGE" | "TEXT"
    text: str = ""
    image_name: str = ""
    image_bytes: bytes = b""


class CampaignPage(QWidget):
    """
    캠페인 편집기(드래프트) → 저장 시 '캠페인 1개'로 DB에 생성
    - 이미지/문구를 같은 리스트에서 섞어 배치(순서 편집)
    - 이미지 미리보기/문구 편집은 모두 팝업으로 처리
    """
    def __init__(self, repo: CampaignsRepo, on_status: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.repo = repo
        self._on_status = on_status or (lambda _: None)

        self._draft: list[DraftItem] = []
        self._campaigns: list[CampaignRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("캠페인 설정")
        title.setObjectName("PageTitle")
        desc = QLabel("이미지/문구를 원하는 순서로 배치한 뒤, 저장해서 하나의 캠페인으로 등록합니다.")
        desc.setObjectName("PageDesc")

        # TOP
        top = QHBoxLayout()
        top.setSpacing(8)

        top.addWidget(QLabel("저장된 캠페인"))
        self.cbo_campaigns = QComboBox()
        self.cbo_campaigns.setMinimumWidth(360)

        self.btn_load = QPushButton("불러오기")
        self.btn_delete_campaign = QPushButton("캠페인 삭제")

        self.btn_new = QPushButton("새로 만들기")
        self.btn_save_campaign = QPushButton("캠페인 저장(생성)")

        top.addWidget(self.cbo_campaigns)
        top.addWidget(self.btn_load)
        top.addWidget(self.btn_delete_campaign)
        top.addStretch(1)
        top.addWidget(self.btn_new)
        top.addWidget(self.btn_save_campaign)

        # MAIN
        main = QHBoxLayout()
        main.setSpacing(12)

        left_card = QFrame()
        left_card.setObjectName("Card")
        lv = QVBoxLayout(left_card)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(8)

        lv.addWidget(QLabel("캠페인 구성(순서 편집)"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_add_images = QPushButton("이미지 추가(복수)")
        self.btn_add_text = QPushButton("문구 추가")
        self.btn_edit_item = QPushButton("선택 편집")
        self.btn_preview = QPushButton("미리보기")
        self.btn_del_item = QPushButton("삭제")
        self.btn_up = QPushButton("▲")
        self.btn_down = QPushButton("▼")

        btn_row.addWidget(self.btn_add_images)
        btn_row.addWidget(self.btn_add_text)
        btn_row.addWidget(self.btn_edit_item)
        btn_row.addWidget(self.btn_preview)
        btn_row.addWidget(self.btn_del_item)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_up)
        btn_row.addWidget(self.btn_down)

        self.lst_items = QListWidget()
        self.lst_items.setIconSize(QSize(52, 52))
        self.lst_items.setMinimumWidth(760)

        lv.addLayout(btn_row)
        lv.addWidget(self.lst_items, 1)

        main.addWidget(left_card, 1)

        root.addWidget(title)
        root.addWidget(desc)
        root.addLayout(top)
        root.addLayout(main, 1)

        # events
        self.btn_new.clicked.connect(self._new_draft)

        self.btn_add_images.clicked.connect(self._add_images)
        self.btn_add_text.clicked.connect(self._add_text_item)
        self.btn_edit_item.clicked.connect(self._edit_selected_item_popup)
        self.btn_preview.clicked.connect(self._preview_selected_item)

        self.btn_del_item.clicked.connect(self._delete_selected_item)
        self.btn_up.clicked.connect(lambda: self._move_selected(-1))
        self.btn_down.clicked.connect(lambda: self._move_selected(+1))

        self.btn_save_campaign.clicked.connect(self._save_campaign)
        self.btn_load.clicked.connect(self._load_selected_campaign)
        self.btn_delete_campaign.clicked.connect(self._delete_selected_campaign)

        self.lst_items.itemDoubleClicked.connect(lambda *_: self._preview_selected_item())

        # init
        self._reload_campaigns_combo()
        self._new_draft()

    # -------------------------
    # 캠페인 목록
    # -------------------------
    def _reload_campaigns_combo(self) -> None:
        self.cbo_campaigns.blockSignals(True)
        self.cbo_campaigns.clear()

        self._campaigns = self.repo.list_campaigns()
        if not self._campaigns:
            self.cbo_campaigns.addItem("(저장된 캠페인 없음)", None)
        else:
            for c in self._campaigns:
                self.cbo_campaigns.addItem(f"[{c.id}] {c.name}", c.id)

        self.cbo_campaigns.setCurrentIndex(0)
        self.cbo_campaigns.blockSignals(False)

    def _selected_campaign_id(self) -> Optional[int]:
        v = self.cbo_campaigns.currentData()
        return int(v) if v is not None else None

    # -------------------------
    # Draft 편집
    # -------------------------
    def _new_draft(self) -> None:
        self._draft = []
        self._rebuild_list(select_index=-1)
        self._on_status("새 캠페인 작성 시작")

    def _add_images(self) -> None:
        try:
            paths = pick_open_files(
                title="캠페인 이미지 선택(복수)",
                filters=[
                    Filter("Images", "*.png;*.jpg;*.jpeg;*.webp"),
                    Filter("All Files", "*.*"),
                ],
                default_ext="",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기 실행 실패\n{e}")
            return

        if not paths:
            return

        insert_at = self.lst_items.currentRow()
        if insert_at < 0:
            insert_at = len(self._draft)
        else:
            insert_at += 1

        self._on_status("이미지 로딩 중...")

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
            return (new_items, ok, fail, insert_at)

        def done(res):
            new_items, ok, fail, insert_at_local = res
            if new_items:
                self._draft[insert_at_local:insert_at_local] = new_items
                self._rebuild_list(select_index=insert_at_local)
            self._on_status(f"이미지 추가: {ok}건 (실패 {fail}건)")

        run_bg(job, on_done=done, on_error=lambda tb: QMessageBox.critical(self, "오류", tb))

    def _add_text_item(self) -> None:
        dlg = TextItemDialog(title="문구 추가", text="", parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        text = dlg.get_text()

        insert_at = self.lst_items.currentRow()
        if insert_at < 0:
            insert_at = len(self._draft)
        else:
            insert_at += 1

        self._draft.insert(insert_at, DraftItem(item_type="TEXT", text=text))
        self._rebuild_list(select_index=insert_at)
        self._on_status("문구 아이템 추가")

    def _edit_selected_item_popup(self) -> None:
        idx = self.lst_items.currentRow()
        if idx < 0 or idx >= len(self._draft):
            QMessageBox.information(self, "안내", "편집할 아이템을 선택하세요.")
            return

        it = self._draft[idx]
        if it.item_type == "TEXT":
            dlg = TextItemDialog(title="문구 수정", text=it.text, parent=self)
            if dlg.exec() != QDialog.Accepted:
                return
            it.text = dlg.get_text()
            self._rebuild_list(select_index=idx)
            self._on_status("문구 수정 완료")
            return

        ok = QMessageBox.question(
            self, "이미지 교체",
            "선택 이미지를 다른 이미지로 교체하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        try:
            path = pick_open_file(
                title="이미지 교체",
                filters=[
                    Filter("Images", "*.png;*.jpg;*.jpeg;*.webp"),
                    Filter("All Files", "*.*"),
                ],
                default_ext="",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기 실행 실패\n{e}")
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

            it.image_name = path.split("/")[-1].split("\\")[-1]
            it.image_bytes = data
            self._rebuild_list(select_index=idx)
            self._on_status("이미지 교체 완료")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"이미지 교체 실패\n{e}")

    def _preview_selected_item(self) -> None:
        idx = self.lst_items.currentRow()
        if idx < 0 or idx >= len(self._draft):
            QMessageBox.information(self, "안내", "미리볼 아이템을 선택하세요.")
            return

        it = self._draft[idx]
        if it.item_type == "TEXT":
            QMessageBox.information(self, "문구 미리보기", it.text or "(빈 문구)")
            return

        dlg = ImagePreviewDialog(title=f"이미지 미리보기 - {it.image_name}", image_bytes=it.image_bytes, parent=self)
        dlg.exec()

    def _delete_selected_item(self) -> None:
        idx = self.lst_items.currentRow()
        if idx < 0 or idx >= len(self._draft):
            return

        it = self._draft[idx]
        label = it.image_name if it.item_type == "IMAGE" else (it.text[:30] + ("..." if len(it.text) > 30 else ""))

        ok = QMessageBox.question(
            self, "삭제 확인",
            f"선택 아이템을 삭제하시겠습니까?\n- {it.item_type}: {label}",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        del self._draft[idx]
        self._rebuild_list(select_index=min(idx, len(self._draft) - 1))
        self._on_status("아이템 삭제")

    def _move_selected(self, direction: int) -> None:
        idx = self.lst_items.currentRow()
        if idx < 0 or idx >= len(self._draft):
            return

        ni = idx + direction
        if ni < 0 or ni >= len(self._draft):
            return

        self._draft[idx], self._draft[ni] = self._draft[ni], self._draft[idx]
        self._rebuild_list(select_index=ni)
        self._on_status("순서 변경")

    # -------------------------
    # List rebuild
    # -------------------------
    def _rebuild_list(self, select_index: int = -1) -> None:
        self.lst_items.blockSignals(True)
        self.lst_items.clear()

        for i, it in enumerate(self._draft, start=1):
            if it.item_type == "IMAGE":
                item = QListWidgetItem(f"{i}. [이미지] {it.image_name}")
                pix = QPixmap()
                if pix.loadFromData(it.image_bytes):
                    icon_pix = pix.scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    item.setIcon(QIcon(icon_pix))
            else:
                preview = (it.text or "").replace("\n", " ")
                if len(preview) > 40:
                    preview = preview[:40] + "..."
                item = QListWidgetItem(f"{i}. [문구] {preview}")

            self.lst_items.addItem(item)

        self.lst_items.blockSignals(False)

        if not self._draft:
            self.lst_items.setCurrentRow(-1)
            return

        if select_index < 0:
            select_index = 0
        select_index = max(0, min(select_index, len(self._draft) - 1))
        self.lst_items.setCurrentRow(select_index)

    # -------------------------
    # 저장/불러오기
    # -------------------------
    def _save_campaign(self) -> None:
        if not self._draft:
            QMessageBox.information(self, "안내", "저장할 내용이 없습니다. 이미지/문구를 추가하세요.")
            return

        dlg = CampaignNameDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.get_name()

        items_payload = []
        for it in self._draft:
            if it.item_type == "TEXT":
                items_payload.append(("TEXT", {"text": it.text}))
            else:
                items_payload.append(("IMAGE", {"image_name": it.image_name, "image_bytes": it.image_bytes}))

        try:
            cid = self.repo.create_campaign(name, items_payload)
        except ValueError as e:
            QMessageBox.warning(self, "오류", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패\n{e}")
            return

        QMessageBox.information(self, "완료", f"캠페인 저장 완료\n- ID: {cid}\n- 이름: {name}")
        self._on_status(f"캠페인 저장: {name} (id={cid})")
        self._reload_campaigns_combo()

        # ✅ 다른 페이지(발송 등)도 즉시 갱신되도록 이벤트 발행
        try:
            app_events.campaigns_changed.emit()
        except Exception:
            pass

    def _load_selected_campaign(self) -> None:
        cid = self._selected_campaign_id()
        if cid is None:
            QMessageBox.information(self, "안내", "불러올 캠페인이 없습니다.")
            return

        try:
            rows = self.repo.get_campaign_items(cid)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"불러오기 실패\n{e}")
            return

        self._draft = []
        for r in rows:
            if r.item_type == "TEXT":
                self._draft.append(DraftItem(item_type="TEXT", text=r.text))
            else:
                self._draft.append(DraftItem(item_type="IMAGE", image_name=r.image_name, image_bytes=r.image_bytes))

        self._rebuild_list(select_index=0)
        self._on_status(f"캠페인 불러오기: id={cid}")

    def _delete_selected_campaign(self) -> None:
        cid = self._selected_campaign_id()
        if cid is None:
            QMessageBox.information(self, "안내", "삭제할 캠페인이 없습니다.")
            return

        ok = QMessageBox.question(
            self, "삭제 확인",
            f"캠페인(ID={cid})을 삭제하시겠습니까?\n(아이템 포함 전체 삭제)",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self.repo.delete_campaign(cid)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패\n{e}")
            return

        self._reload_campaigns_combo()
        # ✅ 다른 페이지(발송 등)도 즉시 갱신되도록 이벤트 발행
        try:
            app_events.campaigns_changed.emit()
        except Exception:
            pass
        self._on_status(f"캠페인 삭제: id={cid}")
        QMessageBox.information(self, "완료", f"캠페인 삭제 완료 (id={cid})")
