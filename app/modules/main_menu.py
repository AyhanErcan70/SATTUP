import os

import traceback

from PyQt6.QtWidgets import QMainWindow, QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QLabel, QGraphicsColorizeEffect, QFrame, QMessageBox, QComboBox, QPushButton, QGraphicsBlurEffect
from PyQt6.QtGui import QPixmap, QIcon, QColor, QFontMetrics
from PyQt6.QtCore import QSize
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, QEvent, QPoint, QRect, QParallelAnimationGroup, QUrl, QVariantAnimation
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from PyQt6 import uic
from config import ASSETS_DIR, ICONS_PATH, get_ui_path
from app.utils.style_utils import clear_all_styles
from app.modules.users import UsersApp
from app.modules.employees import EmployeesApp
from app.modules.customers import CustomersApp
from app.modules.vehicles import VehiclesApp
from app.modules.drivers import DriversApp
from app.modules.repairs import RepairsApp
from app.modules.constants import ConstantsApp
from app.modules.routes import RoutesApp
from app.modules.trips import TripsGridApp
from app.modules.attendance import AttendanceApp
from assets.images import kaynaklar_rc


_MENU_FRAME_QSS = """
QPushButton {
	background-color: #E8E8E8;
    color: #000;
    font-family: 'DaytonaPro', sans-serif;
    font-weight: bold;
    font-size: 11pt;
    border-radius: 10px;
	border-top: 1px solid #C0C0C0;
    border-left: 1px solid #C0C0C0;
    border-right: 4px solid #808080;
    border-bottom: 5px solid #696969;
    text-align: left;
    margin-right: 4px;
    margin-bottom: 5px;
    padding: 3px;
}

QPushButton[selected="true"] {
    background-color: #FFF3E0;
    color: #984C00;
    border-right: 4px solid #984C00;
    border-bottom: 5px solid #6B3A00;
}

QPushButton[flash="true"] {
    background-color: #FFE0B2;
}

QPushButton:hover {
    color: #984C00;
    border-right: 4px solid #A9A9A9;
    border-bottom: 5px solid #808080;
}

QPushButton:pressed {
    border-top: 2px solid #696969;
    border-left: 2px solid #696969;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    
    margin-top: 4px;
    margin-left: 2px;
    margin-bottom: 1px;
    margin-right: 2px;
    
    padding-top: 10px;
}
"""

class DownComboBox(QComboBox):
    def showPopup(self):
        super().showPopup()
        try:
            view = self.view()
            if view is None:
                return
            popup = view.window()
            if popup is None:
                return

            below = self.mapToGlobal(QPoint(0, self.height()))
            popup.move(below)
        except Exception:
            return

class MainMenuApp(QMainWindow):
    def __init__(self, user_data=None, start_passive: bool = False, offline_timeout_ms: int = 120000):
        super().__init__()
        uic.loadUi(get_ui_path("main_window.ui"), self)
        # clear_all_styles(self)
        self.user_data = user_data

        try:
            if hasattr(self, "menu_frame") and self.menu_frame is not None:
                self.menu_frame.setStyleSheet(_MENU_FRAME_QSS)
        except Exception:
            pass

        try:
            if hasattr(self, "top_frame") and self.top_frame is not None:
                self.top_frame.setProperty("mw_header", True)
            if hasattr(self, "bottom_frame") and self.bottom_frame is not None:
                self.bottom_frame.setProperty("mw_header", True)
        except Exception:
            pass

        try:
            for _w in (getattr(self, "top_frame", None), getattr(self, "bottom_frame", None)):
                if _w is None:
                    continue
                try:
                    _w.style().unpolish(_w)
                    _w.style().polish(_w)
                    _w.update()
                except Exception:
                    pass
        except Exception:
            pass

        self._session_active = False
        self._offline_timeout_ms = int(offline_timeout_ms or 0)
        self._offline_warning_ms = 30000
        self._offline_timer = None
        self._offline_warn_timer = None
        self._offline_countdown_timer = None
        self._offline_sound_loop_timer = None
        self._offline_warning_dialog = None
        self._offline_warning_label = None
        self._offline_warning_active = False
        self._offline_seconds_left = 0
        self._offline_warning_pulse_anim = None
        self._footer_user_label = None
        self._footer_user_timer = None
        self._welcome_overlay = None
        self._welcome_dismissed = False
        self._welcome_year_label = None
        self._welcome_month_combo = None
        self._welcome_overlay_opacity = None
        self._welcome_overlay_fade_anim = None
        self._welcome_overlay_geom_anim = None
        self._startup_title_gating = True
        self._offline_audio_output = None
        self._offline_player = None

        self._menu_buttons = []
        self._menu_button_texts = {}
        self._sidebar_expanded_width = 200
        self._sidebar_collapsed_width = 60
        self._sidebar_animation = None
        self._sidebar_is_collapsed = False
        self._sidebar_text_anims = {}
        self._sidebar_text_base_styles = {}
        self._fade_anims = {}
        self._title_pulse_anim = None
        self._title_base_stylesheet = ""
        self._toast = None
        self._toast_anim = None
        self._hover_anims = {}
        self._toggle_btn_anim = None
        self._slide_anims = {}
        self._page_intro_anims = {}
        self._active_indicator = None
        self._active_indicator_anim = None
        self._title_underline = None
        self._title_underline_anim = None
        self._title_anim_layer = None
        self._title_anim_anims = []
        self._title_anim_timers = []
        self._title_anim_running = False
        self._title_text_last = ""

        if hasattr(self, "lbl_logo") and self.lbl_logo is not None:
            pix = QPixmap(os.path.join(ASSETS_DIR, "images", "logo-w.png"))
            if not pix.isNull():
                self.lbl_logo.setPixmap(pix.scaled(QSize(180, 80), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.lbl_logo.setScaledContents(False)

        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
            self.centralWidget().setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Başlangıç Başlığı
        self._default_title_text = "SAKARYA ASİL TUR TAŞIMACILIK HİZMETLERİ UYGULAMASI"
        self.lbl_title.setText(self._default_title_text)
        try:
            if hasattr(self, "lbl_title") and self.lbl_title is not None:
                self._title_base_stylesheet = self.lbl_title.styleSheet() or ""
        except Exception:
            self._title_base_stylesheet = ""
        
        # Menü sistemini ateşle
        self.setup_menu()

        self._setup_sidebar_toggle()
        self._apply_menu_icons()
        self._ensure_active_indicator()
        self._ensure_title_anim_layer()

        self._ensure_welcome_overlay()
        self._load_onoff_settings_from_db()
        self.set_mode(active=not bool(start_passive))

        self._setup_session_toggle()

        # İlk açılışta da full title animasyonu
        try:
            # Başlık animasyonu bitene kadar dönem overlay'ı pasif ve soluk kalsın
            self._set_welcome_overlay_interactive(False, animate=False)
            QTimer.singleShot(120, lambda: self._animate_title_type_in(self._default_title_text))
        except Exception:
            pass

    def _setup_session_toggle(self):
        btn = None
        try:
            if hasattr(self, "btn_session_toggle"):
                btn = getattr(self, "btn_session_toggle")
        except Exception:
            btn = None

        if btn is None:
            try:
                btn = self.findChild(QPushButton, "btn_session_toggle")
            except Exception:
                btn = None
        if btn is None:
            try:
                btn = self.findChild(QPushButton, "pushButton")
            except Exception:
                btn = None
        if btn is None:
            return
        try:
            btn.clicked.connect(self._on_session_toggle_clicked)
        except Exception:
            pass
        self._update_session_toggle_button()

    def _update_session_toggle_button(self):
        btn = None
        try:
            if hasattr(self, "btn_session_toggle"):
                btn = getattr(self, "btn_session_toggle")
        except Exception:
            btn = None
        if btn is None:
            try:
                btn = self.findChild(QPushButton, "btn_session_toggle")
            except Exception:
                btn = None
        if btn is None:
            try:
                btn = self.findChild(QPushButton, "pushButton")
            except Exception:
                btn = None
        if btn is None:
            return
        try:
            btn.setText("Oturum Kapat" if self._session_active else "Oturum Aç")
        except Exception:
            pass

    def _on_session_toggle_clicked(self):
        if self._session_active:
            self.set_mode(active=False)
        else:
            try:
                self._show_toast("Oturum açılıyor...")
                QTimer.singleShot(0, self.request_login)
            except Exception:
                self.request_login()

    def _force_maximized(self):
        self.setMinimumSize(0, 0)
        self.setMinimumWidth(0)
        self.setMinimumHeight(0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
            self.centralWidget().setMinimumWidth(0)
            self.centralWidget().setMinimumHeight(0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.setWindowState(Qt.WindowState.WindowMaximized)

    def resizeEvent(self, event):
        try:
            self._position_title_underline()
            self._position_title_anim_layer()
            self._position_welcome_overlay()
            # toast konumu da resize sonrası düzgün kalsın
            if self._toast is not None and self._toast.isVisible():
                self._show_toast(self._toast.text())
        except Exception:
            pass
        return super().resizeEvent(event)

    def _ensure_offline_audio(self):
        if self._offline_player is not None and self._offline_audio_output is not None:
            return
        try:
            self._offline_audio_output = QAudioOutput()
            self._offline_player = QMediaPlayer()
            self._offline_player.setAudioOutput(self._offline_audio_output)
            sound_path = os.path.join(ASSETS_DIR, "sounds", "offline_clock.wav")
            if os.path.exists(sound_path):
                self._offline_player.setSource(QUrl.fromLocalFile(sound_path))
            self._offline_audio_output.setVolume(0.6)
        except Exception:
            self._offline_audio_output = None
            self._offline_player = None

    def _play_offline_sound(self):
        try:
            self._ensure_offline_audio()
            if self._offline_player is not None:
                self._offline_player.stop()
                self._offline_player.play()
        except Exception:
            return

    def _stop_offline_sound(self):
        try:
            if self._offline_sound_loop_timer is not None:
                self._offline_sound_loop_timer.stop()
        except Exception:
            pass
        try:
            if self._offline_player is not None:
                self._offline_player.stop()
        except Exception:
            return

    def _ensure_offline_timer(self):
        if self._offline_timer is not None:
            return
        self._offline_timer = QTimer(self)
        self._offline_timer.setSingleShot(True)
        self._offline_timer.timeout.connect(self._on_offline_timeout)

    def _ensure_offline_warn_timer(self):
        if self._offline_warn_timer is not None:
            return
        self._offline_warn_timer = QTimer(self)
        self._offline_warn_timer.setSingleShot(True)
        self._offline_warn_timer.timeout.connect(self._on_offline_warning_start)

    def _ensure_offline_countdown_timer(self):
        if self._offline_countdown_timer is not None:
            return
        self._offline_countdown_timer = QTimer(self)
        self._offline_countdown_timer.setInterval(1000)
        self._offline_countdown_timer.timeout.connect(self._on_offline_countdown_tick)

    def _ensure_offline_sound_loop_timer(self):
        if self._offline_sound_loop_timer is not None:
            return
        self._offline_sound_loop_timer = QTimer(self)
        self._offline_sound_loop_timer.setInterval(3500)
        self._offline_sound_loop_timer.timeout.connect(self._play_offline_sound)

    def _start_offline_timer(self):
        if not self._session_active:
            return
        if self._offline_timeout_ms <= 0:
            return
        self._offline_warning_active = False
        self._hide_offline_warning_dialog()
        self._ensure_offline_timer()
        self._ensure_offline_warn_timer()
        try:
            self._offline_timer.start(self._offline_timeout_ms)
        except Exception:
            pass

        warn_before = int(getattr(self, "_offline_warning_ms", 30000) or 0)
        warn_ms = max(0, int(self._offline_timeout_ms) - warn_before)
        try:
            self._offline_warn_timer.start(warn_ms)
        except Exception:
            pass

        self._start_footer_user_timer()
        self._update_footer_user_label()

    def set_offline_policy(self, online_ms: int, warning_ms: int):
        try:
            online_ms = int(online_ms)
        except Exception:
            online_ms = 0
        try:
            warning_ms = int(warning_ms)
        except Exception:
            warning_ms = 0

        if online_ms <= 0:
            online_ms = 120000
        if warning_ms < 0:
            warning_ms = 0
        if warning_ms >= online_ms:
            warning_ms = max(0, online_ms - 1000)

        self._offline_timeout_ms = int(online_ms)
        self._offline_warning_ms = int(warning_ms)

        if self._session_active:
            self._start_offline_timer()

    def _load_onoff_settings_from_db(self):
        try:
            from app.core.db_manager import DatabaseManager

            db = DatabaseManager()
            online_ms = 120000
            warning_ms = 30000
            try:
                rows = db.get_constants("onoff_online_ms")
                if rows:
                    online_ms = int(rows[0][1])
            except Exception:
                pass
            try:
                rows = db.get_constants("onoff_warning_ms")
                if rows:
                    warning_ms = int(rows[0][1])
            except Exception:
                pass
            self.set_offline_policy(online_ms=online_ms, warning_ms=warning_ms)
        except Exception:
            return

    def _stop_offline_timer(self):
        try:
            if self._offline_timer is not None:
                self._offline_timer.stop()
            if self._offline_warn_timer is not None:
                self._offline_warn_timer.stop()
            if self._offline_countdown_timer is not None:
                self._offline_countdown_timer.stop()
            if self._footer_user_timer is not None:
                self._footer_user_timer.stop()
            self._stop_offline_sound()
            self._offline_warning_active = False
            self._hide_offline_warning_dialog()
        except Exception:
            return

    def _ensure_footer_user_label(self):
        if self._footer_user_label is not None:
            return
        try:
            from PyQt6.QtWidgets import QLabel

            self._footer_user_label = self.findChild(QLabel, "lbl_user")
        except Exception:
            self._footer_user_label = None

    def _ensure_footer_user_timer(self):
        if self._footer_user_timer is not None:
            return
        self._footer_user_timer = QTimer(self)
        self._footer_user_timer.setInterval(1000)
        self._footer_user_timer.timeout.connect(self._update_footer_user_label)

    def _start_footer_user_timer(self):
        self._ensure_footer_user_timer()
        try:
            if self._footer_user_timer is not None and self._session_active:
                self._footer_user_timer.start()
        except Exception:
            pass

    def _get_current_username(self) -> str:
        try:
            if isinstance(self.user_data, dict):
                for k in ("username", "user", "kullanici", "kullanici_adi", "kullaniciAdi", "name"):
                    v = self.user_data.get(k)
                    if v:
                        return str(v)
        except Exception:
            pass
        return ""

    def _format_ms_as_hhmmss(self, ms: int) -> str:
        try:
            ms = int(ms or 0)
        except Exception:
            ms = 0
        if ms < 0:
            ms = 0
        sec = ms // 1000
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _update_footer_user_label(self):
        self._ensure_footer_user_label()
        if self._footer_user_label is None:
            return

        if not self._session_active:
            try:
                self._footer_user_label.setText("")
            except Exception:
                pass
            return

        username = self._get_current_username()

        remaining_ms = 0
        try:
            if self._offline_timer is not None:
                remaining_ms = int(self._offline_timer.remainingTime())
        except Exception:
            remaining_ms = 0

        time_txt = self._format_ms_as_hhmmss(remaining_ms)
        if username:
            txt = f"{username}  |  {time_txt}"
        else:
            txt = f"{time_txt}"
        try:
            self._footer_user_label.setText(txt)
        except Exception:
            pass

    def _reset_offline_timer(self):
        if not self._session_active:
            return
        self._start_offline_timer()

    def eventFilter(self, obj, event):
        try:
            if obj in getattr(self, "_menu_buttons", []):
                if event.type() == QEvent.Type.Enter:
                    self._animate_menu_hover(obj, entering=True)
                elif event.type() == QEvent.Type.Leave:
                    self._animate_menu_hover(obj, entering=False)

            if self._session_active:
                if not self._offline_warning_active:
                    if event.type() in (
                        QEvent.Type.MouseButtonPress,
                        QEvent.Type.MouseButtonRelease,
                        QEvent.Type.KeyPress,
                        QEvent.Type.Wheel,
                    ):
                        self._reset_offline_timer()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _ensure_offline_warning_dialog(self):
        if self._offline_warning_dialog is not None:
            return
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton

        dlg = QDialog(self)
        dlg.setWindowTitle("Oturum Uyarısı")
        dlg.setModal(False)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        label = QLabel(dlg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 14px;")

        btn_extend = QPushButton("Ek Süre")
        btn_offline = QPushButton("Offline Ol")
        btn_extend.clicked.connect(self._on_offline_extend)
        btn_offline.clicked.connect(self._on_offline_go_offline)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_extend)
        row.addWidget(btn_offline)
        row.addStretch(1)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        lay.addWidget(label)
        lay.addLayout(row)

        self._offline_warning_dialog = dlg
        self._offline_warning_label = label

    def _hide_offline_warning_dialog(self):
        try:
            if self._offline_warning_dialog is not None:
                try:
                    if self._offline_warning_pulse_anim is not None:
                        self._offline_warning_pulse_anim.stop()
                except Exception:
                    pass
                self._offline_warning_pulse_anim = None
                try:
                    self._offline_warning_dialog.setWindowOpacity(1.0)
                except Exception:
                    pass
                self._offline_warning_dialog.hide()
        except Exception:
            return

    def _pulse_offline_warning_dialog(self):
        try:
            dlg = self._offline_warning_dialog
            if dlg is None:
                return

            try:
                if self._offline_warning_pulse_anim is not None:
                    self._offline_warning_pulse_anim.stop()
            except Exception:
                pass
            self._offline_warning_pulse_anim = None

            try:
                dlg.setWindowOpacity(1.0)
            except Exception:
                pass

            a1 = QPropertyAnimation(dlg, b"windowOpacity", dlg)
            a1.setDuration(140)
            a1.setStartValue(1.0)
            a1.setEndValue(0.88)
            a1.setEasingCurve(QEasingCurve.Type.OutCubic)

            a2 = QPropertyAnimation(dlg, b"windowOpacity", dlg)
            a2.setDuration(220)
            a2.setStartValue(0.88)
            a2.setEndValue(1.0)
            a2.setEasingCurve(QEasingCurve.Type.OutCubic)

            a3 = QPropertyAnimation(dlg, b"windowOpacity", dlg)
            a3.setDuration(140)
            a3.setStartValue(1.0)
            a3.setEndValue(0.92)
            a3.setEasingCurve(QEasingCurve.Type.OutCubic)

            a4 = QPropertyAnimation(dlg, b"windowOpacity", dlg)
            a4.setDuration(220)
            a4.setStartValue(0.92)
            a4.setEndValue(1.0)
            a4.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QSequentialAnimationGroup(dlg)
            group.addAnimation(a1)
            group.addAnimation(a2)
            group.addAnimation(a3)
            group.addAnimation(a4)

            def _finish():
                try:
                    dlg.setWindowOpacity(1.0)
                except Exception:
                    pass
                self._offline_warning_pulse_anim = None

            group.finished.connect(_finish)
            self._offline_warning_pulse_anim = group
            group.start()
        except Exception:
            return

    def _update_offline_warning_text(self):
        try:
            if self._offline_warning_label is None:
                return
            sec = max(0, int(self._offline_seconds_left))
            self._offline_warning_label.setText(
                f"{sec} saniye sonra oturumunuz sonlandırılacaktır.\n\nEk süre ister misiniz?"
            )
        except Exception:
            return

    def _on_offline_warning_start(self):
        if not self._session_active:
            return
        self._offline_warning_active = True
        try:
            warn_before = int(getattr(self, "_offline_warning_ms", 30000) or 0)
        except Exception:
            warn_before = 30000
        self._offline_seconds_left = max(1, int((warn_before + 999) // 1000))
        self._ensure_offline_warning_dialog()
        self._update_offline_warning_text()
        try:
            if self._offline_warning_dialog is not None:
                self._offline_warning_dialog.adjustSize()
                self._offline_warning_dialog.move(self.geometry().center() - self._offline_warning_dialog.rect().center())
                self._offline_warning_dialog.show()
                self._offline_warning_dialog.raise_()
                self._offline_warning_dialog.activateWindow()
        except Exception:
            pass

        try:
            self._pulse_offline_warning_dialog()
        except Exception:
            pass

        try:
            self._play_offline_sound()
            self._ensure_offline_sound_loop_timer()
            self._offline_sound_loop_timer.start()
        except Exception:
            pass

        self._ensure_offline_countdown_timer()
        try:
            self._offline_countdown_timer.start()
        except Exception:
            pass

    def _on_offline_countdown_tick(self):
        if not self._session_active:
            return
        if not self._offline_warning_active:
            return
        self._offline_seconds_left = int(self._offline_seconds_left) - 1
        self._update_offline_warning_text()
        if self._offline_seconds_left <= 0:
            try:
                if self._offline_countdown_timer is not None:
                    self._offline_countdown_timer.stop()
            except Exception:
                pass
            self._on_offline_go_offline()

    def _on_offline_extend(self):
        self._offline_warning_active = False
        try:
            if self._offline_countdown_timer is not None:
                self._offline_countdown_timer.stop()
        except Exception:
            pass
        self._stop_offline_sound()
        self._hide_offline_warning_dialog()
        self._start_offline_timer()
        try:
            self._show_toast("Ek süre verildi")
        except Exception:
            pass

    def _on_offline_go_offline(self):
        try:
            if self._offline_timer is not None:
                self._offline_timer.stop()
        except Exception:
            pass
        try:
            if self._offline_warn_timer is not None:
                self._offline_warn_timer.stop()
        except Exception:
            pass
        try:
            if self._offline_countdown_timer is not None:
                self._offline_countdown_timer.stop()
        except Exception:
            pass
        self._stop_offline_sound()
        self._offline_warning_active = False
        self._hide_offline_warning_dialog()
        self._on_offline_timeout()

    def _ensure_welcome_overlay(self):
        if self._welcome_overlay is not None:
            return
        page_main = None
        try:
            if hasattr(self, "page_main"):
                page_main = getattr(self, "page_main")
        except Exception:
            page_main = None
        if page_main is None:
            try:
                page_main = self.mainStack.widget(0) if self.mainStack is not None else None
            except Exception:
                page_main = None
        if page_main is None:
            return

        self._welcome_overlay = QFrame(page_main)
        self._welcome_overlay.setObjectName("welcome_overlay")
        self._welcome_overlay.setStyleSheet(
            "background-color: rgba(15, 15, 15, 160); border-radius: 14px;"
        )

        try:
            eff = QGraphicsOpacityEffect(self._welcome_overlay)
            eff.setOpacity(1.0)
            self._welcome_overlay.setGraphicsEffect(eff)
            self._welcome_overlay_opacity = eff
        except Exception:
            self._welcome_overlay_opacity = None
        self._welcome_overlay.setVisible(True)

        from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout

        year_text = "2026"
        try:
            active_month = None
            if isinstance(self.user_data, dict):
                active_month = (self.user_data or {}).get("active_month")
            if active_month:
                y_str, _m_str = str(active_month).split("-", 1)
                if y_str.strip().isdigit():
                    year_text = y_str.strip()
        except Exception:
            year_text = "2026"

        self._welcome_hint_label = QLabel(self._welcome_overlay)
        self._welcome_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome_hint_label.setWordWrap(True)
        self._welcome_hint_label.setText("Lütfen ilk olarak Ay seçimi yapıp Devam tuşuna basınız")
        self._welcome_hint_label.setStyleSheet("color: rgba(255,255,255,210); font-size: 18px; font-weight: 600; background: transparent;")

        self._welcome_year_label = QLabel(self._welcome_overlay)
        self._welcome_year_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome_year_label.setText(year_text)
        self._welcome_year_label.setStyleSheet("color: white; font-size: 34px; font-weight: 800; background: transparent;")

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        lbl_month = QLabel(self._welcome_overlay)
        lbl_month.setText("AY")
        lbl_month.setStyleSheet("color: rgba(255,255,255,210); font-size: 18px; background: transparent;")

        self._welcome_month_combo = DownComboBox(self._welcome_overlay)
        self._welcome_month_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._welcome_month_combo.setMinimumHeight(44)
        self._welcome_month_combo.setStyleSheet(
            "QComboBox { padding: 6px 10px; border-radius: 8px; color: white; font-size: 34px; }"
            "QComboBox QAbstractItemView { color: white; background-color: rgba(20,20,20,240); selection-background-color: rgba(152,76,0,180); }"
        )
        months = [
            ("OCAK", 1),
            ("ŞUBAT", 2),
            ("MART", 3),
            ("NİSAN", 4),
            ("MAYIS", 5),
            ("HAZİRAN", 6),
            ("TEMMUZ", 7),
            ("AĞUSTOS", 8),
            ("EYLÜL", 9),
            ("EKİM", 10),
            ("KASIM", 11),
            ("ARALIK", 12),
        ]
        for name, m in months:
            self._welcome_month_combo.addItem(name, m)

        try:
            if isinstance(self.user_data, dict):
                am = (self.user_data or {}).get("active_month")
                if am:
                    _y, m_str = str(am).split("-", 1)
                    mi = self._welcome_month_combo.findData(int(m_str))
                    if mi >= 0:
                        self._welcome_month_combo.setCurrentIndex(mi)
        except Exception:
            pass

        row.addStretch(1)
        row.addWidget(lbl_month)
        row.addWidget(self._welcome_month_combo)
        row.addStretch(1)

        self._welcome_btn = QPushButton("DEVAM", self._welcome_overlay)
        self._welcome_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._welcome_btn.setStyleSheet(
            "QPushButton { background-color: #984C00; color: white; border: none; padding: 10px 18px; border-radius: 10px; font-weight: 700; }"
            "QPushButton:hover { background-color: #B35E00; }"
            "QPushButton:pressed { background-color: #7A3D00; }"
        )
        self._welcome_btn.clicked.connect(self._on_welcome_continue)

        lay = QVBoxLayout(self._welcome_overlay)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        lay.addStretch(1)
        lay.addWidget(self._welcome_hint_label)
        lay.addSpacing(6)
        lay.addWidget(self._welcome_year_label)
        lay.addSpacing(6)
        lay.addLayout(row)
        lay.addSpacing(10)
        lay.addWidget(self._welcome_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(1)

        self._position_welcome_overlay()
        try:
            self._welcome_overlay.raise_()
        except Exception:
            pass

    def _set_welcome_overlay_interactive(self, interactive: bool, animate: bool = True):
        if self._welcome_overlay is None:
            return

        try:
            if self._welcome_overlay_fade_anim is not None:
                try:
                    self._welcome_overlay_fade_anim.stop()
                except Exception:
                    pass
                self._welcome_overlay_fade_anim = None
        except Exception:
            pass

        try:
            if self._welcome_overlay_geom_anim is not None:
                try:
                    self._welcome_overlay_geom_anim.stop()
                except Exception:
                    pass
                self._welcome_overlay_geom_anim = None
        except Exception:
            pass

        try:
            self._welcome_overlay.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                not bool(interactive),
            )
        except Exception:
            pass

        eff = self._welcome_overlay_opacity
        if eff is None:
            try:
                eff = self._welcome_overlay.graphicsEffect()
            except Exception:
                eff = None
        if not isinstance(eff, QGraphicsOpacityEffect):
            try:
                eff = QGraphicsOpacityEffect(self._welcome_overlay)
                self._welcome_overlay.setGraphicsEffect(eff)
                self._welcome_overlay_opacity = eff
            except Exception:
                eff = None

        target = 1.0 if interactive else 0.35
        if not animate or eff is None:
            try:
                if eff is not None:
                    eff.setOpacity(target)
            except Exception:
                pass
            return

        try:
            a = QPropertyAnimation(eff, b"opacity", self._welcome_overlay)
            a.setDuration(380)
            a.setStartValue(float(eff.opacity()))
            a.setEndValue(float(target))
            a.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QParallelAnimationGroup(self._welcome_overlay)
            group.addAnimation(a)

            # Interactive açılırken hafif scale-in (geometry tabanlı, minimal)
            if interactive:
                try:
                    g = self._welcome_overlay.geometry()
                    dx = max(1, int(g.width() * 0.015))
                    dy = max(1, int(g.height() * 0.015))
                    start_g = QRect(g.x() + dx, g.y() + dy, max(10, g.width() - 2 * dx), max(10, g.height() - 2 * dy))
                    self._welcome_overlay.setGeometry(start_g)
                    ag = QPropertyAnimation(self._welcome_overlay, b"geometry", self._welcome_overlay)
                    ag.setDuration(420)
                    ag.setStartValue(start_g)
                    ag.setEndValue(g)
                    ag.setEasingCurve(QEasingCurve.Type.OutCubic)
                    group.addAnimation(ag)
                except Exception:
                    pass

            def _finish():
                self._welcome_overlay_fade_anim = None
                self._welcome_overlay_geom_anim = None

            group.finished.connect(_finish)
            self._welcome_overlay_fade_anim = group
            self._welcome_overlay_geom_anim = group
            group.start()
        except Exception:
            return

    def _on_welcome_continue(self):
        try:
            y = "2026"
            if self._welcome_year_label is not None:
                y = (self._welcome_year_label.text() or "2026").strip() or "2026"
            m = 1
            if self._welcome_month_combo is not None:
                m = int(self._welcome_month_combo.currentData() or 1)
            if self.user_data is None or not isinstance(self.user_data, dict):
                self.user_data = {}
            self.user_data["active_month"] = f"{int(y):04d}-{int(m):02d}"
        except Exception:
            pass

        try:
            from app.core.db_manager import DatabaseManager

            db = DatabaseManager()
            selected_month = None
            try:
                selected_month = (self.user_data or {}).get("active_month")
            except Exception:
                selected_month = None

            def _prev_month_key(month_key: str) -> str | None:
                try:
                    y_str, m_str = str(month_key).split("-", 1)
                    yy = int(y_str)
                    mm = int(m_str)
                    if mm <= 1:
                        return f"{yy - 1:04d}-12"
                    return f"{yy:04d}-{mm - 1:02d}"
                except Exception:
                    return None

            if selected_month and not db.month_has_operational_template(str(selected_month)):
                prev = _prev_month_key(str(selected_month))
                if prev and db.month_has_operational_template(prev):
                    ok = QMessageBox.question(
                        None,
                        "Şablon Kopyalama",
                        f"{selected_month} dönemi için şablon bulunamadı.\n\n{prev} dönemindeki şablonlar kopyalansın mı?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if ok == QMessageBox.StandardButton.Yes:
                        done = db.copy_month_operational_template(prev, str(selected_month))
                        if not done:
                            QMessageBox.warning(None, "Uyarı", "Şablon kopyalama yapılamadı.")
                else:
                    QMessageBox.information(
                        None,
                        "Bilgi",
                        f"{selected_month} dönemi için şablon bulunamadı ve kopyalanacak önceki dönem yok.",
                    )
        except Exception:
            pass

        self._welcome_dismissed = True
        try:
            if self._welcome_overlay is not None:
                self._welcome_overlay.setVisible(False)
        except Exception:
            pass

    def _position_welcome_overlay(self):
        if self._welcome_overlay is None:
            return
        parent = self._welcome_overlay.parentWidget()
        if parent is None:
            return
        try:
            w = min(520, max(360, parent.width() - 120))
            h = 220
            x = max(20, (parent.width() - w) // 2)
            y = max(20, (parent.height() - h) // 2)
            self._welcome_overlay.setGeometry(QRect(x, y, w, h))
        except Exception:
            return

    def _clear_stack_to_main(self):
        try:
            if hasattr(self, "mainStack") and self.mainStack is not None:
                for i in reversed(range(self.mainStack.count())):
                    w = self.mainStack.widget(i)
                    if w is None:
                        continue
                    if getattr(w, "objectName", lambda: "")() == "page_main":
                        continue
                    self.mainStack.removeWidget(w)
                    try:
                        w.setParent(None)
                    except Exception:
                        pass
                    w.deleteLater()
                try:
                    if hasattr(self, "page_main") and self.page_main is not None:
                        self.mainStack.setCurrentWidget(self.page_main)
                    else:
                        self.mainStack.setCurrentIndex(0)
                except Exception:
                    pass
        except Exception:
            return

    def set_mode(self, active: bool):
        self._session_active = bool(active)
        try:
            app = None
            try:
                from PyQt6.QtWidgets import QApplication

                app = QApplication.instance()
            except Exception:
                app = None
            if app is not None:
                app.installEventFilter(self)
        except Exception:
            pass

        if self._session_active:
            try:
                if hasattr(self, "menu_frame") and self.menu_frame is not None:
                    self.menu_frame.setVisible(True)
            except Exception:
                pass
            try:
                if self._welcome_overlay is not None:
                    self._welcome_overlay.setVisible(False)
            except Exception:
                pass
            self._start_offline_timer()
        else:
            self._stop_offline_timer()
            self._clear_stack_to_main()
            self._welcome_dismissed = False
            try:
                if hasattr(self, "lbl_title") and self.lbl_title is not None:
                    self._clear_title_letter_items()
                    self.lbl_title.setText(getattr(self, "_default_title_text", "") or "")
            except Exception:
                pass
            try:
                if hasattr(self, "menu_frame") and self.menu_frame is not None:
                    self.menu_frame.setVisible(False)
            except Exception:
                pass
            try:
                for btn in getattr(self, "_menu_buttons", []):
                    btn.setChecked(False)
            except Exception:
                pass
            try:
                if self._active_indicator is not None:
                    self._active_indicator.setVisible(False)
            except Exception:
                pass
            self._ensure_welcome_overlay()
            try:
                if self._welcome_overlay is not None:
                    if not getattr(self, "_welcome_dismissed", False):
                        self._welcome_overlay.setVisible(True)
                        self._welcome_overlay.raise_()
            except Exception:
                pass

        try:
            self._update_session_toggle_button()
        except Exception:
            pass

    def request_login(self):
        try:
            try:
                dlg_existing = getattr(self, "_login_dialog", None)
                if dlg_existing is not None:
                    try:
                        dlg_existing.raise_()
                        dlg_existing.activateWindow()
                        dlg_existing.show()
                    except Exception:
                        pass
                    return
            except Exception:
                pass

            from app.modules.auth import AuthApp

            dlg = AuthApp()
            self._login_dialog = dlg
            try:
                dlg.setParent(self)
                dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
                dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
                dlg.show()
                dlg.raise_()
                dlg.activateWindow()
            except Exception:
                pass

            result = None
            try:
                result = dlg.exec()
            except Exception:
                result = 0

            if result:
                ud = getattr(dlg, "user_data", None) or {}
                if self.user_data is None:
                    self.user_data = {}
                try:
                    self.user_data.update(ud)
                except Exception:
                    self.user_data = ud
                self.set_mode(active=True)
                self._show_toast("Oturum açıldı")
            else:
                self._show_toast("Oturum açılmadı")
        except Exception:
            try:
                self._show_toast("Login açılamadı")
            except Exception:
                pass
            traceback.print_exc()
        finally:
            try:
                self._login_dialog = None
            except Exception:
                pass

    def _on_offline_timeout(self):
        try:
            self._play_offline_sound()
        except Exception:
            pass
        try:
            self._show_toast("Offline moda geçildi")
        except Exception:
            pass
        self.set_mode(active=False)

    def setup_menu(self):
        """15 Butonun tamamını bağlayan liste - Görseldeki sıralama ile aynı"""
        self._menu_map = {
            "btn_users": self.open_users,
            "btn_employees": self.open_employees,
            "btn_customers": self.open_customers,
            "btn_vehicles": self.open_vehicles,
            "btn_drivers": self.open_drivers,
            "btn_repairs": self.open_repairs,
            "btn_contracts": self.open_contracts,
            "btn_routes": self.open_routes,
            "btn_trips": self.open_trips,
            "btn_attendance": self.open_attendance,
            "btn_payments": self.open_payments,
            "btn_finance": self.open_finance,
            "btn_constants": self.open_constants,
            "btn_reports": self.open_reports,
            "btn_settings": self.open_settings
        }

        self._menu_buttons = []
        self._menu_button_texts = {}

        for btn_name, open_func in self._menu_map.items():
            if hasattr(self, btn_name):
                btn = getattr(self, btn_name)
                btn.setCheckable(True)
                btn.setAutoExclusive(True)
                self._menu_buttons.append(btn)
                self._menu_button_texts[btn] = btn.text()
                # handle_menu_click: Hem başlığı değiştirir hem ilgili modülü açar
                btn.clicked.connect(lambda checked, b=btn, f=open_func: self.handle_menu_click(b, f))

                try:
                    btn.installEventFilter(self)
                except Exception:
                    pass

        # İlk görünür durumda indicator'ü hizala
        try:
            if self._menu_buttons:
                self._move_active_indicator(self._menu_buttons[0], animate=False)
        except Exception:
            pass

    def _animate_menu_hover(self, btn, entering: bool):
        try:
            eff = btn.graphicsEffect()
            if eff is None or eff.metaObject().className() != "QGraphicsDropShadowEffect":
                from PyQt6.QtWidgets import QGraphicsDropShadowEffect

                eff = QGraphicsDropShadowEffect(btn)
                eff.setColor(QColor(0, 0, 0, 0))
                eff.setBlurRadius(0.0)
                eff.setXOffset(0.0)
                eff.setYOffset(0.0)
                btn.setGraphicsEffect(eff)

            anim = self._hover_anims.get(btn)
            if anim is not None:
                try:
                    anim.stop()
                except Exception:
                    pass

            # Premium hover: subtle amber glow + tiny lift (no geometry scaling)
            end_blur = 22.0 if entering else 0.0
            end_y = 2.0 if entering else 0.0
            end_color = QColor(152, 76, 0, 160) if entering else QColor(0, 0, 0, 0)

            dur = 200 if entering else 220
            curve = QEasingCurve(QEasingCurve.Type.OutQuart)

            a1 = QPropertyAnimation(eff, b"blurRadius", btn)
            a1.setDuration(dur)
            a1.setStartValue(float(eff.blurRadius()))
            a1.setEndValue(end_blur)
            a1.setEasingCurve(curve)

            a2 = QPropertyAnimation(eff, b"yOffset", btn)
            a2.setDuration(dur)
            a2.setStartValue(float(eff.yOffset()))
            a2.setEndValue(end_y)
            a2.setEasingCurve(curve)

            a3 = QPropertyAnimation(eff, b"color", btn)
            a3.setDuration(dur)
            try:
                a3.setStartValue(eff.color())
            except Exception:
                a3.setStartValue(QColor(0, 0, 0, 0))
            a3.setEndValue(end_color)
            a3.setEasingCurve(curve)

            group = QParallelAnimationGroup(btn)
            group.addAnimation(a1)
            group.addAnimation(a2)
            group.addAnimation(a3)

            def _finish():
                try:
                    self._hover_anims.pop(btn, None)
                except Exception:
                    pass

            group.finished.connect(_finish)
            self._hover_anims[btn] = group
            group.start()
        except Exception:
            return

    def _transition_between_pages(self, prev_widget, new_widget):
        try:
            if prev_widget is None or new_widget is None:
                if new_widget is not None:
                    self._animate_page_intro(new_widget)
                return
            if prev_widget is new_widget:
                return

            def _stack_contains(w):
                try:
                    if w is None:
                        return False
                    if not hasattr(self, "mainStack") or self.mainStack is None:
                        return False
                    for i in range(self.mainStack.count()):
                        if self.mainStack.widget(i) is w:
                            return True
                except Exception:
                    return False
                return False

            # Bazı open_* fonksiyonları eski sayfayı hemen remove/delete ediyor.
            # Böyle durumlarda blur-out yapmayalım; sadece yeni sayfaya intro uygula.
            if not _stack_contains(prev_widget):
                try:
                    new_widget.setVisible(True)
                except Exception:
                    pass
                self._animate_page_intro(new_widget)
                return

            # Outgoing blur-out (short, subtle)
            blur = prev_widget.graphicsEffect()
            if not isinstance(blur, QGraphicsBlurEffect):
                blur = QGraphicsBlurEffect(prev_widget)
                blur.setBlurRadius(0.0)
                prev_widget.setGraphicsEffect(blur)
            try:
                blur.setBlurRadius(0.0)
            except Exception:
                pass

            if not hasattr(self, "_page_out_anims"):
                self._page_out_anims = {}
            prev_anim = self._page_out_anims.get(prev_widget)
            if prev_anim is not None:
                try:
                    prev_anim.stop()
                except Exception:
                    pass

            a = QPropertyAnimation(blur, b"blurRadius", prev_widget)
            a.setDuration(150)
            a.setStartValue(float(getattr(blur, "blurRadius", lambda: 0.0)()))
            a.setEndValue(6.0)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)

            def _finish():
                try:
                    prev_widget.setGraphicsEffect(None)
                except Exception:
                    pass
                try:
                    self._page_out_anims.pop(prev_widget, None)
                except Exception:
                    pass
                try:
                    new_widget.setVisible(True)
                except Exception:
                    pass
                try:
                    self._animate_page_intro(new_widget)
                except Exception:
                    pass

            a.finished.connect(_finish)
            self._page_out_anims[prev_widget] = a
            a.start()
        except Exception:
            return

    def _ensure_title_anim_layer(self):
        if self._title_anim_layer is not None:
            return
        if not hasattr(self, "lbl_title") or self.lbl_title is None:
            return
        parent = self.lbl_title.parentWidget()
        if parent is None:
            return

        self._title_anim_layer = QFrame(parent)
        self._title_anim_layer.setObjectName("title_anim_layer")
        self._title_anim_layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._title_anim_layer.setStyleSheet("background: transparent;")
        self._title_anim_layer.setVisible(True)
        self._position_title_anim_layer()
        try:
            self._title_anim_layer.raise_()
        except Exception:
            pass

    def _position_title_anim_layer(self):
        if self._title_anim_layer is None or not hasattr(self, "lbl_title") or self.lbl_title is None:
            return
        try:
            self._title_anim_layer.setGeometry(self.lbl_title.geometry())
            self._title_anim_layer.raise_()
        except Exception:
            return

    def _clear_title_letter_items(self):
        try:
            for t in self._title_anim_timers:
                try:
                    t.stop()
                except Exception:
                    pass
            self._title_anim_timers = []
        except Exception:
            self._title_anim_timers = []

        try:
            for a in self._title_anim_anims:
                try:
                    a.stop()
                except Exception:
                    pass
            self._title_anim_anims = []
        except Exception:
            self._title_anim_anims = []

        if self._title_anim_layer is None:
            return
        try:
            for child in self._title_anim_layer.findChildren(QLabel):
                child.deleteLater()
        except Exception:
            return

    def _animate_title_type_in(self, text: str):
        if not hasattr(self, "lbl_title") or self.lbl_title is None:
            return

        self._ensure_title_anim_layer()
        self._position_title_anim_layer()
        if self._title_anim_layer is None:
            self.lbl_title.setText(text)
            return

        # Aynı text tekrar tekrar geliyorsa bile animasyon yapabilsin diye last'i sadece info için tutuyoruz
        self._title_text_last = text or ""

        self._title_anim_running = True
        self._clear_title_letter_items()

        # Alttaki gerçek label metni animasyon bitince set edilecek
        self.lbl_title.setText("")

        fm = QFontMetrics(self.lbl_title.font())
        base_y = max(0, (self._title_anim_layer.height() - fm.height()) // 2)

        # Toplam süreyi daha stabil tut: çok uzun başlıklarda bile akış aynı kalsın
        letters_only = [ch for ch in (text or "") if ch != " "]
        n = max(1, len(letters_only))
        target_total = 520  # ms
        stagger = int(target_total / max(1, n - 1)) if n > 1 else target_total
        stagger = max(14, min(34, stagger))

        # Her harf aynı sağ başlangıç noktasından gelsin (senin çizdiğin şema gibi)
        start_x = max(0, self._title_anim_layer.width() + 40)
        glow_color = QColor("#FFE101")

        x = 0
        idx = 0
        for ch in (text or ""):
            if ch == " ":
                x += fm.horizontalAdvance(" ")
                continue

            w = max(6, fm.horizontalAdvance(ch))
            h = max(fm.height(), 10)

            lbl = QLabel(self._title_anim_layer)
            lbl.setText(ch)
            lbl.setFont(self.lbl_title.font())
            lbl.setStyleSheet("color: #FFE101; background: transparent;")
            lbl.resize(w + 2, h)
            target_pos = QPoint(x, base_y)
            start_pos = QPoint(start_x, base_y)
            lbl.move(start_pos)
            lbl.show()

            op = QGraphicsOpacityEffect(lbl)
            op.setOpacity(0.0)
            lbl.setGraphicsEffect(op)

            def _start_letter(letter_lbl=lbl, effect=op, tp=target_pos):
                try:
                    pos_anim = QPropertyAnimation(letter_lbl, b"pos", letter_lbl)
                    pos_anim.setDuration(260)
                    pos_anim.setStartValue(letter_lbl.pos())
                    pos_anim.setEndValue(tp)
                    pos_anim.setEasingCurve(QEasingCurve.Type.OutQuart)

                    op_anim = QPropertyAnimation(effect, b"opacity", letter_lbl)
                    op_anim.setDuration(240)
                    op_anim.setStartValue(effect.opacity())
                    op_anim.setEndValue(1.0)
                    op_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

                    def _pos_finish():
                        try:
                            # Netleşsin: opacity effect kaldır, normal label kalsın
                            letter_lbl.setGraphicsEffect(None)
                        except Exception:
                            pass

                    pos_anim.finished.connect(_pos_finish)

                    par = QParallelAnimationGroup(letter_lbl)
                    par.addAnimation(pos_anim)
                    par.addAnimation(op_anim)
                    self._title_anim_anims.append(par)
                    par.start()
                except Exception:
                    return

            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(_start_letter)
            timer.start(idx * stagger)
            self._title_anim_timers.append(timer)

            x += fm.horizontalAdvance(ch)
            idx += 1

        # Animasyon bittikten sonra gerçek title'ı set et ve overlay'i temizle
        total_ms = (idx * stagger) + 520
        end_timer = QTimer(self)
        end_timer.setSingleShot(True)

        def _end():
            self._title_anim_running = False
            self.lbl_title.setText(text)
            self._clear_title_letter_items()

            # Açılışta başlık animasyonu bittikten sonra dönem overlay'ını aktif et
            try:
                if (
                    not self._session_active
                    and self._welcome_overlay is not None
                    and self._welcome_overlay.isVisible()
                    and getattr(self, "_startup_title_gating", False)
                ):
                    self._startup_title_gating = False
                    self._set_welcome_overlay_interactive(True, animate=True)
            except Exception:
                pass

            # Tüm metin tamamlanınca tek seferlik glow/parlama
            try:
                eff = QGraphicsColorizeEffect(self.lbl_title)
                eff.setColor(glow_color)
                eff.setStrength(0.0)
                self.lbl_title.setGraphicsEffect(eff)

                g1 = QPropertyAnimation(eff, b"strength", self.lbl_title)
                g1.setDuration(160)
                g1.setStartValue(0.0)
                g1.setEndValue(1.0)
                g1.setEasingCurve(QEasingCurve.Type.OutCubic)

                g2 = QPropertyAnimation(eff, b"strength", self.lbl_title)
                g2.setDuration(300)
                g2.setStartValue(1.0)
                g2.setEndValue(0.0)
                g2.setEasingCurve(QEasingCurve.Type.OutCubic)

                gg = QSequentialAnimationGroup(self.lbl_title)
                gg.addAnimation(g1)
                gg.addAnimation(g2)

                def _glow_finish():
                    try:
                        self.lbl_title.setGraphicsEffect(None)
                    except Exception:
                        pass

                gg.finished.connect(_glow_finish)
                self._title_anim_anims.append(gg)
                gg.start()
            except Exception:
                pass

        end_timer.timeout.connect(_end)
        end_timer.start(total_ms)
        self._title_anim_timers.append(end_timer)

    def _ensure_title_underline(self):
        if self._title_underline is not None:
            return
        if not hasattr(self, "lbl_title") or self.lbl_title is None:
            return
        parent = self.lbl_title.parentWidget()
        if parent is None:
            return

        self._title_underline = QFrame(parent)
        self._title_underline.setObjectName("title_underline")
        self._title_underline.setStyleSheet("background-color: #FFE101; border-radius: 2px;")
        self._title_underline.setFixedHeight(4)
        self._title_underline.setVisible(True)
        self._position_title_underline()

    def _position_title_underline(self):
        if self._title_underline is None or not hasattr(self, "lbl_title") or self.lbl_title is None:
            return
        g = self.lbl_title.geometry()
        # lbl_title'ın altına hizala
        x = g.x() + 6
        y = g.y() + g.height() + 4
        w = max(20, g.width() - 12)
        h = self._title_underline.height()
        # Animasyon yoksa direkt yerleştir
        if self._title_underline_anim is None:
            self._title_underline.setGeometry(QRect(x, y, w, h))

    def _animate_title_underline(self):
        self._ensure_title_underline()
        if self._title_underline is None or not hasattr(self, "lbl_title") or self.lbl_title is None:
            return

        try:
            g = self.lbl_title.geometry()
            x = g.x() + 6
            y = g.y() + g.height() + 4
            full_w = max(20, g.width() - 12)
            h = self._title_underline.height()

            start = QRect(x, y, 10, h)
            end = QRect(x, y, full_w, h)

            if self._title_underline_anim is not None:
                try:
                    self._title_underline_anim.stop()
                except Exception:
                    pass

            a1 = QPropertyAnimation(self._title_underline, b"geometry", self._title_underline)
            a1.setDuration(220)
            a1.setStartValue(start)
            a1.setEndValue(end)
            a1.setEasingCurve(QEasingCurve.Type.OutCubic)

            a2 = QPropertyAnimation(self._title_underline, b"geometry", self._title_underline)
            a2.setDuration(320)
            a2.setStartValue(end)
            a2.setEndValue(end)
            a2.setEasingCurve(QEasingCurve.Type.Linear)

            a3 = QPropertyAnimation(self._title_underline, b"geometry", self._title_underline)
            a3.setDuration(260)
            a3.setStartValue(end)
            a3.setEndValue(QRect(x, y, max(18, int(full_w * 0.55)), h))
            a3.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QSequentialAnimationGroup(self._title_underline)
            group.addAnimation(a1)
            group.addAnimation(a2)
            group.addAnimation(a3)

            def _finish():
                self._title_underline_anim = None
                try:
                    self._position_title_underline()
                except Exception:
                    pass

            group.finished.connect(_finish)
            self._title_underline_anim = group
            group.start()
        except Exception:
            return

    def handle_menu_click(self, button, open_func):
        """lbl_title'ı günceller, modülü açar ve tıklanan butonu kilitler"""
        if not self._session_active:
            self._show_toast("Oturum açmalısınız")
            self._clear_stack_to_main()
            self._ensure_welcome_overlay()
            try:
                if self._welcome_overlay is not None:
                    self._welcome_overlay.setVisible(True)
                    self._welcome_overlay.raise_()
            except Exception:
                pass
            return
        # Başlığı ve modülü aç
        text = self._menu_button_texts.get(button, button.text())
        self._animate_title_type_in(text)
        button.setChecked(True)
        self._set_active_menu_button(button)

        prev_widget = None
        try:
            prev_widget = self.mainStack.currentWidget() if hasattr(self, "mainStack") and self.mainStack is not None else None
        except Exception:
            prev_widget = None
        try:
            open_func()
        except Exception:
            traceback.print_exc()

        new_widget = None
        try:
            new_widget = self.mainStack.currentWidget() if hasattr(self, "mainStack") and self.mainStack is not None else None
        except Exception:
            new_widget = None

        try:
            self._transition_between_pages(prev_widget, new_widget)
        except Exception:
            pass

        current = None
        try:
            current = self.mainStack.currentWidget()
        except Exception:
            current = None
        if current is not None:
            # Hard guarantee: widget görünür kalsın (opacity effect kalmış olabilir)
            try:
                if current in self._fade_anims:
                    try:
                        self._fade_anims[current].stop()
                    except Exception:
                        pass
                    self._fade_anims.pop(current, None)
            except Exception:
                pass

        self._show_toast(text)
        # GUI geçiş animasyonunu kapalı tutuyoruz (kayar/bounce yok)

        self._move_active_indicator(button, animate=True)
        # underline kapalı

    def _pulse_title(self):
        if not hasattr(self, "lbl_title") or self.lbl_title is None:
            return

        try:
            # Temporary background highlight (more visible than subtle colorize-only)
            try:
                self.lbl_title.setStyleSheet(
                    (self._title_base_stylesheet or "")
                    + "background-color: rgba(255, 243, 224, 200); border-radius: 8px; padding: 6px;"
                )
                QTimer.singleShot(900, lambda: self.lbl_title.setStyleSheet(self._title_base_stylesheet or ""))
            except Exception:
                pass

            eff = self.lbl_title.graphicsEffect()
            if not isinstance(eff, QGraphicsColorizeEffect):
                eff = QGraphicsColorizeEffect(self.lbl_title)
                eff.setColor(QColor("#984C00"))
                self.lbl_title.setGraphicsEffect(eff)

            if self._title_pulse_anim is not None:
                try:
                    self._title_pulse_anim.stop()
                except Exception:
                    pass

            a1 = QPropertyAnimation(eff, b"strength", self.lbl_title)
            a1.setDuration(180)
            a1.setStartValue(0.0)
            a1.setEndValue(1.0)
            a1.setEasingCurve(QEasingCurve.Type.OutCubic)

            a2 = QPropertyAnimation(eff, b"strength", self.lbl_title)
            a2.setDuration(360)
            a2.setStartValue(1.0)
            a2.setEndValue(0.0)
            a2.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QSequentialAnimationGroup(self.lbl_title)
            group.addAnimation(a1)
            group.addPause(260)
            group.addAnimation(a2)

            def _finish():
                try:
                    eff.setStrength(0.0)
                except Exception:
                    pass
                self._title_pulse_anim = None

            group.finished.connect(_finish)
            self._title_pulse_anim = group
            group.start()
        except Exception:
            return

    def _ensure_toast(self):
        if self._toast is not None:
            return
        parent = self.centralWidget() if self.centralWidget() is not None else self
        self._toast = QLabel(parent)
        self._toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._toast.setText("")
        self._toast.setVisible(False)
        self._toast.setStyleSheet(
            "background-color: rgba(30, 30, 30, 200); color: white; padding: 8px 12px; border-radius: 10px;"
        )
        eff = QGraphicsOpacityEffect(self._toast)
        eff.setOpacity(0.0)
        self._toast.setGraphicsEffect(eff)

    def _show_toast(self, text: str):
        try:
            self._ensure_toast()
            if self._toast is None:
                return

            msg = (text or "").strip()
            if not msg:
                msg = "Hazır"
            self._toast.setText(msg)
            self._toast.adjustSize()

            parent = self._toast.parentWidget()
            if parent is None:
                return

            margin = 16
            x = max(margin, parent.width() - self._toast.width() - margin)
            y = max(margin, parent.height() - self._toast.height() - margin)
            target_pos = QPoint(x, y)

            eff = self._toast.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(self._toast)
                self._toast.setGraphicsEffect(eff)

            if self._toast_anim is not None:
                try:
                    self._toast_anim.stop()
                except Exception:
                    pass

            try:
                start_opacity = float(eff.opacity())
            except Exception:
                start_opacity = 0.0

            start_pos = self._toast.pos()
            if not self._toast.isVisible():
                start_pos = QPoint(target_pos.x(), target_pos.y() + 6)
                try:
                    eff.setOpacity(0.0)
                    start_opacity = 0.0
                except Exception:
                    pass

            self._toast.move(start_pos)

            self._toast.setVisible(True)

            a_in_op = QPropertyAnimation(eff, b"opacity", self._toast)
            a_in_op.setDuration(160)
            a_in_op.setStartValue(start_opacity)
            a_in_op.setEndValue(1.0)
            a_in_op.setEasingCurve(QEasingCurve.Type.OutCubic)

            a_in_pos = QPropertyAnimation(self._toast, b"pos", self._toast)
            a_in_pos.setDuration(200)
            a_in_pos.setStartValue(start_pos)
            a_in_pos.setEndValue(target_pos)
            a_in_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

            in_group = QParallelAnimationGroup(self._toast)
            in_group.addAnimation(a_in_op)
            in_group.addAnimation(a_in_pos)

            a_out_op = QPropertyAnimation(eff, b"opacity", self._toast)
            a_out_op.setDuration(240)
            a_out_op.setStartValue(1.0)
            a_out_op.setEndValue(0.0)
            a_out_op.setEasingCurve(QEasingCurve.Type.OutCubic)

            a_out_pos = QPropertyAnimation(self._toast, b"pos", self._toast)
            a_out_pos.setDuration(240)
            a_out_pos.setStartValue(target_pos)
            a_out_pos.setEndValue(QPoint(target_pos.x(), target_pos.y() - 4))
            a_out_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

            out_group = QParallelAnimationGroup(self._toast)
            out_group.addAnimation(a_out_op)
            out_group.addAnimation(a_out_pos)

            group = QSequentialAnimationGroup(self._toast)
            group.addAnimation(in_group)
            group.addPause(1250)
            group.addAnimation(out_group)

            def _finish():
                try:
                    eff.setOpacity(0.0)
                except Exception:
                    pass
                try:
                    self._toast.setVisible(False)
                except Exception:
                    pass
                self._toast_anim = None

            group.finished.connect(_finish)
            self._toast_anim = group
            group.start()
        except Exception:
            return

    def _set_active_menu_button(self, active_btn):
        for btn in getattr(self, "_menu_buttons", []):
            try:
                btn.setProperty("selected", btn is active_btn)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()
            except Exception:
                pass

    def _ensure_active_indicator(self):
        if self._active_indicator is not None:
            return
        if not hasattr(self, "menu_frame") or self.menu_frame is None:
            return

        # Sol tarafta aktif modülü gösteren ince bar
        self._active_indicator = QFrame(self.menu_frame)
        self._active_indicator.setObjectName("active_indicator")
        self._active_indicator.setStyleSheet("background-color: #984C00; border-radius: 3px;")
        self._active_indicator.setFixedWidth(6)
        self._active_indicator.setVisible(False)

    def _move_active_indicator(self, btn, animate: bool):
        if btn is None:
            return
        self._ensure_active_indicator()
        if self._active_indicator is None:
            return

        try:
            # Buton geometrisini menu_frame koordinatlarına çevir
            top_left = btn.mapTo(self.menu_frame, QPoint(0, 0))
            target = QRect(2, top_left.y() + 6, 6, max(10, btn.height() - 12))
            self._active_indicator.setVisible(True)

            if not animate:
                self._active_indicator.setGeometry(target)
                return

            if self._active_indicator_anim is not None:
                try:
                    self._active_indicator_anim.stop()
                except Exception:
                    pass

            start_rect = self._active_indicator.geometry()

            # Mesafeye göre süre: kısa mesafe hızlı, uzun mesafe daha yumuşak
            try:
                dist = abs(target.y() - start_rect.y())
            except Exception:
                dist = 0
            duration = int(160 + min(240, dist * 1.1))
            curve = QEasingCurve(QEasingCurve.Type.OutCubic)

            # Subtle settle: hedefi çok hafif geçip yerine otursun
            overshoot = QRect(target)
            try:
                delta = 2 if (target.y() - start_rect.y()) >= 0 else -2
                overshoot.moveTop(target.y() + delta)
            except Exception:
                pass

            a1 = QPropertyAnimation(self._active_indicator, b"geometry", self._active_indicator)
            a1.setDuration(int(duration * 0.7))
            a1.setStartValue(start_rect)
            a1.setEndValue(overshoot)
            a1.setEasingCurve(curve)

            a2 = QPropertyAnimation(self._active_indicator, b"geometry", self._active_indicator)
            a2.setDuration(int(duration * 0.45))
            a2.setStartValue(overshoot)
            a2.setEndValue(target)
            a2.setEasingCurve(QEasingCurve.Type.OutQuart)

            group = QSequentialAnimationGroup(self._active_indicator)
            group.addAnimation(a1)
            group.addAnimation(a2)
            self._active_indicator_anim = group
            group.start()
        except Exception:
            return

    def _animate_page_intro(self, widget):
        """Premium: küçük translate + fade-in (bounce yok, controlled easing)."""
        try:
            if widget is None:
                return

            # Önceki animasyon varsa durdur
            prev = self._page_intro_anims.get(widget)
            if prev is not None:
                try:
                    prev.stop()
                except Exception:
                    pass
                try:
                    self._page_intro_anims.pop(widget, None)
                except Exception:
                    pass

            end_pos = widget.pos()
            start_pos = QPoint(end_pos.x() + 18, end_pos.y() + 4)
            widget.move(start_pos)

            # Opacity effect (bitince kaldırıyoruz)
            eff = widget.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(eff)
            eff.setOpacity(0.0)

            pos_anim = QPropertyAnimation(widget, b"pos", widget)
            pos_anim.setDuration(220)
            pos_anim.setStartValue(start_pos)
            pos_anim.setEndValue(end_pos)
            pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            # Fade-in (login'deki gibi)
            fade = QPropertyAnimation(eff, b"opacity", widget)
            fade.setDuration(200)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QParallelAnimationGroup(widget)
            group.addAnimation(pos_anim)
            group.addAnimation(fade)

            def _finish():
                try:
                    widget.move(end_pos)
                except Exception:
                    pass
                try:
                    if isinstance(widget.graphicsEffect(), QGraphicsOpacityEffect):
                        widget.graphicsEffect().setOpacity(1.0)
                        widget.setGraphicsEffect(None)
                except Exception:
                    pass
                try:
                    self._page_intro_anims.pop(widget, None)
                except Exception:
                    pass

            group.finished.connect(_finish)
            self._page_intro_anims[widget] = group
            group.start()
        except Exception:
            return

    def _animate_widget_fade_in(self, widget):
        try:
            effect = widget.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(effect)

            effect.setOpacity(0.0)

            anim = self._fade_anims.get(widget)
            if anim is not None:
                try:
                    anim.stop()
                except Exception:
                    pass

            anim = QPropertyAnimation(effect, b"opacity", widget)
            anim.setDuration(160)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            def _finish():
                try:
                    effect.setOpacity(1.0)
                except Exception:
                    pass
                try:
                    self._fade_anims.pop(widget, None)
                except Exception:
                    pass

            anim.finished.connect(_finish)
            self._fade_anims[widget] = anim
            anim.start()
        except Exception:
            return

    def _setup_sidebar_toggle(self):
        if not hasattr(self, "btn_menu_toggle") or not hasattr(self, "menu_frame"):
            return

        self.btn_menu_toggle.clicked.connect(self._toggle_sidebar)
        self._sidebar_apply_state(collapsed=False, animate=False)

    def _toggle_sidebar(self):
        self._pulse_toggle_button()
        self._sidebar_apply_state(collapsed=not self._sidebar_is_collapsed, animate=True)

    def _pulse_toggle_button(self):
        if not hasattr(self, "btn_menu_toggle") or self.btn_menu_toggle is None:
            return

        btn = self.btn_menu_toggle
        try:
            # Press hissi: shadow blur + yOffset
            eff = btn.graphicsEffect()
            if eff is None or eff.metaObject().className() != "QGraphicsDropShadowEffect":
                from PyQt6.QtWidgets import QGraphicsDropShadowEffect

                eff = QGraphicsDropShadowEffect(btn)
                eff.setColor(QColor(0, 0, 0, 140))
                eff.setBlurRadius(0.0)
                eff.setXOffset(0.0)
                eff.setYOffset(0.0)
                btn.setGraphicsEffect(eff)

            if self._toggle_btn_anim is not None:
                try:
                    self._toggle_btn_anim.stop()
                except Exception:
                    pass

            a1 = QPropertyAnimation(eff, b"blurRadius", btn)
            a1.setDuration(160)
            a1.setStartValue(float(eff.blurRadius()))
            a1.setEndValue(22.0)
            a1.setEasingCurve(QEasingCurve.Type.OutCubic)

            a2 = QPropertyAnimation(eff, b"yOffset", btn)
            a2.setDuration(160)
            a2.setStartValue(float(eff.yOffset()))
            a2.setEndValue(6.0)
            a2.setEasingCurve(QEasingCurve.Type.OutCubic)

            a3 = QPropertyAnimation(eff, b"blurRadius", btn)
            a3.setDuration(260)
            a3.setStartValue(22.0)
            a3.setEndValue(0.0)
            a3.setEasingCurve(QEasingCurve.Type.OutCubic)

            a4 = QPropertyAnimation(eff, b"yOffset", btn)
            a4.setDuration(260)
            a4.setStartValue(6.0)
            a4.setEndValue(0.0)
            a4.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QSequentialAnimationGroup(btn)
            group.addAnimation(a1)
            group.addAnimation(a2)
            group.addPause(80)
            group.addAnimation(a3)
            group.addAnimation(a4)

            def _finish():
                self._toggle_btn_anim = None

            group.finished.connect(_finish)
            self._toggle_btn_anim = group
            group.start()
        except Exception:
            return

    def _sidebar_apply_state(self, collapsed: bool, animate: bool):
        if not hasattr(self, "menu_frame"):
            return

        self._sidebar_is_collapsed = collapsed
        target_width = self._sidebar_collapsed_width if collapsed else self._sidebar_expanded_width

        if hasattr(self, "btn_menu_toggle") and self.btn_menu_toggle is not None:
            self.btn_menu_toggle.setText("»" if collapsed else "☰")

        if animate:
            if self._sidebar_animation is not None:
                try:
                    self._sidebar_animation.stop()
                except Exception:
                    pass

            self.menu_frame.setMinimumWidth(0)
            self._sidebar_animation = QPropertyAnimation(self.menu_frame, b"maximumWidth")
            self._sidebar_animation.setDuration(420)
            self._sidebar_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._sidebar_animation.setStartValue(self.menu_frame.maximumWidth())
            self._sidebar_animation.setEndValue(target_width)
            self._sidebar_animation.finished.connect(lambda: self.menu_frame.setMinimumWidth(target_width))
            self._sidebar_animation.start()
        else:
            self.menu_frame.setMaximumWidth(target_width)

        if not animate:
            self.menu_frame.setMinimumWidth(target_width)

        if animate:
            self._sidebar_apply_text_stagger(collapsed=collapsed)
        else:
            # Text / tooltip yönetimi
            for btn in getattr(self, "_menu_buttons", []):
                full_text = self._menu_button_texts.get(btn, "")
                if collapsed:
                    btn.setToolTip(full_text)
                    btn.setText("")
                    btn.setStyleSheet("text-align:center; padding-left:0px; padding-right:0px;")
                    btn.setIconSize(QSize(24, 24))
                else:
                    btn.setText(full_text)
                    btn.setToolTip("")
                    btn.setStyleSheet("")
                    btn.setIconSize(QSize(22, 22))

    def _sidebar_apply_text_stagger(self, collapsed: bool):
        try:
            btns = list(getattr(self, "_menu_buttons", []) or [])
            if not btns:
                return

            for b in btns:
                try:
                    a = self._sidebar_text_anims.get(b)
                    if a is not None:
                        a.stop()
                except Exception:
                    pass
                try:
                    self._sidebar_text_anims.pop(b, None)
                except Exception:
                    pass

            delay_step = 120
            duration = 650

            for i, btn in enumerate(btns):
                full_text = self._menu_button_texts.get(btn, "")

                if collapsed:
                    btn.setToolTip(full_text)
                    btn.setStyleSheet("text-align:center; padding-left:0px; padding-right:0px;")
                    btn.setIconSize(QSize(24, 24))
                else:
                    btn.setText(full_text)
                    btn.setToolTip("")
                    btn.setStyleSheet("")
                    btn.setIconSize(QSize(22, 22))

                base_style = btn.styleSheet() or ""
                self._sidebar_text_base_styles[btn] = base_style

                try:
                    c = btn.palette().buttonText().color()
                    r, g, bb = int(c.red()), int(c.green()), int(c.blue())
                except Exception:
                    r, g, bb = 255, 255, 255

                start_a = 255 if collapsed else 0
                end_a = 0 if collapsed else 255

                anim = QVariantAnimation(btn)
                anim.setDuration(duration)
                anim.setStartValue(start_a)
                anim.setEndValue(end_a)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)

                # İlk frame'i zorla: böylece fade-in gerçekten 0'dan başlar.
                try:
                    st = self._sidebar_text_base_styles.get(btn, "")
                    btn.setStyleSheet(st + f"color: rgba({r},{g},{bb},{start_a});")
                except Exception:
                    pass

                def _on_val(v, b=btn, rr=r, gg=g, bbb=bb):
                    try:
                        a = int(v)
                    except Exception:
                        a = 255
                    try:
                        st = self._sidebar_text_base_styles.get(b, "")
                        b.setStyleSheet(st + f"color: rgba({rr},{gg},{bbb},{a});")
                    except Exception:
                        pass

                anim.valueChanged.connect(_on_val)

                def _finish(b=btn, is_collapsed=collapsed):
                    try:
                        st = self._sidebar_text_base_styles.get(b, "")
                        b.setStyleSheet(st)
                    except Exception:
                        pass
                    if is_collapsed:
                        try:
                            b.setText("")
                        except Exception:
                            pass
                    try:
                        self._sidebar_text_anims.pop(b, None)
                    except Exception:
                        pass

                anim.finished.connect(_finish)
                self._sidebar_text_anims[btn] = anim

                try:
                    QTimer.singleShot(i * delay_step, anim.start)
                except Exception:
                    anim.start()

            if collapsed:
                try:
                    if hasattr(self, "btn_menu_toggle") and self.btn_menu_toggle is not None:
                        self.btn_menu_toggle.setText("»")
                except Exception:
                    pass
        except Exception:
            return

    def _apply_menu_icons(self):
        if not getattr(self, "_menu_buttons", None):
            return

        # Load icons from filesystem to avoid rcc toolchain mismatch (PySide6 vs PyQt6)
        menu_icon_dir = os.path.join(ICONS_PATH, "menu")
        icon_map = {
            "btn_users": os.path.join(menu_icon_dir, "user-3-line.svg"),
            "btn_employees": os.path.join(menu_icon_dir, "team-line.svg"),
            "btn_customers": os.path.join(menu_icon_dir, "contacts-book-line.svg"),
            "btn_vehicles": os.path.join(menu_icon_dir, "bus-line.svg"),
            "btn_drivers": os.path.join(menu_icon_dir, "steering-2-line.svg"),
            "btn_repairs": os.path.join(menu_icon_dir, "tools-line.svg"),
            "btn_contracts": os.path.join(menu_icon_dir, "file-text-line.svg"),
            "btn_routes": os.path.join(menu_icon_dir, "route-line.svg"),
            "btn_trips": os.path.join(menu_icon_dir, "road-map-line.svg"),
            "btn_attendance": os.path.join(menu_icon_dir, "calendar-check-line.svg"),
            "btn_payments": os.path.join(menu_icon_dir, "money-dollar-circle-line.svg"),
            "btn_finance": os.path.join(menu_icon_dir, "pie-chart-2-line.svg"),
            "btn_constants": os.path.join(menu_icon_dir, "settings-3-line.svg"),
            "btn_reports": os.path.join(menu_icon_dir, "bar-chart-box-line.svg"),
            "btn_settings": os.path.join(menu_icon_dir, "settings-line.svg"),
        }
        fallback = ":/resim/arrow-down.png"

        for btn_name in getattr(self, "_menu_map", {}).keys():
            if not hasattr(self, btn_name):
                continue
            btn = getattr(self, btn_name)
            icon_path = icon_map.get(btn_name, fallback)
            if isinstance(icon_path, str) and os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
            else:
                btn.setIcon(QIcon(fallback))
            btn.setIconSize(QSize(22, 22))
    # --- Modül Fonksiyonları (Hepsi hazır, tıklandığında çalışır) ---
    def open_users(self):
    # 1. Eğer halihazırda bir modül varsa temizle (isteğe bağlı)
        for i in reversed(range(self.mainStack.count())): 
            widget = self.mainStack.widget(i)
            if widget.objectName() != "page_main": # Ana sayfa hariç temizle
                self.mainStack.removeWidget(widget)
                widget.deleteLater()

        # 2. UsersApp'i oluştur
        self.users_module = UsersApp()
        
        # 3. ÖNEMLİ: Pencere özelliklerini sıfırla ki popup gibi davranmasın
        self.users_module.setWindowFlags(Qt.WindowType.Widget) 
        
        # 4. mainStack'e ekle ve o sayfaya geç
        self.mainStack.addWidget(self.users_module)
        self.mainStack.setCurrentWidget(self.users_module)

    # Diğerleri için şimdilik terminale yazı yazdırıyoruz, hata vermezler.
    def open_employees(self):
        
        
        # 1. Eski modülleri güvenli bir şekilde temizle (Ana sayfa hariç)
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. Yeni modülü oluştur
        self.employees_module = EmployeesApp(user_data=self.user_data)
        # QStackedWidget içinde popup gibi davranmaması için Widget flag
        self.employees_module.setWindowFlags(Qt.WindowType.Widget)
        self.employees_module.setMinimumSize(0, 0)
        self.employees_module.setMinimumWidth(0)
        self.employees_module.setMinimumHeight(0)
        # ScrollArea içinde küçülebilsin (layout minimumSizeHint büyüklüğünü dayatmasın)
        self.employees_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        # Personel UI bazı makinelerde minimumSizeHint'i büyütebiliyor.
        # Bunu ana pencereye taşırmamak için QScrollArea içine alıyoruz.
        self.employees_scroll = QScrollArea()
        self.employees_scroll.setWidgetResizable(True)
        self.employees_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.employees_scroll.setWidget(self.employees_module)
        self.employees_scroll.setMinimumSize(0, 0)
        self.employees_scroll.setMinimumWidth(0)
        self.employees_scroll.setMinimumHeight(0)
        self.employees_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mainStack.addWidget(self.employees_scroll)
        self.mainStack.setCurrentWidget(self.employees_scroll)
        
        # 3. İLK TIKLAMADA TAM OTURMASI İÇİN SİHİRLİ DOKUNUŞ
        # Pencere zaten Maximized ise, layout'u yeniden hesaplamaya zorla
        self.layout().activate()

        # Personel UI bazı makinelerde ana pencerenin minimumSize değerini büyütebiliyor.
        # Bu da Windows tarafında setGeometry uyarıları + sağa kayma gibi davranışlara yol açıyor.
        # Bu yüzden minimum size kısıtını temizliyoruz.
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Bazı sistemlerde QStackedWidget içeriği değişince pencere restore/move yapabiliyor.
        # Maximized durumunu bir sonraki event loop turunda tekrar uygula.
        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)

    def open_customers(self):
        # 1. Eski modülleri güvenli bir şekilde temizle (Ana sayfa hariç)
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. Yeni modülü oluştur
        self.customers_module = CustomersApp(user_data=self.user_data)
        self.customers_module.setWindowFlags(Qt.WindowType.Widget)
        self.customers_module.setMinimumSize(0, 0)
        self.customers_module.setMinimumWidth(0)
        self.customers_module.setMinimumHeight(0)
        self.customers_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.customers_scroll = QScrollArea()
        self.customers_scroll.setWidgetResizable(True)
        self.customers_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.customers_scroll.setWidget(self.customers_module)
        self.customers_scroll.setMinimumSize(0, 0)
        self.customers_scroll.setMinimumWidth(0)
        self.customers_scroll.setMinimumHeight(0)
        self.customers_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mainStack.addWidget(self.customers_scroll)
        self.mainStack.setCurrentWidget(self.customers_scroll)

        self.layout().activate()
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)
    def open_vehicles(self):
        # 1. Eski modülleri güvenli bir şekilde temizle (Ana sayfa hariç)
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. Yeni modülü oluştur
        self.vehicles_module = VehiclesApp(user_data=self.user_data)
        self.vehicles_module.setWindowFlags(Qt.WindowType.Widget)
        self.vehicles_module.setMinimumSize(0, 0)
        self.vehicles_module.setMinimumWidth(0)
        self.vehicles_module.setMinimumHeight(0)
        self.vehicles_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.vehicles_scroll = QScrollArea()
        self.vehicles_scroll.setWidgetResizable(True)
        self.vehicles_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.vehicles_scroll.setWidget(self.vehicles_module)
        self.vehicles_scroll.setMinimumSize(0, 0)
        self.vehicles_scroll.setMinimumWidth(0)
        self.vehicles_scroll.setMinimumHeight(0)
        self.vehicles_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mainStack.addWidget(self.vehicles_scroll)
        self.mainStack.setCurrentWidget(self.vehicles_scroll)

        self.layout().activate()
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)
    def open_drivers(self):
        # 1. Eski modülleri güvenli bir şekilde temizle (Ana sayfa hariç)
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. Yeni modülü oluştur
        self.drivers_module = DriversApp(user_data=self.user_data)
        self.drivers_module.setWindowFlags(Qt.WindowType.Widget)
        self.drivers_module.setMinimumSize(0, 0)
        self.drivers_module.setMinimumWidth(0)
        self.drivers_module.setMinimumHeight(0)
        self.drivers_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.drivers_scroll = QScrollArea()
        self.drivers_scroll.setWidgetResizable(True)
        self.drivers_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.drivers_scroll.setWidget(self.drivers_module)
        self.drivers_scroll.setMinimumSize(0, 0)
        self.drivers_scroll.setMinimumWidth(0)
        self.drivers_scroll.setMinimumHeight(0)
        self.drivers_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mainStack.addWidget(self.drivers_scroll)
        self.mainStack.setCurrentWidget(self.drivers_scroll)

        self.layout().activate()
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)
    def open_repairs(self):
        # 1. Eski modülleri güvenli bir şekilde temizle (Ana sayfa hariç)
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. Yeni modülü oluştur
        self.repairs_module = RepairsApp(user_data=self.user_data)
        self.repairs_module.setWindowFlags(Qt.WindowType.Widget)
        self.repairs_module.setMinimumSize(0, 0)
        self.repairs_module.setMinimumWidth(0)
        self.repairs_module.setMinimumHeight(0)
        self.repairs_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.repairs_scroll = QScrollArea()
        self.repairs_scroll.setWidgetResizable(True)
        self.repairs_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.repairs_scroll.setWidget(self.repairs_module)
        self.repairs_scroll.setMinimumSize(0, 0)
        self.repairs_scroll.setMinimumWidth(0)
        self.repairs_scroll.setMinimumHeight(0)
        self.repairs_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mainStack.addWidget(self.repairs_scroll)
        self.mainStack.setCurrentWidget(self.repairs_scroll)

        self.layout().activate()
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)

    def open_contracts(self):
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()
        from app.modules.contracts import ContractsApp
        self.contracts_module = ContractsApp(user_data=self.user_data)
        self.contracts_module.setWindowFlags(Qt.WindowType.Widget)
        self.contracts_module.setMinimumSize(0, 0)
        self.contracts_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.contracts_scroll = QScrollArea()
        self.contracts_scroll.setWidgetResizable(True)
        self.contracts_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.contracts_scroll.setWidget(self.contracts_module)
        self.contracts_scroll.setMinimumSize(0, 0)
        self.contracts_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.mainStack.addWidget(self.contracts_scroll)
        self.mainStack.setCurrentWidget(self.contracts_scroll)
        self.layout().activate()
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)
    def open_routes(self):
        # 1. Eski modülleri güvenli bir şekilde temizle (Ana sayfa hariç)
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. Yeni modülü oluştur
        self.routes_module = RoutesApp(user_data=self.user_data)
        self.routes_module.setWindowFlags(Qt.WindowType.Widget)
        self.routes_module.setMinimumSize(0, 0)
        self.routes_module.setMinimumWidth(0)
        self.routes_module.setMinimumHeight(0)
        self.routes_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.routes_scroll = QScrollArea()
        self.routes_scroll.setWidgetResizable(True)
        self.routes_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.routes_scroll.setWidget(self.routes_module)
        self.routes_scroll.setMinimumSize(0, 0)
        self.routes_scroll.setMinimumWidth(0)
        self.routes_scroll.setMinimumHeight(0)
        self.routes_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mainStack.addWidget(self.routes_scroll)
        self.mainStack.setCurrentWidget(self.routes_scroll)

        self.layout().activate()
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)

    def open_trips(self):
        # 1. Eski modülleri güvenli bir şekilde temizle (Ana sayfa hariç)
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. Yeni modülü oluştur
        self.trips_module = TripsGridApp(user_data=self.user_data)
        self.trips_module.setWindowFlags(Qt.WindowType.Widget)
        self.trips_module.setMinimumSize(0, 0)
        self.trips_module.setMinimumWidth(0)
        self.trips_module.setMinimumHeight(0)
        self.trips_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.trips_scroll = QScrollArea()
        self.trips_scroll.setWidgetResizable(True)
        self.trips_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.trips_scroll.setWidget(self.trips_module)
        self.trips_scroll.setMinimumSize(0, 0)
        self.trips_scroll.setMinimumWidth(0)
        self.trips_scroll.setMinimumHeight(0)
        self.trips_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mainStack.addWidget(self.trips_scroll)
        self.mainStack.setCurrentWidget(self.trips_scroll)

        self.layout().activate()
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)

    def open_attendance(self):
        # 1. Eski modülleri güvenli bir şekilde temizle (Ana sayfa hariç)
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. Yeni modülü oluştur
        self.attendance_module = AttendanceApp(user_data=self.user_data, parent=self)
        self.attendance_module.setWindowFlags(Qt.WindowType.Widget)
        self.attendance_module.setMinimumSize(0, 0)
        self.attendance_module.setMinimumWidth(0)
        self.attendance_module.setMinimumHeight(0)
        self.attendance_module.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.attendance_scroll = QScrollArea()
        self.attendance_scroll.setWidgetResizable(True)
        self.attendance_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.attendance_scroll.setWidget(self.attendance_module)
        self.attendance_scroll.setMinimumSize(0, 0)
        self.attendance_scroll.setMinimumWidth(0)
        self.attendance_scroll.setMinimumHeight(0)
        self.attendance_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.mainStack.addWidget(self.attendance_scroll)
        self.mainStack.setCurrentWidget(self.attendance_scroll)

        self.layout().activate()
        self.setMinimumSize(0, 0)
        if self.centralWidget() is not None:
            self.centralWidget().setMinimumSize(0, 0)
        if hasattr(self, "mainStack") and self.mainStack is not None:
            self.mainStack.setMinimumSize(0, 0)
            self.mainStack.setMinimumWidth(0)
            self.mainStack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        QTimer.singleShot(0, self._force_maximized)
        QTimer.singleShot(50, self._force_maximized)

    def open_payments(self): print("Hakedişler modülü açılıyor...")
    def open_finance(self): print("Mali Yönetim modülü açılıyor...")
    def open_constants(self):
        for i in reversed(range(self.mainStack.count())):
            widget = self.mainStack.widget(i)
            if widget and widget.objectName() != "page_main":
                self.mainStack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # 2. ÖNCE VERİTABANI NESNESİNİ OLUŞTURUYORUZ (Bu eksikti)
        from app.core.db_manager import DatabaseManager
        db_mng = DatabaseManager() 
        
        # 3. MODÜLÜ AÇIYORUZ
        from app.modules.constants import ConstantsApp
        # Dosya adını senin istediğin gibi "constants_window.ui" olarak bıraktım
        self.constants_module = ConstantsApp(db_manager=db_mng, parent=self) 

        try:
            self.constants_module.onoff_settings_changed.connect(self.set_offline_policy)
        except Exception:
            pass
        
        self.mainStack.addWidget(self.constants_module)
        self.mainStack.setCurrentWidget(self.constants_module)








    def open_reports(self): print("Raporlar modülü açılıyor...")
    def open_settings(self): print("Ayarlar modülü açılıyor...")
