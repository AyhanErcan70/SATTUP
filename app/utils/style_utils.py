from __future__ import annotations

import os

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication, QTableWidget, QWidget


def clear_all_styles(root: QWidget) -> None:
    if root is None:
        return

    try:
        # Default: keep Qt Designer styles.
        # Set SATTUP_CLEAR_STYLES=1 to restore legacy behavior (clear all widget stylesheets).
        if str(os.environ.get("SATTUP_CLEAR_STYLES", "")).strip() not in ("1", "true", "True", "yes", "YES"):
            return
    except Exception:
        pass

    try:
        root.setStyleSheet("")
    except Exception:
        pass

    for w in root.findChildren(QWidget):
        try:
            w.setStyleSheet("")
        except Exception:
            pass


class GlobalWidgetPolisher(QObject):
    def __init__(self, row_height: int = 20):
        super().__init__()
        self._row_height = int(row_height)

    def eventFilter(self, obj, event):
        try:
            if event is not None and event.type() == QEvent.Type.Show:
                if isinstance(obj, QTableWidget):
                    self._polish_table(obj)
        except Exception:
            pass
        return False

    def _polish_table(self, tbl: QTableWidget):
        if tbl is None:
            return
        try:
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


_global_polisher = None


def ensure_global_polisher(app: QApplication | None = None, row_height: int = 20) -> None:
    global _global_polisher
    try:
        if _global_polisher is not None:
            return
        app0 = app or QApplication.instance()
        if app0 is None:
            return
        _global_polisher = GlobalWidgetPolisher(row_height=row_height)
        app0.installEventFilter(_global_polisher)
    except Exception:
        return
