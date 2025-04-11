from flask import Flask
from flask_jwt_extended import JWTManager
from config import settings
from extensions import mail, db
from routes.auth_routes import auth_routes
from routes.goals_routes import goals_routes
from routes.ai_routes import ai_routes

def create_app():
    app = Flask(__name__)

    # Настройки приложения
    app.config['SECRET_KEY'] = settings.SECRET_KEY
    app.config['DEBUG'] = settings.DEBUG
    app.config['SQLALCHEMY_DATABASE_URI'] = settings.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = settings.SQLALCHEMY_TRACK_MODIFICATIONS
    app.config['JWT_SECRET_KEY'] = settings.JWT_SECRET_KEY

    # Настройки почты
    app.config['MAIL_SERVER'] = settings.MAIL_SERVER
    app.config['MAIL_PORT'] = settings.MAIL_PORT
    app.config['MAIL_USERNAME'] = settings.MAIL_USERNAME
    app.config['MAIL_PASSWORD'] = settings.MAIL_PASSWORD
    app.config['MAIL_USE_TLS'] = settings.MAIL_USE_TLS
    app.config['MAIL_USE_SSL'] = settings.MAIL_USE_SSL

    # Инициализация расширений
    db.init_app(app)
    mail.init_app(app)
    jwt = JWTManager(app)

    # Создание таблиц
    with app.app_context():
        db.create_all()

    # Регистрация маршрутов
    app.register_blueprint(auth_routes, url_prefix='/auth')
    app.register_blueprint(goals_routes, url_prefix='/api')
    app.register_blueprint(ai_routes, url_prefix='/api')

    @app.route('/')
    def home():
        return "Welcome to WhatIamToDo server!"

    return app

if __name__ == '__main__':
    app = create_app()
    app.run()