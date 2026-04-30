from datetime import datetime, timedelta
import os
import random
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from models.email_verification_model import EmailVerificationModel
from models.password_reset_model import PasswordResetModel
from models.user_model import UserModel

auth_bp = Blueprint('auth_bp', __name__)


def _normalize_phone(phone):
    return ''.join(ch for ch in str(phone or '').strip() if ch.isdigit())


def _is_valid_vietnam_phone(phone):
    normalized_phone = _normalize_phone(phone)
    if not normalized_phone:
        return False
    if not (normalized_phone.startswith('09') or normalized_phone.startswith('03')):
        return False
    return len(normalized_phone) in {10, 11}


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


def _send_register_verification_email(receiver_email, verification_code):
    _send_email(
        receiver_email,
        'Mã xác thực đăng ký tài khoản K-COFFEE',
        (
            'Xin chào,\n\n'
            f'Mã xác thực đăng ký của bạn là: {verification_code}\n'
            'Mã có hiệu lực trong 5 phút.\n\n'
            'Nếu bạn không thực hiện yêu cầu này, hãy bỏ qua email.\n\n'
            'K-COFFEE'
        ),
    )


def _send_password_reset_email(receiver_email, verification_code):
    _send_email(
        receiver_email,
        'Mã xác thực quên mật khẩu K-COFFEE',
        (
            'Xin chào,\n\n'
            f'Mã xác thực đặt lại mật khẩu của bạn là: {verification_code}\n'
            'Mã có hiệu lực trong 5 phút.\n\n'
            'Nếu bạn không thực hiện yêu cầu này, hãy bỏ qua email.\n\n'
            'K-COFFEE'
        ),
    )


@auth_bp.route('/api/register/request-code', methods=['POST'])
def request_register_code():
    data = request.json or {}
    full_name = str(data.get('fullName', '')).strip()
    phone = _normalize_phone(data.get('phone', ''))
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', '')).strip()

    if not full_name or not phone or not email or not password:
        return jsonify({'message': 'Họ tên, số điện thoại, email và mật khẩu là bắt buộc.'}), 400

    if not _is_valid_vietnam_phone(phone):
        return jsonify({'message': 'Số điện thoại không hợp lệ. Chỉ chấp nhận đầu 09 hoặc 03 và dài 10 hoặc 11 số.'}), 400

    if UserModel.get_user_by_email(email):
        return jsonify({'message': 'Email này đã có tài khoản. Vui lòng dùng chức năng quên mật khẩu.'}), 400

    verification_code = f"{random.randint(0, 999999):06d}"
    hashed_password = generate_password_hash(password)
    expires_at = datetime.now() + timedelta(minutes=5)

    saved = EmailVerificationModel.upsert_pending(
        full_name,
        phone,
        email,
        hashed_password,
        verification_code,
        expires_at,
    )
    if not saved:
        return jsonify({'message': 'Không thể tạo yêu cầu xác thực email.'}), 500

    try:
        _send_register_verification_email(email, verification_code)
    except Exception as error:
        return jsonify({'message': str(error)}), 500

    return jsonify({'message': 'Đã gửi mã xác thực về email. Vui lòng kiểm tra hộp thư.'}), 200


@auth_bp.route('/api/register/verify', methods=['POST'])
def verify_register_code():
    data = request.json or {}
    email = str(data.get('email', '')).strip().lower()
    verification_code = str(data.get('verificationCode', '')).strip()

    if not email or not verification_code:
        return jsonify({'message': 'Email và mã xác thực là bắt buộc.'}), 400

    if UserModel.get_user_by_email(email):
        return jsonify({'message': 'Email này đã có tài khoản. Vui lòng dùng chức năng quên mật khẩu.'}), 400

    verification_record = EmailVerificationModel.get_by_email(email)
    if not verification_record:
        return jsonify({'message': 'Không tìm thấy yêu cầu xác thực email.'}), 404

    if not EmailVerificationModel.is_code_valid(verification_record, verification_code):
        return jsonify({'message': 'Mã xác thực không đúng hoặc đã hết hạn.'}), 400

    success = UserModel.create_user(
        verification_record['full_name'],
        verification_record.get('phone'),
        email,
        verification_record['hashed_password'],
    )
    if not success:
        return jsonify({'message': 'Có lỗi xảy ra khi tạo tài khoản, vui lòng thử lại!'}), 500

    EmailVerificationModel.mark_verified(email)
    EmailVerificationModel.delete(email)
    return jsonify({'message': 'Đăng ký tài khoản thành công!'}), 201


@auth_bp.route('/api/password-reset/request-code', methods=['POST'])
def request_password_reset_code():
    data = request.json or {}
    email = str(data.get('email', '')).strip().lower()

    if not email:
        return jsonify({'message': 'Email là bắt buộc.'}), 400

    if not UserModel.get_user_by_email(email):
        return jsonify({'message': 'Email chưa được đăng ký tài khoản.'}), 404

    verification_code = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.now() + timedelta(minutes=5)

    saved = PasswordResetModel.upsert_pending(email, verification_code, expires_at)
    if not saved:
        return jsonify({'message': 'Không thể tạo yêu cầu quên mật khẩu.'}), 500

    try:
        _send_password_reset_email(email, verification_code)
    except Exception as error:
        return jsonify({'message': str(error)}), 500

    return jsonify({'message': 'Đã gửi mã xác thực quên mật khẩu về email.'}), 200


@auth_bp.route('/api/password-reset/verify', methods=['POST'])
def verify_password_reset_code():
    data = request.json or {}
    email = str(data.get('email', '')).strip().lower()
    verification_code = str(data.get('verificationCode', '')).strip()
    new_password = str(data.get('newPassword', '')).strip()

    if not email or not verification_code or not new_password:
        return jsonify({'message': 'Email, mã xác thực và mật khẩu mới là bắt buộc.'}), 400

    user = UserModel.get_user_by_email(email)
    if not user:
        return jsonify({'message': 'Email chưa được đăng ký tài khoản.'}), 404

    reset_record = PasswordResetModel.get_by_email(email)
    if not reset_record:
        return jsonify({'message': 'Không tìm thấy yêu cầu quên mật khẩu.'}), 404

    if not PasswordResetModel.is_code_valid(reset_record, verification_code):
        return jsonify({'message': 'Mã xác thực không đúng hoặc đã hết hạn.'}), 400

    success = UserModel.update_password(user['id'], generate_password_hash(new_password))
    if not success:
        return jsonify({'message': 'Không thể cập nhật mật khẩu mới.'}), 500

    PasswordResetModel.delete(email)
    return jsonify({'message': 'Đổi mật khẩu thành công. Bạn có thể đăng nhập lại.'}), 200


@auth_bp.route('/api/register', methods=['POST'])
def register_legacy():
    return jsonify({
        'message': 'Vui lòng dùng luồng gửi mã xác thực email trước khi hoàn tất đăng ký.'
    }), 400


@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', '')).strip()

    try:
        user = UserModel.get_user_by_email(email)
        if user and check_password_hash(user['password'], password):
            return jsonify({
                'message': 'Đăng nhập thành công!',
                'user': {
                    'id': user['id'],
                    'full_name': user['full_name'],
                    'phone': user.get('phone'),
                    'email': user['email'],
                    'role': user['role'],
                    'address': user.get('address'),
                    'avatar': user.get('avatar'),
                },
            }), 200
    except Exception as error:
        print('Loi khi dang nhap:', error)
        return jsonify({
            'message': 'Server chưa kết nối được cơ sở dữ liệu. Vui lòng kiểm tra biến môi trường DB trên Render/Aiven.'
        }), 500

    return jsonify({'message': 'Email hoặc mật khẩu không chính xác!'}), 401
