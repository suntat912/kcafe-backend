from datetime import datetime

from models.database import get_db_connection


class EmailVerificationModel:
    @staticmethod
    def ensure_table():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS email_verifications (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        full_name VARCHAR(255) NOT NULL,
                        phone VARCHAR(50) NULL,
                        email VARCHAR(255) NOT NULL UNIQUE,
                        hashed_password TEXT NOT NULL,
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
    def upsert_pending(full_name, phone, email, hashed_password, verification_code, expires_at):
        EmailVerificationModel.ensure_table()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    INSERT INTO email_verifications (
                        full_name, phone, email, hashed_password, verification_code, expires_at, verified
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE
                        full_name = VALUES(full_name),
                        phone = VALUES(phone),
                        hashed_password = VALUES(hashed_password),
                        verification_code = VALUES(verification_code),
                        expires_at = VALUES(expires_at),
                        verified = 0,
                        created_at = CURRENT_TIMESTAMP
                """,
                (full_name, phone, email, hashed_password, verification_code, expires_at),
            )
            conn.commit()
            return True
        except Exception as error:
            print('Loi khi luu ma xac thuc email:', error)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_by_email(email):
        EmailVerificationModel.ensure_table()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM email_verifications WHERE email = %s", (email,))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def mark_verified(email):
        EmailVerificationModel.ensure_table()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE email_verifications SET verified = 1 WHERE email = %s",
                (email,),
            )
            conn.commit()
            return True
        except Exception as error:
            print('Loi khi cap nhat email verification:', error)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def delete(email):
        EmailVerificationModel.ensure_table()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM email_verifications WHERE email = %s", (email,))
            conn.commit()
            return True
        except Exception as error:
            print('Loi khi xoa email verification:', error)
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
