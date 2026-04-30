import os
import uuid

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from models.product_model import CategoryModel, ProductModel
from werkzeug.utils import secure_filename

product_bp = Blueprint('product_bp', __name__)

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _serialize_category(category):
    return {
        'id': category['id'],
        'name': category['name'],
        'description': category.get('description'),
        'created_at': category.get('created_at'),
        'product_count': int(category.get('product_count', 0) or 0),
    }


def _serialize_product(product):
    return {
        'id': product['id'],
        'category_id': product['category_id'],
        'category_name': product.get('category_name'),
        'name': product['name'],
        'description': product.get('description'),
        'price': int(product.get('price', 0) or 0),
        'stock': int(product.get('stock', 0) or 0),
        'image_url': product.get('image_url'),
        'status': product.get('status'),
        'created_at': product.get('created_at'),
    }


@product_bp.route('/api/products/upload-image', methods=['POST'])
def upload_product_image():
    if 'image' not in request.files:
        return jsonify({'message': 'Chưa có tệp ảnh!'}), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'message': 'Bạn chưa chọn ảnh!'}), 400

    if not _allowed_image(file.filename):
        return jsonify({'message': 'Định dạng ảnh không hợp lệ!'}), 400

    extension = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    filename = f"product_{uuid.uuid4().hex}.{extension}"
    upload_folder = current_app.config['PRODUCT_UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    file.save(os.path.join(upload_folder, filename))

    return jsonify({'message': 'Tải ảnh thành công!', 'image_url': filename}), 200


@product_bp.route('/uploads/products/<path:filename>', methods=['GET'])
def get_product_image(filename):
    return send_from_directory(current_app.config['PRODUCT_UPLOAD_FOLDER'], filename)


@product_bp.route('/api/categories', methods=['GET'])
def get_categories():
    categories = CategoryModel.get_all()
    return jsonify({'categories': [_serialize_category(item) for item in categories]}), 200


@product_bp.route('/api/categories', methods=['POST'])
def create_category():
    data = request.json or {}
    name = str(data.get('name', '')).strip()
    description = str(data.get('description', '')).strip()

    if not name:
        return jsonify({'message': 'Tên danh mục là bắt buộc!'}), 400

    category_id = CategoryModel.create(name, description)
    if not category_id:
        return jsonify({'message': 'Tạo danh mục thất bại!'}), 500

    category = CategoryModel.get_by_id(category_id)
    return jsonify({'message': 'Tạo danh mục thành công!', 'category': _serialize_category(category)}), 201


@product_bp.route('/api/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    category = CategoryModel.get_by_id(category_id)
    if not category:
        return jsonify({'message': 'Không tìm thấy danh mục!'}), 404

    data = request.json or {}
    name = str(data.get('name', category.get('name', ''))).strip()
    description = str(data.get('description', category.get('description') or '')).strip()

    if not name:
        return jsonify({'message': 'Tên danh mục là bắt buộc!'}), 400

    success = CategoryModel.update(category_id, name, description)
    if not success:
        return jsonify({'message': 'Cập nhật danh mục thất bại!'}), 500

    updated = CategoryModel.get_by_id(category_id)
    return jsonify({'message': 'Cập nhật danh mục thành công!', 'category': _serialize_category(updated)}), 200


@product_bp.route('/api/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    category = CategoryModel.get_by_id(category_id)
    if not category:
        return jsonify({'message': 'Không tìm thấy danh mục!'}), 404

    if CategoryModel.has_products(category_id):
        return jsonify({'message': 'Danh mục này đang có sản phẩm, không thể xóa!'}), 400

    success = CategoryModel.delete(category_id)
    if not success:
        return jsonify({'message': 'Xóa danh mục thất bại!'}), 500

    return jsonify({'message': 'Xóa danh mục thành công!'}), 200


@product_bp.route('/api/products', methods=['GET'])
def get_products():
    products = ProductModel.get_all()
    return jsonify({'products': [_serialize_product(item) for item in products]}), 200


@product_bp.route('/api/products', methods=['POST'])
def create_product():
    data = request.json or {}
    category_id = data.get('categoryId')
    name = str(data.get('name', '')).strip()
    description = str(data.get('description', '')).strip()
    image_url = str(data.get('imageUrl', 'default-product.png')).strip() or 'default-product.png'
    status = str(data.get('status', 'active')).strip().lower()

    try:
        price = int(data.get('price', 0))
        stock = int(data.get('stock', 0))
        category_id = int(category_id)
    except (TypeError, ValueError):
        return jsonify({'message': 'Giá, tồn kho và danh mục không hợp lệ!'}), 400

    if not name or price < 0 or stock < 0:
        return jsonify({'message': 'Thông tin sản phẩm không hợp lệ!'}), 400

    if status not in {'active', 'inactive'}:
        return jsonify({'message': 'Trạng thái không hợp lệ!'}), 400

    if not CategoryModel.get_by_id(category_id):
        return jsonify({'message': 'Danh mục không tồn tại!'}), 400

    product_id = ProductModel.create(category_id, name, description, price, stock, image_url, status)
    if not product_id:
        return jsonify({'message': 'Tạo sản phẩm thất bại!'}), 500

    product = ProductModel.get_by_id(product_id)
    return jsonify({'message': 'Tạo sản phẩm thành công!', 'product': _serialize_product(product)}), 201


@product_bp.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    product = ProductModel.get_by_id(product_id)
    if not product:
        return jsonify({'message': 'Không tìm thấy sản phẩm!'}), 404

    data = request.json or {}
    category_id = data.get('categoryId', product.get('category_id'))
    name = str(data.get('name', product.get('name', ''))).strip()
    description = str(data.get('description', product.get('description') or '')).strip()
    image_url = str(data.get('imageUrl', product.get('image_url') or 'default-product.png')).strip() or 'default-product.png'
    status = str(data.get('status', product.get('status', 'active'))).strip().lower()

    try:
        price = int(data.get('price', product.get('price', 0)))
        stock = int(data.get('stock', product.get('stock', 0)))
        category_id = int(category_id)
    except (TypeError, ValueError):
        return jsonify({'message': 'Giá, tồn kho và danh mục không hợp lệ!'}), 400

    if not name or price < 0 or stock < 0:
        return jsonify({'message': 'Thông tin sản phẩm không hợp lệ!'}), 400

    if status not in {'active', 'inactive'}:
        return jsonify({'message': 'Trạng thái không hợp lệ!'}), 400

    if not CategoryModel.get_by_id(category_id):
        return jsonify({'message': 'Danh mục không tồn tại!'}), 400

    success = ProductModel.update(product_id, category_id, name, description, price, stock, image_url, status)
    if not success:
        return jsonify({'message': 'Cập nhật sản phẩm thất bại!'}), 500

    updated = ProductModel.get_by_id(product_id)
    return jsonify({'message': 'Cập nhật sản phẩm thành công!', 'product': _serialize_product(updated)}), 200


@product_bp.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    product = ProductModel.get_by_id(product_id)
    if not product:
        return jsonify({'message': 'Không tìm thấy sản phẩm!'}), 404

    success = ProductModel.delete(product_id)
    if not success:
        return jsonify({'message': 'Xóa sản phẩm thất bại!'}), 500

    return jsonify({'message': 'Xóa sản phẩm thành công!'}), 200
