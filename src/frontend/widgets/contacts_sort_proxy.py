from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, QModelIndex, Qt


class ContactsSortProxyModel(QSortFilterProxyModel):
    """
    - No(1번 컬럼): 화면 표시용 순번(정렬/필터 적용 후 row()+1)
    - 체크박스(0번 컬럼): 소스 모델의 CheckStateRole 그대로
    - 나머지 컬럼: 정상 정렬 지원
    """

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        # ✅ 체크박스는 정렬 제외
        if column == 0:
            return
        super().sort(column, order)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        col = index.column()

        # 체크박스 컬럼은 그대로 소스 모델 값을 사용
        if col == 0:
            return super().data(index, role)

        # No 컬럼은 "현재 보이는 화면 기준" 순번
        if col == 1:
            if role == Qt.DisplayRole:
                return index.row() + 1
            # No 컬럼은 정렬키/검색에 영향 주지 않도록 (필요 시)
            return None

        return super().data(index, role)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        # No(1)는 정렬 대상에서 제외(항상 표시용)
        if left.column() == 1 and right.column() == 1:
            return left.row() < right.row()
        return super().lessThan(left, right)

    def _source_contact_id(self, proxy_index: QModelIndex) -> int:
        src = self.mapToSource(proxy_index)
        if not src.isValid():
            return 0
        m = self.sourceModel()
        # ContactsTableModel이 _rows를 갖고 있다는 전제(현재 구조)
        item = m._rows[src.row()]  # noqa
        return int(getattr(item, "id", 0))

    @staticmethod
    def _to_int(v) -> int:
        s = str(v).strip().replace("-", "")
        digits = "".join(ch for ch in s if ch.isdigit())
        return int(digits) if digits else 0
