from datetime import datetime

from models.database import get_db_connection


class PasswordResetModel:
    @staticmethod
    def ensure_table():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS password_resets (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        email VARCHAR(255) NOT NULL UNIQUE,
                        verification_code VARCHAR(10) NOT NULL,
                        expires_at DATETIME NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        verified TINYINT(1) DEFAULT 0
                    )
                """
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def upsert_pending(email, verification_code, expires_at):
        PasswordResetModel.ensure_table()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    INSERT INTO password_resets (email, verification_code, expires_at, verified)
                    VALUES (%s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE
                        verification_code = VALUES(verification_code),
                        expires_at = VALUES(expires_at),
                        verified = 0,
                        created_at = CURRENT_TIMESTAMP
                """,
                (email, verification_code, expires_at),
            )
            conn.commit()
            return True
        except Exception as error:
            print('Loi khi luu ma dat lai mat khau:', error)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_by_email(email):
        PasswordResetModel.ensure_table()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM password_resets WHERE email = %s", (email,))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def delete(email):
        PasswordResetModel.ensure_table()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM password_resets WHERE email = %s", (email,))
            conn.commit()
            return True
        except Exception as error:
            print('Loi khi xoa reset password:', error)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def is_code_valid(record, code):
        if not record:
            return False
        if int(record.get('verified') or 0) == 1:
            return False
        if str(record.get('verification_code') or '').strip() != str(code or '').strip():
            return False

        expires_at = record.get('expires_at')
        if isinstance(expires_at, str):
            expires_at = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S')

        return bool(expires_at and expires_at >= datetime.now())
