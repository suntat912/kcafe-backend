from models.database import get_db_connection
import json
import os
from datetime import datetime, timedelta


class OrderModel:
    @staticmethod
    def _get_payment_defaults():
        return {
            'gateway': os.getenv('PAYMENT_PROVIDER', 'vietqr'),
            'bank_code': os.getenv('PAYMENT_BANK_CODE', 'VCB'),
            'account_no': os.getenv('PAYMENT_ACCOUNT_NO', '1027982130'),
        }

    @staticmethod
    def ensure_discount_tables():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS discount_codes (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        code VARCHAR(50) NOT NULL UNIQUE,
                        discount_type ENUM('percent', 'fixed') NOT NULL,
                        discount_value INT NOT NULL,
                        min_order_value INT DEFAULT 0,
                        expires_at DATETIME NULL,
                        active TINYINT(1) DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
            )
            cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS order_discounts (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        order_id INT NOT NULL,
                        discount_code_id INT NULL,
                        code VARCHAR(50) NOT NULL,
                        discount_type ENUM('percent', 'fixed') NOT NULL,
                        discount_value INT NOT NULL,
                        discount_amount INT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
                    )
                """
            )
            cursor.execute("SELECT COUNT(*) FROM discount_codes")
            count = cursor.fetchone()[0]
            if count == 0:
                cursor.executemany(
                    """
                        INSERT INTO discount_codes (code, discount_type, discount_value, min_order_value, active)
                        VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        ('WELCOME10', 'percent', 10, 0, 1),
                        ('GIAM20K', 'fixed', 20000, 100000, 1),
                        ('VIP50K', 'fixed', 50000, 300000, 1),
                    ],
                )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def _get_order_discount(cursor, order_id):
        OrderModel.ensure_discount_tables()
        cursor.execute(
            """
                SELECT id, order_id, discount_code_id, code, discount_type,
                       discount_value, discount_amount, created_at
                FROM order_discounts
                WHERE order_id = %s
                ORDER BY id DESC
                LIMIT 1
            """,
            (order_id,),
        )
        return cursor.fetchone()

    @staticmethod
    def validate_discount_code(code, subtotal):
        OrderModel.ensure_discount_tables()
        normalized_code = str(code or '').strip().upper()
        if not normalized_code:
            return None

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                    SELECT id, code, discount_type, discount_value, min_order_value, expires_at, active
                    FROM discount_codes
                    WHERE code = %s
                    LIMIT 1
                """,
                (normalized_code,),
            )
            discount = cursor.fetchone()
            if not discount or int(discount.get('active') or 0) != 1:
                return {'valid': False, 'message': 'Mã giảm giá không hợp lệ.'}

            expires_at = discount.get('expires_at')
            if expires_at and expires_at < datetime.now():
                return {'valid': False, 'message': 'Mã giảm giá đã hết hạn.'}

            subtotal = int(subtotal or 0)
            min_order_value = int(discount.get('min_order_value') or 0)
            if subtotal < min_order_value:
                return {
                    'valid': False,
                    'message': f"Đơn hàng cần tối thiểu {min_order_value:,}".replace(',', '.') + 'đ để dùng mã này.',
                }

            if discount.get('discount_type') == 'percent':
                discount_amount = int(subtotal * int(discount.get('discount_value') or 0) / 100)
            else:
                discount_amount = int(discount.get('discount_value') or 0)

            discount_amount = max(0, min(discount_amount, subtotal))
            return {
                'valid': True,
                'discount_code_id': discount.get('id'),
                'code': discount.get('code'),
                'discount_type': discount.get('discount_type'),
                'discount_value': int(discount.get('discount_value') or 0),
                'discount_amount': discount_amount,
                'message': 'Áp mã giảm giá thành công.',
            }
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_payment_config():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                    SELECT gateway, bank_code, account_no
                    FROM payment_transactions
                    WHERE gateway IS NOT NULL AND bank_code IS NOT NULL AND account_no IS NOT NULL
                    ORDER BY id DESC
                    LIMIT 1
                """
            )
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_all():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
                SELECT o.id, o.user_id, u.full_name AS user_name, u.email AS user_email,
                       o.total_amount, o.shipping_address, o.payment_method, o.payment_status,
                       o.status, o.created_at
                FROM orders o
                JOIN users u ON u.id = o.user_id
                ORDER BY o.id DESC
            """
        )
        orders = cursor.fetchall()

        for order in orders:
            cursor.execute(
                """
                    SELECT oi.id, oi.order_id, oi.product_id, p.name AS product_name,
                           oi.quantity, oi.price
                    FROM order_items oi
                    JOIN products p ON p.id = oi.product_id
                    WHERE oi.order_id = %s
                    ORDER BY oi.id ASC
                """,
                (order['id'],),
            )
            order['items'] = cursor.fetchall()
            order['payment_transaction'] = OrderModel._get_latest_payment_transaction(cursor, order['id'])
            order['discount'] = OrderModel._get_order_discount(cursor, order['id'])

        cursor.close()
        conn.close()
        return orders

    @staticmethod
    def get_by_user_id(user_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
                SELECT o.id, o.user_id, u.full_name AS user_name, u.email AS user_email,
                       o.total_amount, o.shipping_address, o.payment_method, o.payment_status,
                       o.status, o.created_at
                FROM orders o
                JOIN users u ON u.id = o.user_id
                WHERE o.user_id = %s
                ORDER BY o.id DESC
            """,
            (user_id,),
        )
        orders = cursor.fetchall()

        for order in orders:
            cursor.execute(
                """
                    SELECT oi.id, oi.order_id, oi.product_id, p.name AS product_name,
                           oi.quantity, oi.price
                    FROM order_items oi
                    JOIN products p ON p.id = oi.product_id
                    WHERE oi.order_id = %s
                    ORDER BY oi.id ASC
                """,
                (order['id'],),
            )
            order['items'] = cursor.fetchall()
            order['payment_transaction'] = OrderModel._get_latest_payment_transaction(cursor, order['id'])
            order['discount'] = OrderModel._get_order_discount(cursor, order['id'])

        cursor.close()
        conn.close()
        return orders

    @staticmethod
    def get_by_id(order_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
                SELECT o.id, o.user_id, u.full_name AS user_name, u.email AS user_email,
                       o.total_amount, o.shipping_address, o.payment_method, o.payment_status,
                       o.status, o.created_at
                FROM orders o
                JOIN users u ON u.id = o.user_id
                WHERE o.id = %s
            """,
            (order_id,),
        )
        order = cursor.fetchone()

        if order:
            cursor.execute(
                """
                    SELECT oi.id, oi.order_id, oi.product_id, p.name AS product_name,
                           oi.quantity, oi.price
                    FROM order_items oi
                    JOIN products p ON p.id = oi.product_id
                    WHERE oi.order_id = %s
                    ORDER BY oi.id ASC
                """,
                (order_id,),
            )
            order['items'] = cursor.fetchall()
            order['payment_transaction'] = OrderModel._get_latest_payment_transaction(cursor, order_id)
            order['discount'] = OrderModel._get_order_discount(cursor, order_id)

        cursor.close()
        conn.close()
        return order

    @staticmethod
    def _get_latest_payment_transaction(cursor, order_id):
        cursor.execute(
            """
                SELECT id, order_id, gateway, transaction_code, bank_code, account_no,
                       amount, transfer_content, raw_data, status, created_at, confirmed_at
                FROM payment_transactions
                WHERE order_id = %s
                ORDER BY id DESC
                LIMIT 1
            """,
            (order_id,),
        )
        return cursor.fetchone()

    @staticmethod
    def create(user_id, shipping_address, payment_method, status, items, discount_code=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            subtotal = sum(int(item['price']) * int(item['quantity']) for item in items)
            discount_data = None
            if discount_code:
                discount_data = OrderModel.validate_discount_code(discount_code, subtotal)
                if not discount_data or not discount_data.get('valid'):
                    raise ValueError((discount_data or {}).get('message') or 'Mã giảm giá không hợp lệ.')

            discount_amount = int((discount_data or {}).get('discount_amount') or 0)
            total_amount = max(0, subtotal - discount_amount)
            cursor.execute(
                """
                    INSERT INTO orders (user_id, total_amount, shipping_address, payment_method, status)
                    VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, total_amount, shipping_address, payment_method, status),
            )
            order_id = cursor.lastrowid

            for item in items:
                cursor.execute(
                    """
                        INSERT INTO order_items (order_id, product_id, quantity, price)
                        VALUES (%s, %s, %s, %s)
                    """,
                    (order_id, item['product_id'], item['quantity'], item['price']),
                )

            if discount_data and discount_amount > 0:
                OrderModel.ensure_discount_tables()
                cursor.execute(
                    """
                        INSERT INTO order_discounts (
                            order_id, discount_code_id, code, discount_type, discount_value, discount_amount
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        order_id,
                        discount_data.get('discount_code_id'),
                        discount_data.get('code'),
                        discount_data.get('discount_type'),
                        discount_data.get('discount_value'),
                        discount_amount,
                    ),
                )

            if payment_method == 'transfer':
                payment_defaults = OrderModel._get_payment_defaults()
                transfer_content = f"KCAFE-DH{order_id}"
                cursor.execute(
                    """
                        INSERT INTO payment_transactions (
                            order_id, gateway, bank_code, account_no, amount,
                            transfer_content, raw_data, status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        order_id,
                        payment_defaults['gateway'],
                        payment_defaults['bank_code'],
                        payment_defaults['account_no'],
                        total_amount,
                        transfer_content,
                        json.dumps({'order_id': order_id, 'transfer_content': transfer_content}),
                        'pending',
                    ),
                )

            conn.commit()
            return order_id
        except ValueError as error:
            conn.rollback()
            print('Loi khi tao don hang:', error)
            raise
        except Exception as e:
            conn.rollback()
            print('Loi khi tao don hang:', e)
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update(order_id, user_id, shipping_address, payment_method, status, items):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            total_amount = sum(int(item['price']) * int(item['quantity']) for item in items)
            cursor.execute(
                """
                    UPDATE orders
                    SET user_id = %s,
                        total_amount = %s,
                        shipping_address = %s,
                        payment_method = %s,
                        status = %s
                    WHERE id = %s
                """,
                (user_id, total_amount, shipping_address, payment_method, status, order_id),
            )

            cursor.execute("DELETE FROM order_items WHERE order_id = %s", (order_id,))
            for item in items:
                cursor.execute(
                    """
                        INSERT INTO order_items (order_id, product_id, quantity, price)
                        VALUES (%s, %s, %s, %s)
                    """,
                    (order_id, item['product_id'], item['quantity'], item['price']),
                )

            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print('Loi khi cap nhat don hang:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def delete(order_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM orders WHERE id = %s", (order_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            print('Loi khi xoa don hang:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_status(order_id, status):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE orders SET status = %s WHERE id = %s",
                (status, order_id),
            )
            conn.commit()
            if cursor.rowcount > 0:
                return True

            cursor.execute("SELECT status FROM orders WHERE id = %s", (order_id,))
            current = cursor.fetchone()
            return bool(current and current[0] == status)
        except Exception as e:
            conn.rollback()
            print('Loi khi cap nhat trang thai don hang:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_payment_status(order_id, payment_status):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE orders SET payment_status = %s WHERE id = %s",
                (payment_status, order_id),
            )
            conn.commit()
            if cursor.rowcount > 0:
                return True

            cursor.execute("SELECT payment_status FROM orders WHERE id = %s", (order_id,))
            current = cursor.fetchone()
            return bool(current and current[0] == payment_status)
        except Exception as e:
            conn.rollback()
            print('Loi khi cap nhat payment_status:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def mark_transaction_success(order_id, transaction_code):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    UPDATE payment_transactions
                    SET transaction_code = %s,
                        status = 'success',
                        confirmed_at = CURRENT_TIMESTAMP
                    WHERE order_id = %s
                      AND status = 'pending'
                    ORDER BY id DESC
                    LIMIT 1
                """,
                (transaction_code, order_id),
            )
            conn.commit()
            if cursor.rowcount > 0:
                return True

            cursor.execute(
                """
                    SELECT status, transaction_code
                    FROM payment_transactions
                    WHERE order_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                """,
                (order_id,),
            )
            current = cursor.fetchone()
            return bool(current and current[0] == 'success' and current[1] == transaction_code)
        except Exception as e:
            conn.rollback()
            print('Loi khi cap nhat giao dich thanh toan:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def mark_transaction_failed(order_id, raw_data=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    UPDATE payment_transactions
                    SET status = 'failed',
                        raw_data = %s
                    WHERE order_id = %s
                      AND status = 'pending'
                    ORDER BY id DESC
                    LIMIT 1
                """,
                (json.dumps(raw_data) if raw_data is not None else None, order_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            print('Loi khi cap nhat giao dich that bai:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def create_payment_transaction(order_id, amount, transfer_content):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            payment_defaults = OrderModel._get_payment_defaults()
            cursor.execute(
                """
                    INSERT INTO payment_transactions (
                        order_id, gateway, bank_code, account_no, amount,
                        transfer_content, raw_data, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    order_id,
                    payment_defaults['gateway'],
                    payment_defaults['bank_code'],
                    payment_defaults['account_no'],
                    amount,
                    transfer_content,
                    json.dumps({'order_id': order_id, 'transfer_content': transfer_content}),
                    'pending',
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            print('Loi khi tao payment transaction:', e)
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_order_by_transfer_content(transfer_content):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                    SELECT o.id
                    FROM orders o
                    JOIN payment_transactions pt ON pt.order_id = o.id
                    WHERE pt.transfer_content = %s
                    ORDER BY pt.id DESC
                    LIMIT 1
                """,
                (transfer_content,),
            )
            result = cursor.fetchone()
            return result['id'] if result else None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_transaction_raw_data(order_id, raw_data):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    UPDATE payment_transactions
                    SET raw_data = %s
                    WHERE order_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                """,
                (json.dumps(raw_data), order_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            print('Loi khi cap nhat raw_data giao dich:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def create_webhook_log(provider, event_type, payload, processed=False):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                    INSERT INTO payment_webhook_logs (provider, event_type, payload, processed)
                    VALUES (%s, %s, %s, %s)
                """,
                (provider, event_type, json.dumps(payload), 1 if processed else 0),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            print('Loi khi ghi webhook log:', e)
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_webhook_log_processed(log_id, processed=True):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE payment_webhook_logs SET processed = %s WHERE id = %s",
                (1 if processed else 0, log_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            print('Loi khi cap nhat webhook log:', e)
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_dashboard_stats():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT COUNT(*) AS total_orders FROM orders")
            total_orders = (cursor.fetchone() or {}).get('total_orders', 0)

            cursor.execute("SELECT COUNT(*) AS pending_orders FROM orders WHERE status = 'pending'")
            pending_orders = (cursor.fetchone() or {}).get('pending_orders', 0)

            cursor.execute("SELECT COUNT(*) AS processing_orders FROM orders WHERE status = 'processing'")
            processing_orders = (cursor.fetchone() or {}).get('processing_orders', 0)

            cursor.execute("SELECT COUNT(*) AS completed_orders FROM orders WHERE status = 'completed'")
            completed_orders = (cursor.fetchone() or {}).get('completed_orders', 0)

            cursor.execute("SELECT COUNT(*) AS paid_orders FROM orders WHERE payment_status = 'paid'")
            paid_orders = (cursor.fetchone() or {}).get('paid_orders', 0)

            cursor.execute(
                """
                    SELECT COALESCE(SUM(total_amount), 0) AS total_revenue
                    FROM orders
                    WHERE payment_status = 'paid'
                """
            )
            total_revenue = int((cursor.fetchone() or {}).get('total_revenue', 0) or 0)

            cursor.execute("SELECT COUNT(*) AS total_users FROM users")
            total_users = (cursor.fetchone() or {}).get('total_users', 0)

            cursor.execute("SELECT COUNT(*) AS total_customers FROM users WHERE role = 'customer'")
            total_customers = (cursor.fetchone() or {}).get('total_customers', 0)

            cursor.execute("SELECT COUNT(*) AS total_admins FROM users WHERE role = 'admin'")
            total_admins = (cursor.fetchone() or {}).get('total_admins', 0)

            cursor.execute("SELECT COUNT(*) AS total_products FROM products")
            total_products = (cursor.fetchone() or {}).get('total_products', 0)

            cursor.execute("SELECT COUNT(*) AS total_categories FROM categories")
            total_categories = (cursor.fetchone() or {}).get('total_categories', 0)

            cursor.execute(
                """
                    SELECT p.id, p.name,
                           COALESCE(SUM(oi.quantity), 0) AS sold_quantity,
                           COALESCE(SUM(oi.quantity * oi.price), 0) AS revenue
                    FROM products p
                    LEFT JOIN order_items oi ON oi.product_id = p.id
                    LEFT JOIN orders o ON o.id = oi.order_id
                    GROUP BY p.id, p.name
                    ORDER BY sold_quantity DESC, revenue DESC, p.id DESC
                    LIMIT 5
                """
            )
            top_products = cursor.fetchall()

            return {
                'total_orders': total_orders,
                'pending_orders': pending_orders,
                'processing_orders': processing_orders,
                'completed_orders': completed_orders,
                'paid_orders': paid_orders,
                'total_revenue': total_revenue,
                'total_users': total_users,
                'total_customers': total_customers,
                'total_admins': total_admins,
                'total_products': total_products,
                'total_categories': total_categories,
                'top_products': [
                    {
                        'id': item.get('id'),
                        'name': item.get('name'),
                        'sold_quantity': int(item.get('sold_quantity', 0) or 0),
                        'revenue': int(item.get('revenue', 0) or 0),
                    }
                    for item in top_products
                ],
            }
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def _get_period_range(period):
        now = datetime.now()
        if period == 'month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == 'year':
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start

    @staticmethod
    def get_revenue_report(period='day'):
        start = OrderModel._get_period_range(period)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                    SELECT COALESCE(SUM(total_amount), 0) AS total_revenue_all
                    FROM orders
                    WHERE payment_status = 'paid'
                """
            )
            total_revenue_all = int((cursor.fetchone() or {}).get('total_revenue_all', 0) or 0)

            cursor.execute(
                """
                    SELECT COUNT(*) AS total_orders,
                           COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN total_amount ELSE 0 END), 0) AS total_revenue,
                           COALESCE(SUM(CASE WHEN total_amount >= 100000 THEN 1 ELSE 0 END), 0) AS orders_over_100k,
                           COALESCE(SUM(CASE WHEN total_amount >= 200000 THEN 1 ELSE 0 END), 0) AS orders_over_200k,
                           COALESCE(SUM(CASE WHEN total_amount >= 1000000 THEN 1 ELSE 0 END), 0) AS orders_over_1m
                    FROM orders
                    WHERE created_at >= %s
                """,
                (start,),
            )
            summary = cursor.fetchone() or {}

            cursor.execute(
                """
                    SELECT c.name AS label, COALESCE(SUM(oi.quantity * oi.price), 0) AS value
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    JOIN products p ON p.id = oi.product_id
                    JOIN categories c ON c.id = p.category_id
                    WHERE o.payment_status = 'paid' AND o.created_at >= %s
                    GROUP BY c.id, c.name
                    ORDER BY value DESC
                """,
                (start,),
            )
            category_revenue = cursor.fetchall()

            cursor.execute(
                """
                    SELECT p.name AS label, COALESCE(SUM(oi.quantity * oi.price), 0) AS value
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    JOIN products p ON p.id = oi.product_id
                    WHERE o.payment_status = 'paid' AND o.created_at >= %s
                    GROUP BY p.id, p.name
                    ORDER BY value DESC
                    LIMIT 6
                """,
                (start,),
            )
            product_revenue = cursor.fetchall()

            cursor.execute(
                """
                    SELECT 
                        SUM(CASE WHEN created_at >= %s THEN 1 ELSE 0 END) AS new_customers,
                        SUM(CASE WHEN created_at < %s THEN 1 ELSE 0 END) AS existing_customers
                    FROM users
                    WHERE role = 'customer'
                """,
                (start, start),
            )
            customer_split = cursor.fetchone() or {}

            cursor.execute(
                """
                    SELECT p.id, p.name,
                           COALESCE(SUM(oi.quantity), 0) AS sold_quantity,
                           COALESCE(SUM(oi.quantity * oi.price), 0) AS revenue
                    FROM products p
                    LEFT JOIN order_items oi ON oi.product_id = p.id
                    LEFT JOIN orders o ON o.id = oi.order_id
                    WHERE o.created_at >= %s OR o.created_at IS NULL
                    GROUP BY p.id, p.name
                    ORDER BY sold_quantity DESC, revenue DESC, p.id DESC
                    LIMIT 5
                """,
                (start,),
            )
            top_products = cursor.fetchall()

            return {
                'period': period,
                'summary': {
                    'total_orders': int(summary.get('total_orders', 0) or 0),
                    'total_revenue': int(summary.get('total_revenue', 0) or 0),
                    'total_revenue_all': total_revenue_all,
                    'orders_over_100k': int(summary.get('orders_over_100k', 0) or 0),
                    'orders_over_200k': int(summary.get('orders_over_200k', 0) or 0),
                    'orders_over_1m': int(summary.get('orders_over_1m', 0) or 0),
                },
                'category_revenue': [
                    {'label': item.get('label'), 'value': int(item.get('value', 0) or 0)}
                    for item in category_revenue
                ],
                'product_revenue': [
                    {'label': item.get('label'), 'value': int(item.get('value', 0) or 0)}
                    for item in product_revenue
                ],
                'customer_split': [
                    {'label': 'Khách mới', 'value': int(customer_split.get('new_customers', 0) or 0)},
                    {'label': 'Khách cũ', 'value': int(customer_split.get('existing_customers', 0) or 0)},
                ],
                'order_ranges': [
                    {'label': 'Từ 100k', 'value': int(summary.get('orders_over_100k', 0) or 0)},
                    {'label': 'Từ 200k', 'value': int(summary.get('orders_over_200k', 0) or 0)},
                    {'label': 'Từ 1 triệu', 'value': int(summary.get('orders_over_1m', 0) or 0)},
                ],
                'top_products': [
                    {
                        'id': item.get('id'),
                        'name': item.get('name'),
                        'sold_quantity': int(item.get('sold_quantity', 0) or 0),
                        'revenue': int(item.get('revenue', 0) or 0),
                    }
                    for item in top_products
                ],
            }
        finally:
            cursor.close()
            conn.close()
