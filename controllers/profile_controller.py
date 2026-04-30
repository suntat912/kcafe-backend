import os
import random
import smtplib
import uuid
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from models.password_reset_model import PasswordResetModel
from models.user_model import UserModel

profile_bp = Blueprint('profile_bp', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _normalize_phone(phone):
    return ''.join(ch for ch in str(phone or '').strip() if ch.isdigit())


def _is_valid_vietnam_phone(phone):
    normalized_phone = _normalize_phone(phone)
    if not normalized_phone:
        return False
    if not (normalized_phone.startswith('09') or normalized_phone.startswith('03')):
        return False
    return len(normalized_phone) in {10, 11}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _serialize_user(user):
    return {
        'id': user['id'],
        'full_name': user['full_name'],
        'phone': user.get('phone'),
        'email': user['email'],
        'role': user.get('role'),
        'address': user.get('address'),
        'avatar': user.get('avatar'),
    }


def _send_email(receiver_email, subject, body):
    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    smtp_sender = os.getenv('SMTP_SENDER_EMAIL', smtp_user or '')
    smtp_sender_name = os.getenv('SMTP_SENDER_NAME', 'K-COFFEE')

    if not smtp_host or not smtp_user or not smtp_password or not smtp_sender:
        raise RuntimeError('Chưa cấu hình SMTP để gửi mã xác thực email.')

    message = MIMEText(body, 'plain', 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')
    message['From'] = formataddr((str(Header(smtp_sender_name, 'utf-8')), smtp_sender))
    message['To'] = receiver_email

    server = smtplib.SMTP(smtp_host, smtp_port)
    try:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_sender, [receiver_email], message.as_string())
    finally:
        server.quit()


def _send_change_password_email(receiver_email, verification_code):
    _send_email(
        receiver_email,
        'Mã xác thực đổi mật khẩu K-COFFEE',
        (
            'Xin chào,\n\n'
            f'Mã xác thực đổi mật khẩu của bạn là: {verification_code}\n'
            'Mã có hiệu lực trong 5 phút.\n\n'
            'Nếu bạn không thực hiện yêu cầu này, hãy bỏ qua email.\n\n'
            'K-COFFEE'
        ),
    )


@profile_bp.route('/api/profile/<int:user_id>', methods=['GET'])
def get_profile(user_id):
    user = UserModel.get_user_by_id(user_id)
    if not user:
        return jsonify({'message': 'Khong tim thay tai khoan!'}), 404

    return jsonify({'user': _serialize_user(user)}), 200


@profile_bp.route('/api/profile/<int:user_id>', methods=['PUT'])
def update_profile(user_id):
    user = UserModel.get_user_by_id(user_id)
    if not user:
        return jsonify({'message': 'Khong tim thay tai khoan!'}), 404

    data = request.json or {}
    full_name = data.get('fullName', user.get('full_name'))
    phone = _normalize_phone(data.get('phone', user.get('phone')))
    email = data.get('email', user.get('email'))
    address = data.get('address', user.get('address'))

    if not full_name or not phone or not email:
        return jsonify({'message': 'Họ tên, số điện thoại và email là bắt buộc!'}), 400

    if not _is_valid_vietnam_phone(phone):
        return jsonify({'message': 'Số điện thoại không hợp lệ. Chỉ chấp nhận đầu 09 hoặc 03 và dài 10 hoặc 11 số!'}), 400

    existing_user = UserModel.get_user_by_email(email)
    if existing_user and existing_user['id'] != user_id:
        return jsonify({'message': 'Email da duoc su dung!'}), 400

    success = UserModel.update_profile(user_id, full_name, phone, email, address)
    if not success:
        return jsonify({'message': 'Cap nhat ho so that bai!'}), 500

    updated_user = UserModel.get_user_by_id(user_id)
    return jsonify({'message': 'Cap nhat ho so thanh cong!', 'user': _serialize_user(updated_user)}), 200


@profile_bp.route('/api/profile/<int:user_id>/password/request-code', methods=['POST'])
def request_change_password_code(user_id):
    user = UserModel.get_user_by_id(user_id)
    if not user:
        return jsonify({'message': 'Không tìm thấy tài khoản!'}), 404

    data = request.json or {}
    current_password = data.get('currentPassword')

    if not current_password:
        return jsonify({'message': 'Thiếu mật khẩu hiện tại!'}), 400

    if not check_password_hash(user['password'], current_password):
        return jsonify({'message': 'Mật khẩu hiện tại không đúng!'}), 400

    verification_code = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.now() + timedelta(minutes=5)
    saved = PasswordResetModel.upsert_pending(user['email'], verification_code, expires_at)
    if not saved:
        return jsonify({'message': 'Không thể tạo yêu cầu xác thực đổi mật khẩu!'}), 500

    try:
        _send_change_password_email(user['email'], verification_code)
    except Exception as error:
        return jsonify({'message': str(error)}), 500

    return jsonify({'message': 'Đã gửi mã OTP xác thực đổi mật khẩu về email.'}), 200


@profile_bp.route('/api/profile/<int:user_id>/password/verify', methods=['PUT'])
def change_password(user_id):
    user = UserModel.get_user_by_id(user_id)
    if not user:
        return jsonify({'message': 'Không tìm thấy tài khoản!'}), 404

    data = request.json or {}
    verification_code = str(data.get('verificationCode', '')).strip()
    new_password = str(data.get('newPassword', '')).strip()

    if not verification_code or not new_password:
        return jsonify({'message': 'Thiếu mã OTP hoặc mật khẩu mới!'}), 400

    reset_record = PasswordResetModel.get_by_email(user['email'])
    if not reset_record:
        return jsonify({'message': 'Không tìm thấy yêu cầu xác thực đổi mật khẩu.'}), 404

    if not PasswordResetModel.is_code_valid(reset_record, verification_code):
        return jsonify({'message': 'Mã OTP không đúng hoặc đã hết hạn.'}), 400

    success = UserModel.update_password(user_id, generate_password_hash(new_password))
    if not success:
        return jsonify({'message': 'Đổi mật khẩu thất bại!'}), 500

    PasswordResetModel.delete(user['email'])
    return jsonify({'message': 'Đổi mật khẩu thành công!'}), 200


@profile_bp.route('/api/profile/<int:user_id>/avatar', methods=['POST'])
def upload_avatar(user_id):
    user = UserModel.get_user_by_id(user_id)
    if not user:
        return jsonify({'message': 'Khong tim thay tai khoan!'}), 404

    if 'avatar' not in request.files:
        return jsonify({'message': 'Khong co file avatar!'}), 400

    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'message': 'Ban chua chon anh!'}), 400

    if not _allowed_file(file.filename):
        return jsonify({'message': 'Dinh dang anh khong hop le!'}), 400

    extension = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    filename = f"user_{user_id}_{uuid.uuid4().hex}.{extension}"
    upload_folder = current_app.config['AVATAR_UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    file.save(os.path.join(upload_folder, filename))

    success = UserModel.update_avatar(user_id, filename)
    if not success:
        return jsonify({'message': 'Cap nhat avatar that bai!'}), 500

    updated_user = UserModel.get_user_by_id(user_id)
    return jsonify({'message': 'Cap nhat avatar thanh cong!', 'user': _serialize_user(updated_user)}), 200


@profile_bp.route('/uploads/avatars/<path:filename>', methods=['GET'])
def get_avatar(filename):
    return send_from_directory(current_app.config['AVATAR_UPLOAD_FOLDER'], filename)


@profile_bp.route('/api/admin/users', methods=['GET'])
def get_users():
    users = UserModel.get_all_users()
    return jsonify({'users': [_serialize_user(user) for user in users]}), 200


@profile_bp.route('/api/admin/users/<int:user_id>/role', methods=['PUT'])
def update_user_role(user_id):
    user = UserModel.get_user_by_id(user_id)
    if not user:
        return jsonify({'message': 'Khong tim thay tai khoan!'}), 404

    data = request.json or {}
    role = str(data.get('role', '')).lower()
    if role not in {'admin', 'customer'}:
        return jsonify({'message': 'Role khong hop le!'}), 400

    success = UserModel.update_role(user_id, role)
    if not success:
        return jsonify({'message': 'Cap nhat role that bai!'}), 500

    updated_user = UserModel.get_user_by_id(user_id)
    return jsonify({'message': 'Cap nhat role thanh cong!', 'user': _serialize_user(updated_user)}), 200


@profile_bp.route('/api/admin/users', methods=['POST'])
def create_user_admin():
    data = request.json or {}
    full_name = str(data.get('fullName', '')).strip()
    phone = _normalize_phone(data.get('phone', ''))
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', '')).strip()
    role = str(data.get('role', 'customer')).strip().lower()
    address = str(data.get('address', '')).strip()

    if not full_name or not phone or not email or not password:
        return jsonify({'message': 'Ho ten, so dien thoai, email va mat khau la bat buoc!'}), 400

    if not _is_valid_vietnam_phone(phone):
        return jsonify({'message': 'So dien thoai khong hop le! Chi chap nhan dau 09 hoac 03 va dai 10 hoac 11 so.'}), 400

    if role not in {'admin', 'customer'}:
        return jsonify({'message': 'Role khong hop le!'}), 400

    if UserModel.get_user_by_email(email):
        return jsonify({'message': 'Email da duoc su dung!'}), 400

    user_id = UserModel.create_user_by_admin(
        full_name,
        phone,
        email,
        generate_password_hash(password),
        role,
        address,
    )
    if not user_id:
        return jsonify({'message': 'Tao tai khoan that bai!'}), 500

    new_user = UserModel.get_user_by_id(user_id)
    return jsonify({'message': 'Tao tai khoan thanh cong!', 'user': _serialize_user(new_user)}), 201


@profile_bp.route('/api/admin/users/<int:user_id>', methods=['PUT'])
def update_user_admin(user_id):
    user = UserModel.get_user_by_id(user_id)
    if not user:
        return jsonify({'message': 'Khong tim thay tai khoan!'}), 404

    data = request.json or {}
    full_name = str(data.get('fullName', user.get('full_name', ''))).strip()
    phone = _normalize_phone(data.get('phone', user.get('phone') or ''))
    email = str(data.get('email', user.get('email', ''))).strip().lower()
    role = str(data.get('role', user.get('role', 'customer'))).strip().lower()
    address = str(data.get('address', user.get('address') or '')).strip()

    if not full_name or not phone or not email:
        return jsonify({'message': 'Ho ten, so dien thoai va email la bat buoc!'}), 400

    if not _is_valid_vietnam_phone(phone):
        return jsonify({'message': 'So dien thoai khong hop le! Chi chap nhan dau 09 hoac 03 va dai 10 hoac 11 so.'}), 400

    if role not in {'admin', 'customer'}:
        return jsonify({'message': 'Role khong hop le!'}), 400

    existing_user = UserModel.get_user_by_email(email)
    if existing_user and existing_user['id'] != user_id:
        return jsonify({'message': 'Email da duoc su dung!'}), 400

    success = UserModel.update_user_admin(user_id, full_name, phone, email, role, address)
    if not success:
        return jsonify({'message': 'Cap nhat tai khoan that bai!'}), 500

    updated_user = UserModel.get_user_by_id(user_id)
    return jsonify({'message': 'Cap nhat tai khoan thanh cong!', 'user': _serialize_user(updated_user)}), 200


@profile_bp.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def delete_user_admin(user_id):
    user = UserModel.get_user_by_id(user_id)
    if not user:
        return jsonify({'message': 'Khong tim thay tai khoan!'}), 404

    success = UserModel.delete_user(user_id)
    if not success:
        return jsonify({'message': 'Xoa tai khoan that bai!'}), 500

    return jsonify({'message': 'Xoa tai khoan thanh cong!'}), 200
