import mysql.connector

def get_db_connection():
    connection = mysql.connector.connect(
        host='127.0.0.1',
        user='root',      
        password='1234',      
        database='coffee_shop_db'
    )
    return connection