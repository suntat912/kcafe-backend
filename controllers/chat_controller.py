from flask import Blueprint, jsonify, request

from models.order_model import OrderModel
from models.product_model import CategoryModel, ProductModel

chat_bp = Blueprint('chat_bp', __name__)


def _normalize(text):
    return str(text or '').strip().lower()


def _format_currency(value):
    try:
        return f"{int(value or 0):,}".replace(',', '.') + 'đ'
    except (TypeError, ValueError):
        return '0đ'


def _get_all_products():
    return ProductModel.get_all()


def _get_available_products():
    return [
        product for product in _get_all_products()
        if product.get('status') == 'active' and int(product.get('stock', 0) or 0) > 0
    ]


def _get_top_products():
    stats = OrderModel.get_dashboard_stats() or {}
    top_products = stats.get('top_products', [])
    all_products = _get_all_products()
    mapped = []

    for top_product in top_products:
        matched = next(
            (item for item in all_products if int(item.get('id', 0) or 0) == int(top_product.get('id', 0) or 0)),
            None,
        )
        if matched:
            mapped.append(matched)

    return mapped or all_products[:5]


def _build_product_match(message):
    normalized_message = _normalize(message)
    products = _get_all_products()
    categories = CategoryModel.get_all()

    matched_product = next(
        (
            product for product in products
            if _normalize(product.get('name')) in normalized_message
            or normalized_message in _normalize(product.get('name'))
        ),
        None,
    )
    if matched_product:
        availability = (
            'còn hàng'
            if matched_product.get('status') == 'active' and int(matched_product.get('stock', 0) or 0) > 0
            else 'tạm hết hàng'
        )
        return {
            'reply': (
                f"{matched_product.get('name')} hiện có giá {_format_currency(matched_product.get('price'))}. "
                f"Danh mục: {matched_product.get('category_name')}. "
                f"Tình trạng: {availability}. "
                f"{matched_product.get('description') or ''}".strip()
            ),
            'suggestions': ['Món bán chạy', 'Gợi ý theo khẩu vị của tôi', 'Xem đồ uống'],
        }

    matched_category = next(
        (
            category for category in categories
            if _normalize(category.get('name')) in normalized_message
            or normalized_message in _normalize(category.get('name'))
        ),
        None,
    )
    if matched_category:
        category_products = [
            product for product in products if int(product.get('category_id', 0) or 0) == int(matched_category.get('id', 0) or 0)
        ][:5]
        if category_products:
            product_text = ', '.join(
                f"{product.get('name')} ({_format_currency(product.get('price'))})"
                for product in category_products
            )
            return {
                'reply': f"Danh mục {matched_category.get('name')} hiện có: {product_text}.",
                'suggestions': ['Món bán chạy', 'Gợi ý theo khẩu vị của tôi', 'Thanh toán thế nào'],
            }

    return None


def _analyze_customer_preferences(user_id):
    if not user_id:
        return None

    orders = OrderModel.get_by_user_id(user_id)
    if not orders:
        return None

    products = _get_all_products()
    categories = CategoryModel.get_all()
    product_map = {int(product.get('id', 0) or 0): product for product in products}
    category_map = {int(category.get('id', 0) or 0): category for category in categories}

    category_counter = {}
    product_counter = {}
    purchased_product_ids = set()
    total_spent = 0
    total_items = 0
    valid_orders = 0

    for order in orders:
        if order.get('status') == 'cancelled':
            continue

        valid_orders += 1
        total_spent += int(order.get('total_amount', 0) or 0)

        for item in order.get('items', []):
            product_id = int(item.get('product_id', 0) or 0)
            quantity = int(item.get('quantity', 0) or 0)
            if product_id <= 0 or quantity <= 0:
                continue

            total_items += quantity
            purchased_product_ids.add(product_id)
            product_counter[product_id] = product_counter.get(product_id, 0) + quantity

            product = product_map.get(product_id)
            if not product:
                continue

            category_id = int(product.get('category_id', 0) or 0)
            category_counter[category_id] = category_counter.get(category_id, 0) + quantity

    if not product_counter:
        return None

    favorite_product_id = max(product_counter, key=product_counter.get)
    favorite_product = product_map.get(favorite_product_id)

    favorite_category = None
    if category_counter:
        favorite_category_id = max(category_counter, key=category_counter.get)
        favorite_category = category_map.get(favorite_category_id)

    available_products = _get_available_products()
    recommended_products = []

    if favorite_category:
        same_category_products = [
            product for product in available_products
            if int(product.get('category_id', 0) or 0) == int(favorite_category.get('id', 0) or 0)
            and int(product.get('id', 0) or 0) not in purchased_product_ids
        ]
        recommended_products.extend(same_category_products[:3])

    for product in _get_top_products():
        product_id = int(product.get('id', 0) or 0)
        if product_id in purchased_product_ids:
            continue
        if any(int(existing.get('id', 0) or 0) == product_id for existing in recommended_products):
            continue
        recommended_products.append(product)
        if len(recommended_products) >= 5:
            break

    return {
        'orders_count': valid_orders,
        'total_spent': total_spent,
        'total_items': total_items,
        'favorite_product': favorite_product,
        'favorite_category': favorite_category,
        'recommended_products': recommended_products[:5],
    }


def _build_personal_recommendations(user_id):
    profile = _analyze_customer_preferences(user_id)
    if not profile:
        top_products = _get_top_products()
        if not top_products:
            return {
                'reply': 'Mình chưa có đủ dữ liệu để gợi ý cá nhân hóa. Bạn có thể xem thêm danh sách đồ uống hiện có.',
                'suggestions': ['Xem đồ uống', 'Món bán chạy', 'Có giao hàng không'],
            }

        top_text = ', '.join(
            f"{product.get('name')} ({_format_currency(product.get('price'))})"
            for product in top_products[:5]
        )
        return {
            'reply': f"Mình chưa có lịch sử mua hàng của bạn nên tạm gợi ý các món bán chạy: {top_text}.",
            'suggestions': ['Món bán chạy', 'Xem đồ uống', 'Đơn hàng của tôi'],
        }

    favorite_product = profile.get('favorite_product') or {}
    favorite_category = profile.get('favorite_category') or {}
    recommended_products = profile.get('recommended_products') or []

    if not recommended_products:
        return {
            'reply': (
                f"Dựa trên lịch sử mua hàng, bạn thường chọn {str(favorite_category.get('name') or 'nhóm món quen thuộc').lower()} "
                f"và hay mua {favorite_product.get('name') or 'một số món quen thuộc'}. "
                "Hiện mình chưa tìm thấy món mới phù hợp hơn trong kho, bạn có thể xem lại menu để chọn thêm."
            ),
            'suggestions': ['Xem đồ uống', 'Món bán chạy', 'Đơn hàng của tôi'],
        }

    recommendation_text = ', '.join(
        f"{product.get('name')} ({_format_currency(product.get('price'))})"
        for product in recommended_products
    )

    return {
        'reply': (
            f"Dựa trên {profile.get('orders_count')} đơn trước đó, bạn thường chọn "
            f"{str(favorite_category.get('name') or 'nhóm món này').lower()} "
            f"và món mua nhiều nhất là {favorite_product.get('name') or 'món quen thuộc'}. "
            f"Mình gợi ý thêm cho bạn: {recommendation_text}."
        ),
        'suggestions': ['Món bán chạy', 'Xem đồ uống', 'Đơn hàng của tôi'],
    }


def _build_order_reply(user_id):
    if not user_id:
        return {
            'reply': 'Bạn hãy đăng nhập để mình kiểm tra lịch sử đơn hàng và trạng thái đơn gần nhất cho bạn.',
            'suggestions': ['Đăng nhập', 'Món bán chạy', 'Liên hệ cửa hàng'],
        }

    orders = OrderModel.get_by_user_id(user_id)
    if not orders:
        return {
            'reply': 'Hiện bạn chưa có đơn hàng nào. Bạn có thể xem đồ uống hoặc các món bán chạy để bắt đầu đặt món.',
            'suggestions': ['Xem đồ uống', 'Món bán chạy', 'Cách đặt hàng'],
        }

    latest_orders = orders[:3]
    order_lines = []
    for order in latest_orders:
        order_lines.append(
            f"Đơn #{order.get('id')}: {order.get('status')} - {order.get('payment_status') or 'chưa thanh toán'} - {_format_currency(order.get('total_amount'))}"
        )

    extra_line = ''
    recommendation_profile = _analyze_customer_preferences(user_id)
    if recommendation_profile and recommendation_profile.get('recommended_products'):
        first_recommendation = recommendation_profile['recommended_products'][0]
        extra_line = (
            f"\nGợi ý cho bạn: thử {first_recommendation.get('name')} "
            f"({_format_currency(first_recommendation.get('price'))}) vì bạn hay chọn "
            f"{str((recommendation_profile.get('favorite_category') or {}).get('name') or 'nhóm món này').lower()}."
        )

    return {
        'reply': 'Đây là các đơn gần nhất của bạn:\n' + '\n'.join(order_lines) + extra_line,
        'suggestions': ['Gợi ý theo khẩu vị của tôi', 'Món bán chạy', 'Thanh toán thế nào'],
    }


@chat_bp.route('/api/chatbot/message', methods=['POST'])
def chatbot_message():
    data = request.get_json(silent=True) or {}
    message = str(data.get('message', '')).strip()
    user_id = data.get('userId')

    try:
        user_id = int(user_id) if user_id not in (None, '') else None
    except (TypeError, ValueError):
        user_id = None

    if not message:
        return jsonify({
            'reply': 'Bạn hãy nhập câu hỏi để mình hỗ trợ về đồ uống, thanh toán, giao hàng hoặc đơn hàng.',
            'suggestions': ['Món bán chạy', 'Gợi ý theo khẩu vị của tôi', 'Thanh toán thế nào'],
        }), 200

    normalized_message = _normalize(message)

    if any(keyword in normalized_message for keyword in ['xin chào', 'chào', 'hello', 'hi']):
        return jsonify({
            'reply': 'Xin chào, mình có thể hỗ trợ về đồ uống, món bán chạy, gợi ý cá nhân hóa, thanh toán, giao hàng và đơn hàng của bạn.',
            'suggestions': ['Món bán chạy', 'Gợi ý theo khẩu vị của tôi', 'Xem đồ uống'],
        }), 200

    if any(keyword in normalized_message for keyword in ['khẩu vị', 'gợi ý theo lịch sử', 'gợi ý cho tôi', 'đề xuất cho tôi', 'món nào hợp với tôi']):
        return jsonify(_build_personal_recommendations(user_id)), 200

    if any(keyword in normalized_message for keyword in ['món bán chạy', 'bán chạy', 'best seller', 'gợi ý', 'nên uống gì']):
        top_products = _get_top_products()
        if top_products:
            top_text = ', '.join(
                f"{product.get('name')} ({_format_currency(product.get('price'))})"
                for product in top_products[:5]
            )
            return jsonify({
                'reply': f"Các món bán chạy hiện tại là: {top_text}.",
                'suggestions': ['Gợi ý theo khẩu vị của tôi', 'Xem đồ uống', 'Có giao hàng không'],
            }), 200

    if any(keyword in normalized_message for keyword in ['đơn hàng', 'trạng thái đơn', 'lịch sử đơn', 'đơn của tôi']):
        return jsonify(_build_order_reply(user_id)), 200

    if any(keyword in normalized_message for keyword in ['thanh toán', 'chuyển khoản', 'qr', 'tiền mặt']):
        return jsonify({
            'reply': 'Quán hỗ trợ thanh toán bằng tiền mặt và chuyển khoản QR. Nếu chọn chuyển khoản, hệ thống sẽ tạo mã QR theo đúng số tiền đơn hàng để bạn thanh toán.',
            'suggestions': ['Có giao hàng không', 'Đơn hàng của tôi', 'Món bán chạy'],
        }), 200

    if any(keyword in normalized_message for keyword in ['giao hàng', 'ship', 'vận chuyển']):
        return jsonify({
            'reply': 'Quán có hỗ trợ giao hàng. Bạn chỉ cần chọn món, vào giỏ hàng, nhập địa chỉ giao hàng rồi xác nhận thanh toán để tạo đơn.',
            'suggestions': ['Thanh toán thế nào', 'Xem đồ uống', 'Liên hệ cửa hàng'],
        }), 200

    if any(keyword in normalized_message for keyword in ['giờ mở cửa', 'mấy giờ mở cửa', 'mở cửa', 'đóng cửa']):
        return jsonify({
            'reply': 'Hiện cửa hàng mở cửa mỗi ngày từ 07:00 đến 22:00.',
            'suggestions': ['Liên hệ cửa hàng', 'Món bán chạy', 'Xem đồ uống'],
        }), 200

    if any(keyword in normalized_message for keyword in ['facebook', 'email', 'số điện thoại', 'liên hệ', 'dịch vụ']):
        return jsonify({
            'reply': 'Bạn có thể liên hệ cửa hàng qua email support@kcafe.vn, Facebook facebook.com/kcafe hoặc số điện thoại 1900 1234.',
            'suggestions': ['Có giao hàng không', 'Thanh toán thế nào', 'Món bán chạy'],
        }), 200

    product_reply = _build_product_match(message)
    if product_reply:
        return jsonify(product_reply), 200

    return jsonify({
        'reply': 'Mình có thể hỗ trợ về đồ uống, món bán chạy, gợi ý theo khẩu vị, thanh toán, giao hàng, liên hệ cửa hàng hoặc đơn hàng của bạn.',
        'suggestions': ['Món bán chạy', 'Gợi ý theo khẩu vị của tôi', 'Đơn hàng của tôi'],
    }), 200
