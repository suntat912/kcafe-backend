from models.database import get_db_connection

# CHÍNH LÀ DÒNG NÀY ĐÂY! Bắt buộc phải có chữ UserModel viết hoa
class UserModel:
    
    @staticmethod
    def get_user_by_email(email):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return user

    @staticmethod
    def create_user(full_name, phone, email, hashed_password):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            sql = "INSERT INTO users (full_name, phone, email, password, role) VALUES (%s, %s, %s, %s, %s)"
            val = (full_name, phone, email, hashed_password, 'customer')
            cursor.execute(sql, val)
            conn.commit()
            return True
        except Exception as e:
            print("Lỗi khi tạo user:", e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_user_by_id(user_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return user

    @staticmethod
    def update_profile(user_id, full_name, phone, email, address):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            sql = """
                UPDATE users
                SET full_name = %s, phone = %s, email = %s, address = %s
                WHERE id = %s
            """
            cursor.execute(sql, (full_name, phone, email, address, user_id))
            conn.commit()
            return True
        except Exception as e:
            print("Loi khi cap nhat profile:", e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_password(user_id, hashed_password):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET password = %s WHERE id = %s",
                (hashed_password, user_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print("Loi khi doi mat khau:", e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_avatar(user_id, avatar_filename):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET avatar = %s WHERE id = %s",
                (avatar_filename, user_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print("Loi khi cap nhat avatar:", e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_all_users():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, full_name, phone, email, role, address, avatar, created_at FROM users ORDER BY id DESC"
        )
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return users

    @staticmethod
    def update_role(user_id, role):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET role = %s WHERE id = %s",
                (role, user_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print("Loi khi cap nhat role:", e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def create_user_by_admin(full_name, phone, email, hashed_password, role, address):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    INSERT INTO users (full_name, phone, email, password, role, address)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (full_name, phone, email, hashed_password, role, address),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print("Loi khi admin tao tai khoan:", e)
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_user_admin(user_id, full_name, phone, email, role, address):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    UPDATE users
                    SET full_name = %s, phone = %s, email = %s, role = %s, address = %s
                    WHERE id = %s
                """,
                (full_name, phone, email, role, address, user_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print("Loi khi admin cap nhat tai khoan:", e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def delete_user(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print("Loi khi xoa tai khoan:", e)
            return False
        finally:
            cursor.close()
            conn.close()
