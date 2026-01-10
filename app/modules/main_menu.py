import os

from PyQt6.QtWidgets import QMainWindow, QScrollArea, QSizePolicy
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QSize
from PyQt6.QtCore import Qt, QTimer 

from PyQt6 import uic
from config import ASSETS_DIR, get_ui_path
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

class MainMenuApp(QMainWindow):
    def __init__(self, user_data=None):
        super().__init__()
        uic.loadUi(get_ui_path("main_window.ui"), self)
        clear_all_styles(self)
        self.user_data = user_data

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
        
        # Menü sistemini ateşle
        self.setup_menu()

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
        menu_map = {
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

        for btn_name, open_func in menu_map.items():
            if hasattr(self, btn_name):
                btn = getattr(self, btn_name)
                # handle_menu_click: Hem başlığı değiştirir hem ilgili modülü açar
                btn.clicked.connect(lambda checked, b=btn, f=open_func: self.handle_menu_click(b, f))

    def handle_menu_click(self, button, open_func):
        """lbl_title'ı günceller, modülü açar ve tıklanan butonu kilitler"""
        
        # 1. Önce tüm butonları aktif (Enabled) yap ki bir önceki kilit kalksın
        for btn_name in ["btn_users", "btn_employees", "btn_customers", "btn_vehicles", 
                         "btn_drivers", "btn_repairs", "btn_contracts", "btn_routes", 
                         "btn_trips", "btn_attendance", "btn_payments", "btn_finance", 
                         "btn_constants", "btn_reports", "btn_settings"]:
            if hasattr(self, btn_name):
                getattr(self, btn_name).setEnabled(True)

        # 2. Tıklanan butonu pasif (Disabled) yap
        button.setEnabled(False)

        # 3. Başlığı ve modülü aç
        self.lbl_title.setText(button.text())
        open_func()
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
        # 1. Temizlik (Burası sende doğruydu)
        while self.mainStack.count() > 0:
            widget = self.mainStack.widget(0)
            self.mainStack.removeWidget(widget)
            if widget:
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
