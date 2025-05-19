import pyodbc
from app.config import Config

def get_connection():
    connection_str = (
        f'DRIVER={{ODBC Driver 17 for SQL Server}};'
        f'SERVER={Config.SERVER};DATABASE={Config.DATABASE};'
        f'UID={Config.USERNAME};PWD={Config.PASSWORD}'
    )
    conn = pyodbc.connect(connection_str)
    conn.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
    conn.setencoding('utf-8')
    return conn