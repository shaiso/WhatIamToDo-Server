from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'fallback-secret-key')
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1']
SQLALCHEMY_DATABASE_URI = os.getenv(
    'SQLALCHEMY_DATABASE_URI',
    "postgresql+psycopg://testuser:testpassword@localhost/testdb"
)

SQLALCHEMY_TRACK_MODIFICATIONS = False

JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'fallback_jwt_secret')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Настройки почты
MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() in ['true', '1']
MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False').lower() in ['true', '1']