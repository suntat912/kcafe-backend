import os

import mysql.connector


def _get_required_env(key):
    value = os.getenv(key)
    if value is None or value.strip() == '':
        raise RuntimeError(f'Thieu bien moi truong {key}. Hay cau hinh trong .env hoac tren hosting.')
    return value.strip()


def get_db_connection():
    config = {
        'host': _get_required_env('DB_HOST'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'user': _get_required_env('DB_USER'),
        'password': _get_required_env('DB_PASSWORD'),
        'database': _get_required_env('DB_NAME'),
        'connection_timeout': int(os.getenv('DB_CONNECTION_TIMEOUT', '5')),
    }

    ssl_ca = os.getenv('DB_SSL_CA')
    if ssl_ca:
        config['ssl_ca'] = ssl_ca.strip()

    return mysql.connector.connect(**config)
