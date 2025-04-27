from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100), nullable=False)

    reset_token = db.Column(db.String(50), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    reset_token_sent_at = db.Column(db.DateTime, nullable=True) 

    def generate_reset_token(self, expires_in=30):
        """
        Генерирует код (например 4-значный), сохраняет в БД + время истечения.
        Также фиксируем reset_token_sent_at = сейчас (для логики "повторной отправки").
        """
        code = str(random.randint(1000, 9999))
        self.reset_token = code
        self.reset_token_expires = datetime.utcnow() + timedelta(minutes=expires_in)
        self.reset_token_sent_at = datetime.utcnow()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_expires = None
        self.reset_token_sent_at = None

