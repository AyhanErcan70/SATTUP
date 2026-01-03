import os, sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    import config
except ImportError:
    # Eğer yukarıdaki tutmazsa alternatif yol
    from app import config
from PyQt6.QtWidgets import QDialog, QMessageBox, QGraphicsOpacityEffect
from PyQt6.QtCore import QPropertyAnimation, QPoint, QEasingCurve, QSequentialAnimationGroup, QParallelAnimationGroup, Qt, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6 import uic
from PyQt6.QtCore import QTimer
import ui.icons.resource_rc
from config import get_ui_path, BASE_DIR
from app.core.db_manager import DatabaseManager

class AuthApp(QDialog):
    def __init__(self):
        super().__init__()
        # 1. UI Yükleme (Yeni yol yapısı)
        ui_path = get_ui_path("auth_window.ui")
        uic.loadUi(ui_path, self)
        
        self.db = DatabaseManager()
        self.deneme_hakki = 3
        self.user_data = None

        # 2. Stil ve Arka Plan Düzeltmesi
        # self.load_styles()

        # --- SES AYARI (C:\ASIL\assets\sounds\viss.wav) ---
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        sound_path = os.path.join(BASE_DIR, "assets", "sounds", "viss.wav")
        self.player.setSource(QUrl.fromLocalFile(sound_path))
        self.audio_output.setVolume(0.5)

        # --- NESNELERİ BAŞLANGIÇTA GİZLE (Fade-in için) ---
        # Nesne isimlerini yeni btn_login ve txt_user formatına göre güncelledim
        self.fade_widgets = [
            self.txt_user, self.txt_pass, 
            self.btn_login, self.btn_cancel,
            self.lbl_welcome, self.lbl_login
        ]
        for widget in self.fade_widgets:
            eff = QGraphicsOpacityEffect()
            widget.setGraphicsEffect(eff)
            eff.setOpacity(0)

        # --- BUTON BAĞLANTILARI ---
        self.btn_login.clicked.connect(self.handle_login)
        self.btn_cancel.clicked.connect(self.reject)
        
        # --- EFSANE VISS ANİMASYONUNU BAŞLAT ---
        self.viss_animasyonu()

        if hasattr(config, 'DEBUG') and config.DEBUG:
            self.txt_username.setText("admin")
            self.txt_password.setText("1234")
            # Hatta istersen direkt giriş butonuna tıklatabilirsin:
            QTimer.singleShot(100, self.handle_login)

    def viss_animasyonu(self):
        """Formu sol üstten alıp merkeze getiren 'vışşş' hareketi"""
        self.move(-self.width(), -self.height())
        
        # 1. Yatay Kayma
        anim1 = QPropertyAnimation(self, b"pos")
        anim1.setDuration(800)
        anim1.setEndValue(QPoint(600, 50))
        anim1.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # 2. Merkeze İniş (Zıplayarak)
        anim2 = QPropertyAnimation(self, b"pos")
        anim2.setDuration(1500)
        screen_geo = self.screen().availableGeometry()
        center_point = screen_geo.center() - self.rect().center()
        anim2.setEndValue(center_point)
        anim2.setEasingCurve(QEasingCurve.Type.OutBounce)

        # Ses çalma tetikleyici
        anim1.stateChanged.connect(lambda s: self.player.play() if s == QPropertyAnimation.State.Running else None)

        self.group = QSequentialAnimationGroup()
        self.group.addAnimation(anim1)
        self.group.addAnimation(anim2)
        self.group.finished.connect(self.nesneleri_belirginlestir)
        self.group.start()

    def nesneleri_belirginlestir(self):
        """Fade-in etkisi"""
        self.fade_group = QParallelAnimationGroup()
        for widget in self.fade_widgets:
            anim = QPropertyAnimation(widget.graphicsEffect(), b"opacity")
            anim.setDuration(1000)
            anim.setStartValue(0)
            anim.setEndValue(1)
            self.fade_group.addAnimation(anim)
        self.fade_group.start()

    def handle_login(self):
        """Giriş kontrolü ve DB sorgusu"""
        username = self.txt_user.text().strip()
        password = self.txt_pass.text().strip()

        conn = self.db.connect()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
            user = cursor.fetchone()
            conn.close()

            if user:
                try:
                    self.user_data = {
                        "id": user[0],
                        "username": user[1],
                        "full_name": user[3],
                        "role": user[4],
                        "is_active": user[5],
                    }
                except Exception:
                    self.user_data = None
                self.accept()
            else:
                self.deneme_hakki -= 1
                if self.deneme_hakki > 0:
                    QMessageBox.warning(self, "Hata", f"Hatalı Giriş! Kalan Hak: {self.deneme_hakki}")
                else:
                    QMessageBox.critical(self, "Kilitlendi", "3 kez hatalı giriş yapıldı!")
                    self.reject()