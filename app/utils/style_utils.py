from __future__ import annotations


from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QListView,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableWidget,
    QWidget,
)


def clear_all_styles(root: QWidget) -> None:
    return


class GlobalWidgetPolisher(QObject):
    def __init__(self, row_height: int = 20):
        super().__init__()
        self._row_height = int(row_height)

    def eventFilter(self, obj, event):
        try:
            if event is not None and event.type() == QEvent.Type.Show:
                if isinstance(obj, QTableWidget):
                    self._polish_table(obj)
                if isinstance(obj, QListView):
                    self._polish_listview(obj)
        except Exception:
            pass
        return False

    def _polish_table(self, tbl: QTableWidget):
        if tbl is None:
            return
        try:
            no_zebra = False
            try:
                no_zebra = bool(tbl.property("no_zebra"))
            except Exception:
                no_zebra = False

            if no_zebra:
                tbl.setAlternatingRowColors(False)
            else:
                tbl.setAlternatingRowColors(True)
        except Exception:
            pass
        try:
            vh = tbl.verticalHeader()
            if vh is not None:
                vh.setMinimumSectionSize(self._row_height)
                vh.setDefaultSectionSize(self._row_height)
        except Exception:
            pass

    def _polish_listview(self, lv: QListView):
        if lv is None:
            return
        try:
            lv.setUniformItemSizes(True)
        except Exception:
            pass
        try:
            # Avoid re-installing delegate multiple times
            if isinstance(lv.itemDelegate(), _ListViewRowNumberDelegate):
                return
            lv.setItemDelegate(_ListViewRowNumberDelegate(lv, row_height=self._row_height))
        except Exception:
            pass


class _ListViewRowNumberDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, row_height: int = 20, gutter_width: int = 28):
        super().__init__(parent)
        self._row_height = int(row_height)
        self._gutter_width = int(gutter_width)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        if painter is None or option is None or index is None:
            return

        painter.save()
        try:
            rect = option.rect

            # Paint item content shifted to the right so it doesn't overlap with row numbers.
            opt = QStyleOptionViewItem(option)
            opt.rect = rect.adjusted(self._gutter_width + 8, 0, 0, 0)
            super().paint(painter, opt, index)

            # Paint left gutter background to match selection state.
            gutter_rect = rect
            gutter_rect.setWidth(self._gutter_width + 6)
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(gutter_rect, option.palette.highlight())
            else:
                painter.fillRect(gutter_rect, option.palette.base())

            # Draw row number in left gutter.
            row_no = index.row() + 1
            num_rect = rect
            num_rect.setWidth(self._gutter_width)

            # Use a subtle color; when selected, keep readable.
            if option.state & QStyle.StateFlag.State_Selected:
                painter.setPen(QColor("#162D6D"))
            else:
                painter.setPen(QColor("#555555"))

            painter.drawText(
                num_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                f"{row_no}",
            )

            # Vertical separator line between number gutter and text.
            painter.setPen(QColor("#757779"))
            x = rect.left() + self._gutter_width + 6
            painter.drawLine(x, rect.top(), x, rect.bottom())
        finally:
            painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index):
        sz = super().sizeHint(option, index)
        try:
            sz.setHeight(max(int(sz.height()), self._row_height))
        except Exception:
            pass
        return sz


_global_polisher = None


def ensure_global_polisher(app: QApplication | None = None, row_height: int = 20) -> None:
    return
