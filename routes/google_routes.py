from flask import Blueprint, request, jsonify, redirect, url_for
from authlib.integrations.flask_client import OAuth
from config.settings import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from flask_jwt_extended import create_access_token
from datetime import timedelta
from models.user_model import User
from extensions import db

google_oauth_bp = Blueprint('google_oauth', __name__)

# Инициализируем локальный OAuth-объект (можно вынести в extensions, но оставим тут)
oauth = OAuth()

google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@google_oauth_bp.route('/login')
def google_login():
    """Начало OAuth-потока: перенаправляем пользователя на Google."""
    redirect_uri = url_for('google_oauth.google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@google_oauth_bp.route('/callback')
def google_callback():
    """Google возвращает пользователя сюда с параметром ?code=..."""
    token = google.authorize_access_token()
    # authorize_access_token сам обменивает code на токены
    user_info = google.parse_id_token(token)
    # user_info содержит {"sub": "...", "email": "...", "name": "...", ...}

    if not user_info:
        return jsonify({"message": "Failed to get user info from Google"}), 400

    google_id = user_info.get('sub')
    email = user_info.get('email')
    name = user_info.get('name', 'NoName')

    if not email:
        return jsonify({"message": "No email returned from Google"}), 400

    # Ищем пользователя по email
    user = User.query.filter_by(email=email).first()
    if not user:
        # Создаём нового пользователя (поле google_id заранее добавим в модель)
        user = User(email=email, name=name, google_id=google_id)
        db.session.add(user)
        db.session.commit()
    else:
        # Если уже есть пользователь, но нет google_id, заполним
        if not user.google_id:
            user.google_id = google_id
            db.session.commit()

    # Генерируем наш JWT
    access_token = create_access_token(identity=str(user.id), expires_delta=timedelta(hours=2))

    # Можно вернуть JSON или редирект на фронтенд
    return jsonify({
        "message": f"Hello, {user.name}! Google login successful.",
        "access_token": access_token
    }), 200
