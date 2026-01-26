import os

import traceback

from PyQt6.QtWidgets import QMainWindow, QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QLabel, QGraphicsColorizeEffect
from PyQt6.QtGui import QPixmap, QIcon, QColor
from PyQt6.QtCore import QSize
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, QEvent, QPoint

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

class MainMenuApp(QMainWindow):
    def __init__(self, user_data=None):
        super().__init__()
        uic.loadUi(get_ui_path("main_window.ui"), self)
        # clear_all_styles(self)
        self.user_data = user_data

        self._menu_buttons = []
        self._menu_button_texts = {}
        self._sidebar_expanded_width = 200
        self._sidebar_collapsed_width = 60
        self._sidebar_animation = None
        self._sidebar_is_collapsed = False
        self._fade_anims = {}
        self._title_pulse_anim = None
        self._title_base_stylesheet = ""
        self._toast = None
        self._toast_anim = None
        self._hover_anims = {}
        self._toggle_btn_anim = None
        self._slide_anims = {}

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
        self.lbl_title.setText("SAKARYA ASİL TUR TAŞIMACILIK HİZMETLERİ UYGULAMASI")
        try:
            if hasattr(self, "lbl_title") and self.lbl_title is not None:
                self._title_base_stylesheet = self.lbl_title.styleSheet() or ""
        except Exception:
            self._title_base_stylesheet = ""
        
        # Menü sistemini ateşle
        self.setup_menu()

        self._setup_sidebar_toggle()
        self._apply_menu_icons()

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

    def eventFilter(self, obj, event):
        try:
            if obj in getattr(self, "_menu_buttons", []):
                if event.type() == QEvent.Type.Enter:
                    self._animate_menu_hover(obj, entering=True)
                elif event.type() == QEvent.Type.Leave:
                    self._animate_menu_hover(obj, entering=False)
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _animate_menu_hover(self, btn, entering: bool):
        try:
            eff = btn.graphicsEffect()
            if eff is None or eff.metaObject().className() != "QGraphicsDropShadowEffect":
                from PyQt6.QtWidgets import QGraphicsDropShadowEffect

                eff = QGraphicsDropShadowEffect(btn)
                eff.setColor(QColor(0, 0, 0, 110))
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

            end_blur = 18.0 if entering else 0.0
            end_y = 4.0 if entering else 0.0

            a1 = QPropertyAnimation(eff, b"blurRadius", btn)
            a1.setDuration(140)
            a1.setStartValue(float(eff.blurRadius()))
            a1.setEndValue(end_blur)
            a1.setEasingCurve(QEasingCurve.Type.OutCubic)

            a2 = QPropertyAnimation(eff, b"yOffset", btn)
            a2.setDuration(140)
            a2.setStartValue(float(eff.yOffset()))
            a2.setEndValue(end_y)
            a2.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QSequentialAnimationGroup(btn)
            group.addAnimation(a1)
            group.addPause(140)
            group.addAnimation(a2)

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

    def handle_menu_click(self, button, open_func):
        """lbl_title'ı günceller, modülü açar ve tıklanan butonu kilitler"""
        # Başlığı ve modülü aç
        self.lbl_title.setText(self._menu_button_texts.get(button, button.text()))
        button.setChecked(True)
        self._set_active_menu_button(button)
        try:
            open_func()
        except Exception:
            traceback.print_exc()

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

        self._pulse_title()
        self._show_toast(self.lbl_title.text())
        if current is not None:
            self._animate_slide_in(current)

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
            self._toast.move(x, y)

            eff = self._toast.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(self._toast)
                self._toast.setGraphicsEffect(eff)

            if self._toast_anim is not None:
                try:
                    self._toast_anim.stop()
                except Exception:
                    pass

            self._toast.setVisible(True)

            a_in = QPropertyAnimation(eff, b"opacity", self._toast)
            a_in.setDuration(120)
            a_in.setStartValue(0.0)
            a_in.setEndValue(1.0)
            a_in.setEasingCurve(QEasingCurve.Type.OutCubic)

            a_out = QPropertyAnimation(eff, b"opacity", self._toast)
            a_out.setDuration(220)
            a_out.setStartValue(1.0)
            a_out.setEndValue(0.0)
            a_out.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QSequentialAnimationGroup(self._toast)
            group.addAnimation(a_in)
            group.addPause(900)
            group.addAnimation(a_out)

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
                if btn is active_btn:
                    btn.setProperty("flash", True)
                    QTimer.singleShot(650, lambda b=btn: b.setProperty("flash", False))
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()
            except Exception:
                pass

        # flash property reset sonrası da QSS yeniden uygulansın
        try:
            if active_btn is not None:
                QTimer.singleShot(660, lambda b=active_btn: (b.style().unpolish(b), b.style().polish(b), b.update()))
        except Exception:
            pass

    def _animate_slide_in(self, widget):
        try:
            anim = self._slide_anims.get(widget)
            if anim is not None:
                try:
                    anim.stop()
                except Exception:
                    pass

            end_pos = widget.pos()
            start_pos = QPoint(end_pos.x() + 100, end_pos.y())
            widget.move(start_pos)

            anim = QPropertyAnimation(widget, b"pos", widget)
            anim.setDuration(240)
            anim.setStartValue(start_pos)
            anim.setEndValue(end_pos)
            anim.setEasingCurve(QEasingCurve.Type.OutBack)

            def _finish():
                try:
                    widget.move(end_pos)
                except Exception:
                    pass
                try:
                    self._slide_anims.pop(widget, None)
                except Exception:
                    pass

            anim.finished.connect(_finish)
            self._slide_anims[widget] = anim
            anim.start()
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
            base_ss = btn.styleSheet() or ""
        except Exception:
            base_ss = ""

        try:
            btn.setStyleSheet(base_ss + "background-color: rgba(255, 224, 178, 240);")
            try:
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()
            except Exception:
                pass
            QTimer.singleShot(520, lambda: btn.setStyleSheet(base_ss))
        except Exception:
            pass

        try:
            eff = btn.graphicsEffect()
            if not isinstance(eff, QGraphicsColorizeEffect):
                eff = QGraphicsColorizeEffect(btn)
                eff.setColor(QColor("#984C00"))
                btn.setGraphicsEffect(eff)

            if self._toggle_btn_anim is not None:
                try:
                    self._toggle_btn_anim.stop()
                except Exception:
                    pass

            a1 = QPropertyAnimation(eff, b"strength", btn)
            a1.setDuration(180)
            a1.setStartValue(0.0)
            a1.setEndValue(1.0)
            a1.setEasingCurve(QEasingCurve.Type.OutCubic)

            a2 = QPropertyAnimation(eff, b"strength", btn)
            a2.setDuration(360)
            a2.setStartValue(1.0)
            a2.setEndValue(0.0)
            a2.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QSequentialAnimationGroup(btn)
            group.addAnimation(a1)
            group.addAnimation(a2)

            def _finish():
                try:
                    eff.setStrength(0.0)
                except Exception:
                    pass
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
            self._sidebar_animation.setDuration(220)
            self._sidebar_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._sidebar_animation.setStartValue(self.menu_frame.maximumWidth())
            self._sidebar_animation.setEndValue(target_width)
            self._sidebar_animation.finished.connect(lambda: self.menu_frame.setMinimumWidth(target_width))
            self._sidebar_animation.start()
        else:
            self.menu_frame.setMaximumWidth(target_width)

        if not animate:
            self.menu_frame.setMinimumWidth(target_width)

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
        
        self.mainStack.addWidget(self.constants_module)
        self.mainStack.setCurrentWidget(self.constants_module)








    def open_reports(self): print("Raporlar modülü açılıyor...")
    def open_settings(self): print("Ayarlar modülü açılıyor...")
