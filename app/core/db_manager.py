import sqlite3
import os
from config import DB_PATH, BASE_DIR

class DatabaseManager:
    def __init__(self):
        self.db_path = DB_PATH
        self.create_tables()
        self.create_employees_table()
        self.create_constants_table()
    
    def connect(self):
        try:
            # check_same_thread=False ekliyoruz ki farklı modüllerden erişirken sorun çıkmasın
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            return conn
        except Exception as e:
            print(f"Database connection error: {e}")
            return None

    def create_tables(self):
        conn = self.connect()
        if conn:
            cursor = conn.cursor()
            
            # 1. USERS (Personeller/Kullanıcılar)
            cursor.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                full_name TEXT,
                role TEXT,
                is_active INTEGER DEFAULT 1
            )""")

            # 2. CUSTOMERS (Müşteriler)
            cursor.execute("""CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT UNIQUE,
                title TEXT NOT NULL,
                tax_office TEXT,
                tax_number TEXT,
                address TEXT,
                phone TEXT,
                email TEXT,
                is_active INTEGER DEFAULT 1
            )""")

            # 3. VEHICLES (Araçlar)
            cursor.execute("""CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT UNIQUE NOT NULL,
                brand TEXT,
                model TEXT,
                capacity INTEGER,
                fuel_type TEXT,
                daily_cost REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )""")

            # 4. CONTRACTS (Sözleşmeler)
            cursor.execute("""CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                contract_number TEXT UNIQUE,
                start_date TEXT,
                end_date TEXT,
                contract_type TEXT,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )""")

            # 5. TRIPS (Seferler - Operasyonun Kalbi)
            cursor.execute("""CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER,
                vehicle_id INTEGER,
                user_id INTEGER,
                trip_date TEXT,
                route_info TEXT,
                status TEXT DEFAULT 'Planned',
                FOREIGN KEY (contract_id) REFERENCES contracts (id),
                FOREIGN KEY (vehicle_id) REFERENCES vehicles (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )""")
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO users (username, password, full_name, role, is_active)
                    VALUES ('admin', '1234', 'SATTUP Admin', 'admin', 1)
                """)
                print("Bilgi: İlk admin kullanıcısı (admin/1234) oluşturuldu.")

            conn.commit()
            conn.close()

    # --- PERSONEL (EMPLOYEES) MODÜLÜ METODLARI ---

    def create_employees_table(self):
        """Senin formundaki tüm alanları içeren tabloyu oluşturur"""
        query = """
        CREATE TABLE IF NOT EXISTS employees (
            personel_kodu TEXT PRIMARY KEY,
            personel_turu TEXT, tckn TEXT, ad_soyad TEXT,
            anne_adi TEXT, baba_adi TEXT, dogum_yeri TEXT, dogum_tarihi TEXT,
            gsm TEXT, email TEXT, gorevi TEXT, kan_grubu TEXT,
            il TEXT, ilce TEXT, adres1 TEXT, adres2 TEXT,
            banka_adi TEXT, iban TEXT, notlar1 TEXT, notlar2 TEXT,
            photo_path TEXT,
            is_active INTEGER DEFAULT 1
        )
        """
        conn = self.connect()
        if conn:
            try:
                conn.execute(query)
                conn.commit()

                # Backward-compatible migration: eski DB'lerde photo_path kolonu olmayabilir
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(employees)")
                cols = {row[1] for row in cursor.fetchall()}
                if "photo_path" not in cols:
                    cursor.execute("ALTER TABLE employees ADD COLUMN photo_path TEXT")
                    conn.commit()
            finally:
                conn.close()

    def save_employee(self, data, is_update=False):
        """Personel kaydeder veya günceller (Sözlük yapısıyla çalışır)"""
        conn = self.connect()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            if is_update:
                # Dinamik UPDATE sorgusu
                placeholders = ", ".join([f"{key} = ?" for key in data.keys() if key != "personel_kodu"])
                values = [v for k, v in data.items() if k != "personel_kodu"]
                values.append(data["personel_kodu"])
                query = f"UPDATE employees SET {placeholders} WHERE personel_kodu = ?"
                cursor.execute(query, tuple(values))
            else:
                # INSERT sorgusu
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?" for _ in data.keys()])
                query = f"INSERT INTO employees ({columns}) VALUES ({placeholders})"
                cursor.execute(query, tuple(list(data.values())))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Personel Kayıt Hatası: {e}")
            return False
        finally:
            conn.close()

    def get_all_employees(self):
        """Tüm personel listesini getirir"""
        conn = self.connect()
        if not conn: return []
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE is_active = 1")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_employee_details(self, kodu):
        """Formu doldurmak için tüm detayları getirir"""
        conn = self.connect()
        if not conn: return None
        conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM employees WHERE personel_kodu = ?", (kodu,))
            return cursor.fetchone()
        finally:
            conn.close()
    
    def check_tckn_exists(self, tckn, current_kod=None):
        """TCKN'nin veritabanında olup olmadığını kontrol eder."""
        conn = self.connect()
        cursor = conn.cursor()
        # Eğer güncelleme yapılıyorsak (current_kod varsa), personelin kendi kodunu sorgu dışı bırak
        if current_kod:
            query = "SELECT 1 FROM employees WHERE tckn = ? AND personel_kodu != ?"
            cursor.execute(query, (tckn, current_kod))
        else:
            query = "SELECT 1 FROM employees WHERE tckn = ?"
            cursor.execute(query, (tckn,))
        
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def check_iban_exists(self, iban, current_kod=None):
        """IBAN'ın veritabanında olup olmadığını kontrol eder."""
        conn = self.connect()
        cursor = conn.cursor()
        if current_kod:
            query = "SELECT 1 FROM employees WHERE iban = ? AND personel_kodu != ?"
            cursor.execute(query, (iban, current_kod))
        else:
            query = "SELECT 1 FROM employees WHERE iban = ?"
            cursor.execute(query, (iban,))
        
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def delete_employee(self, kodu):
        """Personeli koduna göre siler"""
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM employees WHERE personel_kodu = ?", (kodu,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Silme hatası: {e}")
            return False
        finally:
            conn.close()

    def get_employee_active_status(self, kodu):
        conn = self.connect()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM employees WHERE personel_kodu = ?", (kodu,))
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()

    def set_employee_active_status(self, kodu, is_active: int):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE employees SET is_active = ? WHERE personel_kodu = ?",
                (1 if int(is_active) else 0, kodu),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Aktif/Pasif güncelleme hatası: {e}")
            return False
        finally:
            conn.close()

    def toggle_employee_active_status(self, kodu):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM employees WHERE personel_kodu = ?", (kodu,))
            row = cursor.fetchone()
            if row and row[0] is not None:
                new_status = 1 if row[0] == 0 else 0
                cursor.execute("UPDATE employees SET is_active = ? WHERE personel_kodu = ?", (new_status, kodu))
                conn.commit()
                return cursor.rowcount > 0
            else:
                return False
        except Exception as e:
            print(f"Aktif/Pasif güncelleme hatası: {e}")
            return False
        finally:
            conn.close()

    def get_last_value(self, table, column):
        """Herhangi bir tablodaki son değeri getirir"""
        query = f"SELECT {column} FROM {table} ORDER BY rowid DESC LIMIT 1"
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def get_personel_by_kod(self, p_kodu):
        """Veritabanından tek bir personelin tüm bilgilerini getirir"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE personel_kodu = ?", (p_kodu,))
        row = cursor.fetchone()
        conn.close()
        return row
    
    def create_constants_table(self):
        """Sabitleri tutacak hiyerarşik tabloyu oluşturur."""
        query = """
        CREATE TABLE IF NOT EXISTS constants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,  -- 'banka', 'il', 'gorev' vb.
            value TEXT NOT NULL,       -- 'Ziraat', 'Sakarya', 'Şoför' vb.
            parent_id INTEGER,         -- İlçe ise ilin id'sini tutar
            FOREIGN KEY (parent_id) REFERENCES constants (id)
        )
        """
        conn = self.connect()
        conn.execute(query)
        conn.commit()
        conn.close()

    def get_constants(self, group_name, parent_id=None):
        """Belirli bir gruptaki sabitleri getirir."""
        conn = self.connect()
        cursor = conn.cursor()
        if parent_id is not None:
            cursor.execute("SELECT id, value FROM constants WHERE group_name = ? AND parent_id = ?", (group_name, parent_id))
        else:
            cursor.execute("SELECT id, value FROM constants WHERE group_name = ? AND parent_id IS NULL", (group_name,))
        data = cursor.fetchall()
        conn.close()
        return data

    def update_or_insert_constant(self, group_name, value, constant_id=None, parent_id=None):
        """Sabit ekler veya günceller."""
        conn = self.connect()
        cursor = conn.cursor()
        if constant_id:
            cursor.execute("UPDATE constants SET value = ? WHERE id = ?", (value, constant_id))
        else:
            cursor.execute("INSERT INTO constants (group_name, value, parent_id) VALUES (?, ?, ?)", (group_name, value, parent_id))
            constant_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return constant_id

    def delete_constant(self, constant_id):
        """Sabiti siler."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM constants WHERE id = ? OR parent_id = ?", (constant_id, constant_id))
        conn.commit()
        conn.close()