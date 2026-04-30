from models.database import get_db_connection


class CategoryModel:
    @staticmethod
    def get_all():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
                SELECT c.id, c.name, c.description, c.created_at,
                       COUNT(p.id) AS product_count
                FROM categories c
                LEFT JOIN products p ON p.category_id = c.id
                GROUP BY c.id, c.name, c.description, c.created_at
                ORDER BY c.id DESC
            """
        )
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result

    @staticmethod
    def get_by_id(category_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, description, created_at FROM categories WHERE id = %s",
            (category_id,),
        )
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    @staticmethod
    def create(name, description):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO categories (name, description) VALUES (%s, %s)",
                (name, description),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print('Loi khi tao danh muc:', e)
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update(category_id, name, description):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE categories SET name = %s, description = %s WHERE id = %s",
                (name, description, category_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print('Loi khi cap nhat danh muc:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def delete(category_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM categories WHERE id = %s", (category_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print('Loi khi xoa danh muc:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def has_products(category_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products WHERE category_id = %s", (category_id,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count > 0


class ProductModel:
    @staticmethod
    def get_all():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
                SELECT p.id, p.category_id, c.name AS category_name, p.name, p.description,
                       p.price, p.stock, p.image_url, p.status, p.created_at
                FROM products p
                JOIN categories c ON c.id = p.category_id
                ORDER BY p.id DESC
            """
        )
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result

    @staticmethod
    def get_by_id(product_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
                SELECT p.id, p.category_id, c.name AS category_name, p.name, p.description,
                       p.price, p.stock, p.image_url, p.status, p.created_at
                FROM products p
                JOIN categories c ON c.id = p.category_id
                WHERE p.id = %s
            """,
            (product_id,),
        )
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    @staticmethod
    def create(category_id, name, description, price, stock, image_url, status):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    INSERT INTO products (category_id, name, description, price, stock, image_url, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (category_id, name, description, price, stock, image_url, status),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print('Loi khi tao san pham:', e)
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update(product_id, category_id, name, description, price, stock, image_url, status):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    UPDATE products
                    SET category_id = %s,
                        name = %s,
                        description = %s,
                        price = %s,
                        stock = %s,
                        image_url = %s,
                        status = %s
                    WHERE id = %s
                """,
                (category_id, name, description, price, stock, image_url, status, product_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print('Loi khi cap nhat san pham:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def delete(product_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print('Loi khi xoa san pham:', e)
            return False
        finally:
            cursor.close()
            conn.close()
