from __future__ import annotations

import os

from PyQt6.QtWidgets import QWidget


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
