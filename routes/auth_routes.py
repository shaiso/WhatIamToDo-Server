from flask import Blueprint, request, jsonify
from flask_mail import Message
from datetime import datetime, timedelta
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from extensions import mail, db
from models.user_model import User
from models.goal_model import Goal
import re

auth_routes = Blueprint('auth', __name__)

EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
PASSWORD_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])[a-zA-Z0-9]{7,}$"
)

@auth_routes.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    email = data.get('email')
    password = data.get('password')
    name = data.get('name')

    if not email or not password or not name:
        return jsonify({"message": "All fields are required"}), 400

    if not EMAIL_REGEX.match(email):
        return jsonify({"message": "Invalid email format"}), 400

    if not PASSWORD_REGEX.match(password):
        return jsonify({
            "message": ("Password must be at least 7 characters long and "
                        "include uppercase, lowercase, and digit.")
        }), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"message": "Email already registered"}), 400

    new_user = User(email=email, name=name)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    # Создаем цель "Повседневные дела"
    color = "#CCCCFF"
    daily_goal = Goal(
        user_id=new_user.id,
        title="Повседневные дела",
        description="",
        color=color
    )
    db.session.add(daily_goal)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201

@auth_routes.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"message": "Invalid email or password"}), 401

    access_token = create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(hours=10)
    )

    return jsonify({
        "message": f"{user.name}",
        "access_token": access_token
    }), 200

@auth_routes.route('/recover-password', methods=['POST'])
def recover_password():
    """
    Генерируем/высылаем одноразовый код на почту.
    Если пользователь нажал "Отправить код ещё раз" — проверяем, прошло ли не меньше 1 минуты
    с момента последней отправки (reset_token_sent_at).
    """
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"message": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    # Проверяем, что прошло >= 1 минуты после предыдущей отправки
    if user.reset_token_sent_at is not None:
        diff = datetime.utcnow() - user.reset_token_sent_at
        if diff < timedelta(minutes=1):
            return jsonify({
                "message": "A code was sent recently. Please wait at least 1 minute before requesting again."
            }), 400

    # Генерируем новый код (или продлеваем срок)
    user.generate_reset_token(expires_in=30)
    db.session.commit()

    code = user.reset_token

    msg = Message(
        subject="Password Recovery",
        sender="WhatImTodo App",
        recipients=[user.email],
        body=(
            f"Hello, {user.name}!\n\n"
            f"Your one-time code for password reset is: {code}\n\n"
            "This code is valid for 30 minutes. If you didn't request a password reset, just ignore this email."
        )
    )
    mail.send(msg)

    return jsonify({"message": "Recovery email has been sent"}), 200

@auth_routes.route('/reset-password', methods=['POST'])
def reset_password():
    """
    При сбросе пароля дополнительно проверяем сложность нового пароля.
    """
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        return jsonify({"message": "Token and new_password are required"}), 400

    # Проверяем сложность нового пароля
    if not PASSWORD_REGEX.match(new_password):
        return jsonify({
            "message": ("Password must be at least 7 characters long and "
                        "include uppercase, lowercase, and digit.")
        }), 400

    user = User.query.filter_by(reset_token=token).first()
    if not user:
        return jsonify({"message": "Invalid one-time key"}), 400

    if not user.reset_token_expires or datetime.utcnow() > user.reset_token_expires:
        return jsonify({"message": "one-time key has expired"}), 400

    user.set_password(new_password)
    user.clear_reset_token()
    db.session.commit()

    return jsonify({"message": "Password reset successfully"}), 200

@auth_routes.route('/protected', methods=['GET'])
@jwt_required()
def protected_route():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)

    if not user:
        return jsonify({"message": "User not found"}), 404

    return jsonify({
        "message": f"Hello, {user.name}. This is a protected route."
    }), 200
