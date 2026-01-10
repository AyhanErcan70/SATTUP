from __future__ import annotations

from PyQt6.QtWidgets import QWidget


def clear_all_styles(root: QWidget) -> None:
    if root is None:
        return

    try:
        root.setStyleSheet("")
    except Exception:
        pass

    for w in root.findChildren(QWidget):
        try:
            w.setStyleSheet("")
        except Exception:
            pass
