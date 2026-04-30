import os

from flask import Flask
from flask_cors import CORS

from controllers.auth_controller import auth_bp
from controllers.chat_controller import chat_bp
from controllers.order_controller import order_bp
from controllers.product_controller import product_bp
from controllers.profile_controller import profile_bp


def load_env_file():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(env_path):
        return

    with open(env_path, 'r', encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip().lstrip('\ufeff')
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_env_file()

app = Flask(__name__)
CORS(app)
app.config['AVATAR_UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads', 'avatars')
app.config['PRODUCT_UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads', 'products')
app.config['PAYMENT_PROVIDER'] = os.getenv('PAYMENT_PROVIDER', 'vietqr')
app.config['PAYMENT_BANK_CODE'] = os.getenv('PAYMENT_BANK_CODE', 'VCB')
app.config['PAYMENT_ACCOUNT_NO'] = os.getenv('PAYMENT_ACCOUNT_NO', '')
app.config['PAYMENT_ACCOUNT_NAME'] = os.getenv('PAYMENT_ACCOUNT_NAME', '')
app.config['ENABLE_MANUAL_PAYMENT_CONFIRM'] = os.getenv('ENABLE_MANUAL_PAYMENT_CONFIRM', 'false').lower() == 'true'

app.register_blueprint(product_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(order_bp)
app.register_blueprint(chat_bp)

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    print(f'Server Flask dang chay tai cong {port}...')
    app.run(host='0.0.0.0', debug=debug, port=port)
