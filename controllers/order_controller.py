from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request

from models.order_model import OrderModel
from models.product_model import ProductModel
from models.user_model import UserModel

order_bp = Blueprint('order_bp', __name__)


def _serialize_datetime(value):
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return value


def _serialize_item(item):
    return {
        'id': item.get('id'),
        'order_id': item.get('order_id'),
        'product_id': item.get('product_id'),
        'product_name': item.get('product_name'),
        'quantity': int(item.get('quantity', 0) or 0),
        'price': int(item.get('price', 0) or 0),
    }


def _serialize_order(order):
    payment_transaction = order.get('payment_transaction') or {}
    discount = order.get('discount') or {}
    return {
        'id': order['id'],
        'user_id': order['user_id'],
        'user_name': order.get('user_name'),
        'user_email': order.get('user_email'),
        'total_amount': int(order.get('total_amount', 0) or 0),
        'shipping_address': order.get('shipping_address'),
        'payment_method': order.get('payment_method'),
        'payment_status': order.get('payment_status'),
        'status': order.get('status'),
        'created_at': _serialize_datetime(order.get('created_at')),
        'discount': {
            'id': discount.get('id'),
            'code': discount.get('code'),
            'discount_type': discount.get('discount_type'),
            'discount_value': int(discount.get('discount_value', 0) or 0),
            'discount_amount': int(discount.get('discount_amount', 0) or 0),
        }
        if discount
        else None,
        'payment_transaction': {
            'id': payment_transaction.get('id'),
            'gateway': payment_transaction.get('gateway'),
            'transaction_code': payment_transaction.get('transaction_code'),
            'bank_code': payment_transaction.get('bank_code'),
            'account_no': payment_transaction.get('account_no'),
            'amount': int(payment_transaction.get('amount', 0) or 0),
            'transfer_content': payment_transaction.get('transfer_content'),
            'status': payment_transaction.get('status'),
            'created_at': _serialize_datetime(payment_transaction.get('created_at')),
            'confirmed_at': _serialize_datetime(payment_transaction.get('confirmed_at')),
        }
        if payment_transaction
        else None,
        'items': [_serialize_item(item) for item in order.get('items', [])],
    }


def _normalize_items(items):
    normalized = []
    for item in items:
        try:
            product_id = int(item.get('productId'))
            quantity = int(item.get('quantity', 0))
            price = int(item.get('price', 0))
        except (TypeError, ValueError):
            return None

        if quantity <= 0 or price < 0:
            return None

        product = ProductModel.get_by_id(product_id)
        if not product:
            return None

        normalized.append({
            'product_id': product_id,
            'quantity': quantity,
            'price': price,
        })

    return normalized if normalized else None


def _extract_first_value(payload, keys):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in keys and value not in (None, ''):
                return value
            found = _extract_first_value(value, keys)
            if found not in (None, ''):
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_first_value(item, keys)
            if found not in (None, ''):
                return found
    return None


def _extract_payment_payload(payload):
    amount = _extract_first_value(payload, {'amount', 'transferamount', 'value'})
    transfer_content = _extract_first_value(
        payload,
        {'transfercontent', 'description', 'content', 'addinfo', 'message', 'remark'},
    )
    transaction_code = _extract_first_value(
        payload,
        {'transactioncode', 'transactionid', 'txid', 'reference', 'referencenumber'},
    )
    event_type = _extract_first_value(payload, {'event', 'eventtype', 'type'}) or 'payment_callback'

    try:
        normalized_amount = int(float(str(amount).replace(',', '').strip())) if amount is not None else None
    except (TypeError, ValueError):
        normalized_amount = None

    return {
        'amount': normalized_amount,
        'transfer_content': str(transfer_content).strip() if transfer_content not in (None, '') else None,
        'transaction_code': str(transaction_code).strip() if transaction_code not in (None, '') else None,
        'event_type': str(event_type),
    }


def _get_payment_config():
    stored_config = OrderModel.get_payment_config() or {}
    return {
        'provider': current_app.config.get('PAYMENT_PROVIDER', 'vietqr'),
        'gateway': stored_config.get('gateway') or current_app.config.get('PAYMENT_PROVIDER', 'vietqr'),
        'bank_code': stored_config.get('bank_code') or current_app.config.get('PAYMENT_BANK_CODE'),
        'account_no': stored_config.get('account_no') or current_app.config.get('PAYMENT_ACCOUNT_NO'),
        'account_name': current_app.config.get('PAYMENT_ACCOUNT_NAME'),
    }


def _get_order_id_from_transfer_content(transfer_content):
    if not transfer_content:
        return None

    order_id = OrderModel.get_order_by_transfer_content(transfer_content)
    if order_id:
        return order_id

    normalized = str(transfer_content).strip().upper()
    if normalized.startswith('KCAFE-DH'):
        raw_order_id = normalized.replace('KCAFE-DH', '', 1)
        if raw_order_id.isdigit():
            return int(raw_order_id)

    return None


@order_bp.route('/api/payment-config', methods=['GET'])
def get_payment_config():
    return jsonify({'payment': _get_payment_config()}), 200


@order_bp.route('/api/orders', methods=['GET'])
def get_orders():
    user_id = request.args.get('user_id')
    if user_id not in (None, ''):
        try:
            normalized_user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({'message': 'Người dùng không hợp lệ!'}), 400
        orders = OrderModel.get_by_user_id(normalized_user_id)
        return jsonify({'orders': [_serialize_order(item) for item in orders]}), 200

    orders = OrderModel.get_all()
    return jsonify({'orders': [_serialize_order(item) for item in orders]}), 200


@order_bp.route('/api/admin/dashboard', methods=['GET'])
def get_admin_dashboard():
    stats = OrderModel.get_dashboard_stats()
    return jsonify({'stats': stats}), 200


@order_bp.route('/api/admin/revenue-report', methods=['GET'])
def get_revenue_report():
    period = str(request.args.get('period', 'day')).strip().lower()
    if period not in {'day', 'month', 'year'}:
        period = 'day'

    report = OrderModel.get_revenue_report(period)
    return jsonify({'report': report}), 200


@order_bp.route('/api/discount-codes/validate', methods=['POST'])
def validate_discount_code():
    data = request.json or {}
    code = str(data.get('code', '')).strip().upper()
    subtotal = data.get('subtotal', 0)

    try:
        subtotal = int(subtotal)
    except (TypeError, ValueError):
        subtotal = 0

    result = OrderModel.validate_discount_code(code, subtotal)
    if not result or not result.get('valid'):
        return jsonify({'message': (result or {}).get('message') or 'Mã giảm giá không hợp lệ.'}), 400

    return jsonify({
        'message': result.get('message'),
        'discount': {
            'code': result.get('code'),
            'discount_type': result.get('discount_type'),
            'discount_value': int(result.get('discount_value', 0) or 0),
            'discount_amount': int(result.get('discount_amount', 0) or 0),
        },
    }), 200


@order_bp.route('/api/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    order = OrderModel.get_by_id(order_id)
    if not order:
        return jsonify({'message': 'Không tìm thấy đơn hàng!'}), 404

    return jsonify({'order': _serialize_order(order)}), 200


@order_bp.route('/api/orders', methods=['POST'])
def create_order():
    data = request.json or {}
    user_id = data.get('userId')
    shipping_address = str(data.get('shippingAddress', '')).strip()
    payment_method = str(data.get('paymentMethod', 'cash')).strip().lower()
    status = str(data.get('status', 'pending')).strip().lower()
    discount_code = str(data.get('discountCode', '')).strip().upper()
    items = _normalize_items(data.get('items', []))

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'message': 'Người đặt không hợp lệ!'}), 400

    if not UserModel.get_user_by_id(user_id):
        return jsonify({'message': 'Người dùng không tồn tại!'}), 400

    if not shipping_address or payment_method not in {'cash', 'transfer'} or status not in {'pending', 'processing', 'completed', 'cancelled'}:
        return jsonify({'message': 'Thông tin đơn hàng không hợp lệ!'}), 400

    if not items:
        return jsonify({'message': 'Đơn hàng phải có ít nhất một sản phẩm!'}), 400

    try:
        order_id = OrderModel.create(
            user_id,
            shipping_address,
            payment_method,
            status,
            items,
            discount_code=discount_code,
        )
    except ValueError as error:
        return jsonify({'message': str(error)}), 400

    if not order_id:
        return jsonify({'message': 'Tạo đơn hàng thất bại!'}), 500

    order = OrderModel.get_by_id(order_id)
    return jsonify({'message': 'Tạo đơn hàng thành công!', 'order': _serialize_order(order)}), 201


@order_bp.route('/api/orders/<int:order_id>', methods=['PUT'])
def update_order(order_id):
    current_order = OrderModel.get_by_id(order_id)
    if not current_order:
        return jsonify({'message': 'Không tìm thấy đơn hàng!'}), 404

    data = request.json or {}
    user_id = data.get('userId', current_order.get('user_id'))
    shipping_address = str(data.get('shippingAddress', current_order.get('shipping_address', ''))).strip()
    payment_method = str(data.get('paymentMethod', current_order.get('payment_method', 'cash'))).strip().lower()
    status = str(data.get('status', current_order.get('status', 'pending'))).strip().lower()
    items = _normalize_items(data.get('items', []))

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'message': 'Người đặt không hợp lệ!'}), 400

    if not UserModel.get_user_by_id(user_id):
        return jsonify({'message': 'Người dùng không tồn tại!'}), 400

    if not shipping_address or payment_method not in {'cash', 'transfer'} or status not in {'pending', 'processing', 'completed', 'cancelled'}:
        return jsonify({'message': 'Thông tin đơn hàng không hợp lệ!'}), 400

    if not items:
        return jsonify({'message': 'Đơn hàng phải có ít nhất một sản phẩm!'}), 400

    success = OrderModel.update(order_id, user_id, shipping_address, payment_method, status, items)
    if not success:
        return jsonify({'message': 'Cập nhật đơn hàng thất bại!'}), 500

    order = OrderModel.get_by_id(order_id)
    return jsonify({'message': 'Cập nhật đơn hàng thành công!', 'order': _serialize_order(order)}), 200


@order_bp.route('/api/orders/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    order = OrderModel.get_by_id(order_id)
    if not order:
        return jsonify({'message': 'Không tìm thấy đơn hàng!'}), 404

    success = OrderModel.delete(order_id)
    if not success:
        return jsonify({'message': 'Xóa đơn hàng thất bại!'}), 500

    return jsonify({'message': 'Xóa đơn hàng thành công!'}), 200


@order_bp.route('/api/orders/<int:order_id>/confirm-transfer', methods=['PUT'])
def confirm_transfer(order_id):
    if not current_app.config.get('ENABLE_MANUAL_PAYMENT_CONFIRM', False):
        return jsonify({'message': 'Xác nhận thủ công đã bị tắt. Đơn hàng chỉ được cập nhật khi có callback thanh toán.'}), 403

    order = OrderModel.get_by_id(order_id)
    if not order:
        return jsonify({'message': 'Không tìm thấy đơn hàng!'}), 404

    if order.get('payment_method') != 'transfer':
        return jsonify({'message': 'Đơn hàng này không dùng chuyển khoản!'}), 400

    if order.get('status') in {'completed', 'cancelled'}:
        return jsonify({'message': 'Đơn hàng không thể xác nhận thanh toán thêm!'}), 400

    if order.get('payment_status') == 'paid':
        return jsonify({'message': 'Đơn hàng này đã được thanh toán trước đó!'}), 400

    payment_transaction = order.get('payment_transaction')
    if not payment_transaction:
        transfer_content = f"KCAFE-DH{order_id}"
        created_tx = OrderModel.create_payment_transaction(
            order_id,
            int(order.get('total_amount', 0) or 0),
            transfer_content,
        )
        if not created_tx:
            return jsonify({'message': 'Không thể khởi tạo giao dịch thanh toán!'}), 500

    transaction_code = f"DEMO-TX-{order_id}"

    success_status = OrderModel.update_status(order_id, 'processing')
    success_payment = OrderModel.update_payment_status(order_id, 'paid')
    success_tx = OrderModel.mark_transaction_success(order_id, transaction_code)

    if not success_status or not success_payment or not success_tx:
        return jsonify({'message': 'Xác nhận thanh toán thất bại!'}), 500

    updated_order = OrderModel.get_by_id(order_id)
    return jsonify({
        'message': 'Thanh toán thành công! Đơn hàng đã chuyển sang trạng thái đang xử lý giao hàng.',
        'order': _serialize_order(updated_order),
    }), 200


@order_bp.route('/api/payments/vietqr/webhook', methods=['POST'])
def vietqr_webhook():
    payload = request.get_json(silent=True) or {}
    payment_data = _extract_payment_payload(payload)
    log_id = OrderModel.create_webhook_log('vietqr', payment_data['event_type'], payload, processed=False)

    transfer_content = payment_data['transfer_content']
    amount = payment_data['amount']
    transaction_code = payment_data['transaction_code'] or f"VQR-{int(datetime.now().timestamp())}"

    if not transfer_content:
        return jsonify({'message': 'Thiếu nội dung chuyển khoản để đối soát.'}), 400

    order_id = _get_order_id_from_transfer_content(transfer_content)
    if not order_id:
        return jsonify({'message': 'Không tìm thấy đơn hàng khớp nội dung chuyển khoản.'}), 404

    order = OrderModel.get_by_id(order_id)
    if not order:
        return jsonify({'message': 'Không tìm thấy đơn hàng.'}), 404

    if order.get('status') == 'cancelled':
        return jsonify({'message': 'Đơn hàng đã hủy, không thể xác nhận thanh toán.'}), 400

    if not order.get('payment_transaction'):
        OrderModel.create_payment_transaction(
            order_id,
            int(order.get('total_amount', 0) or 0),
            transfer_content,
        )
        order = OrderModel.get_by_id(order_id)

    OrderModel.update_transaction_raw_data(order_id, payload)

    if order.get('payment_status') == 'paid':
        if log_id:
            OrderModel.update_webhook_log_processed(log_id, True)
        return jsonify({'message': 'Đơn hàng đã được xác nhận trước đó.', 'order': _serialize_order(order)}), 200

    if amount is None or int(order.get('total_amount', 0) or 0) != amount:
        OrderModel.mark_transaction_failed(order_id, payload)
        return jsonify({'message': 'Số tiền giao dịch không khớp với đơn hàng.'}), 400

    next_status = order.get('status') if order.get('status') in {'processing', 'completed'} else 'processing'
    success_status = OrderModel.update_status(order_id, next_status)
    success_payment = OrderModel.update_payment_status(order_id, 'paid')
    success_tx = OrderModel.mark_transaction_success(order_id, transaction_code)

    if not success_status or not success_payment or not success_tx:
        return jsonify({'message': 'Không thể cập nhật trạng thái thanh toán.'}), 500

    updated_order = OrderModel.get_by_id(order_id)
    if log_id:
        OrderModel.update_webhook_log_processed(log_id, True)

    return jsonify({
        'message': 'Đã tự động xác nhận thanh toán thành công.',
        'order': _serialize_order(updated_order),
    }), 200
