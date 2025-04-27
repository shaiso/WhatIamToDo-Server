from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.goal_model import Goal
from models.step_model import Step
from models.user_model import User
from datetime import datetime
from utils.color_utils import get_unique_pastel_color
from dateutil.parser import isoparse

goals_routes = Blueprint('goals_routes', __name__)

@goals_routes.route('/goals', methods=['POST'])
@jwt_required()
def create_goal():
    """
    Создаём новую цель + сразу связанные шаги.
    Тело запроса (пример):
    {
      "title": "Построить дом",
      "description": "Хочу построить двухэтажный дом",
      "steps": [
         {"title": "Подготовить участок", "description": "...", "date": "2025-03-22"},
         {"title": "Закупить материалы", "description": "...", "date": "2025-03-25"}
      ]
    }
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    steps_data = data.get('steps', [])

    # Обязательное условие: должна быть как минимум 1 задача-Шаг
    if not steps_data:
        return jsonify({"message": "You must provide at least one step"}), 400

    if not title:
        return jsonify({"message": "Goal title is required"}), 400

    # Находим, какие цвета уже заняты у этого юзера
    user_goals = Goal.query.filter_by(user_id=user.id).all()
    used_colors = [g.color for g in user_goals if g.color]

    
    color = get_unique_pastel_color(used_colors)
    if color is None:
        color = "#D3D3D3"  

    new_goal = Goal(user_id=user.id, title=title, description=description, color=color)
    db.session.add(new_goal)
    db.session.flush()  # чтобы у new_goal появился ID

    # Создаём шаги
    for step_info in steps_data:
        step_title = step_info.get('title')
        if not step_title:
            continue
        step_description = step_info.get('description')
        date_str = step_info.get('date')
        date_val = datetime.fromisoformat(date_str) if date_str else None

        new_step = Step(
            goal_id=new_goal.id,
            title=step_title,
            description=step_description,
            date=date_val
        )
        db.session.add(new_step)

    db.session.commit()

    new_goal.update_progress()
    db.session.commit()

    return jsonify({
        "message": "Goal created successfully",
        "goal_id": new_goal.id,
        "color_assigned": new_goal.color
    }), 201

@goals_routes.route('/goals', methods=['GET'])
@jwt_required()
def get_goals():
    """
    Возвращает все цели пользователя (без деталей шагов).
    """
    current_user_id = int(get_jwt_identity())
    goals = Goal.query.filter_by(user_id=current_user_id).all()

    result = []
    for g in goals:
        result.append({
            "id": g.id,
            "title": g.title,
            "description": g.description,
            "color": g.color,
            "progress": g.progress,
            "created_at": g.created_at.isoformat(),
            "updated_at": g.updated_at.isoformat()
        })

    return jsonify(result), 200

@goals_routes.route('/goals/<int:goal_id>', methods=['GET'])
@jwt_required()
def get_goal_detail(goal_id):
    """
    Возвращает полную информацию по одной цели, включая шаги.
    """
    current_user_id = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user_id).first()
    if not goal:
        return jsonify({"message": "Goal not found"}), 404

    steps_data = []
    for s in goal.steps:
        steps_data.append({
            "id": s.id,
            "goal_id": goal.id,
            "goal_name": goal.title,
            "color": goal.color,
            "title": s.title,
            "description": s.description,
            "status": s.status,
            "date": s.date.isoformat() if s.date else None,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat()
        })

    data = {
        "id": goal.id,
        "title": goal.title,
        "description": goal.description,
        "color": goal.color,
        "progress": goal.progress,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
        "steps": steps_data
    }
    return jsonify(data), 200

@goals_routes.route('/goals/<int:goal_id>/info', methods=['GET'])
@jwt_required()
def get_goal_without_steps(goal_id):
    """
    Возвращает информацию по одной цели без подробностей шагов.
    """
    current_user_id = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user_id).first()
    if not goal:
        return jsonify({"message": "Goal not found"}), 404

    data = {
        "id": goal.id,
        "title": goal.title,
        "description": goal.description,
        "color": goal.color,
        "progress": goal.progress,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat()
    }
    return jsonify(data), 200

@goals_routes.route('/goals/<int:goal_id>/steps/<int:step_id>', methods=['GET'])
@jwt_required()
def get_goal_step_detail(goal_id, step_id):
    current_user_id = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user_id).first()
    if not goal:
        return jsonify({"message": "Goal not found"}), 404

    step = next((s for s in goal.steps if s.id == step_id), None)
    if not step:
        return jsonify({"message": "Step not found in goal"}), 404

    goal.update_progress()
    db.session.commit()

    step_data = {
        "id": step.id,
        "goal_id": step.goal_id,
        "goal_name": goal.title,
        "color": goal.color,
        "title": step.title,
        "description": step.description,
        "status": step.status,
        "date": step.date.isoformat() if step.date else None,
        "created_at": step.created_at.isoformat(),
        "updated_at": step.updated_at.isoformat()
    }

    data = {
        "id": goal.id,
        "title": goal.title,
        "description": goal.description,
        "color": goal.color,
        "progress": goal.progress,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
        "steps": [step_data]
    }
    return jsonify(data), 200




@goals_routes.route('/goals/with-steps', methods=['GET'])
@jwt_required()
def get_goals_with_steps():
    """
    Возвращает все цели пользователя вместе со всеми шагами для каждой цели.
    """
    current_user_id = int(get_jwt_identity())
    goals = Goal.query.filter_by(user_id=current_user_id).all()

    result = []
    for g in goals:
        steps_data = []
        for s in g.steps:
            steps_data.append({
                "id": s.id,
                "goal_id": g.id,
                "goal_name": g.title,
                "color": g.color,
                "title": s.title,
                "description": s.description,
                "status": s.status,
                "date": s.date.isoformat() if s.date else None,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat()
            })
        result.append({
            "id": g.id,
            "title": g.title,
            "description": g.description,
            "color": g.color,
            "progress": g.progress,
            "created_at": g.created_at.isoformat(),
            "updated_at": g.updated_at.isoformat(),
            "steps": steps_data
        })

    return jsonify(result), 200

@goals_routes.route('/goals/<int:goal_id>', methods=['PUT', 'PATCH'])
@jwt_required()
def update_goal(goal_id):
    """
    Обновляет поля цели. Шаги тут не трогаем.
    """
    current_user_id = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user_id).first()
    if not goal:
        return jsonify({"message": "Goal not found"}), 404

    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    color = data.get('color')

    if title:
        goal.title = title
    if description:
        goal.description = description
    if color:
        goal.color = color

    db.session.commit()
    return jsonify({"message": "Goal updated"}), 200

@goals_routes.route('/goals/<int:goal_id>', methods=['DELETE'])
@jwt_required()
def delete_goal(goal_id):
    """
    Удаляет цель и каскадно все шаги (см. cascade="all, delete" в модели).
    """
    current_user_id = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user_id).first()
    if not goal:
        return jsonify({"message": "Goal not found"}), 404

    db.session.delete(goal)
    db.session.commit()
    return jsonify({"message": "Goal deleted"}), 200

@goals_routes.route('/goals/<int:goal_id>/steps', methods=['POST'])
@jwt_required()
def add_step_to_goal(goal_id):
    """
    Добавить шаг к уже существующей цели.
    Тело запроса (пример):
    {
      "title": "Подготовить инструменты",
      "description": "...",
      "date": "2025-03-22"
    }
    """
    current_user_id = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user_id).first()
    if not goal:
        return jsonify({"message": "Goal not found"}), 404

    data = request.get_json()

    step_description=data.get('description')
    if not step_description:
        return jsonify({"message": "Step description is required"}), 400

    date_str = data.get('date')
    date_val = datetime.fromisoformat(date_str) if date_str else None

    new_step = Step(
        goal_id=goal.id,
        title="Повседневные дела",
        description=step_description,
        date=date_val
    )
    db.session.add(new_step)
    db.session.commit()

    # Пересчитываем прогресс
    goal.update_progress()
    db.session.commit()

    return jsonify({"message": "Step added", "step_id": new_step.id}), 201

@goals_routes.route('/steps/<int:step_id>', methods=['PUT', 'PATCH'])
@jwt_required()
def update_step(step_id):
    """
    Обновляет шаг (статус, дату, описание и т.д.).
    При смене статуса на 'done' или 'planned' — пересчитываем прогресс в родительской цели.
    """
    current_user_id = int(get_jwt_identity())
    step = Step.query.get(step_id)
    if not step:
        return jsonify({"message": "Step not found"}), 404

    if step.goal.user_id != int(current_user_id):
        return jsonify({"message": "Not authorized"}), 403

    data = request.get_json()
    if 'title' in data:
        step.title = data['title']
    if 'description' in data:
        step.description = data['description']
    if 'status' in data:
        step.status = data['status']
    if 'date' in data:
        if data['date']:
            step.date = datetime.fromisoformat(data['date'])
        else:
            step.date = None

    db.session.commit()
    step.goal.update_progress()
    db.session.commit()

    return jsonify({"message": "Step updated"}), 200

@goals_routes.route('/steps/<int:step_id>', methods=['DELETE'])
@jwt_required()
def delete_step(step_id):
    """
    Удаляет шаг и пересчитывает прогресс.
    """
    current_user_id = int(get_jwt_identity())
    step = Step.query.get(step_id)
    if not step:
        return jsonify({"message": "Step not found"}), 404

    if step.goal.user_id != int(current_user_id):
        return jsonify({"message": "Not authorized"}), 403

    goal = step.goal
    db.session.delete(step)
    db.session.commit()

    goal.update_progress()
    db.session.commit()

    return jsonify({"message": "Step deleted"}), 200

@goals_routes.route('/steps/bulk', methods=['POST'])
@jwt_required()
def get_steps_bulk():
    """
    Получает подробные данные для набора шагов по их идентификаторам.
    Тело запроса (пример):
    {
      "step_ids": [1, 2, 3, 4]
    }
    Возвращает:
    {
      "steps": [
         {
           "id": 1,
           "title": "Название шага",
           "description": "Описание шага",
           "status": "Статус",
           "date": "YYYY-MM-DD",
           "created_at": "...",
           "updated_at": "...",
           "color": "Цвет родительской цели",
           "goal_id": 10,
           "goal_name": "Название цели"
         },
         ...
      ]
    }
    """
    current_user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    step_ids = data.get("step_ids")
    if not step_ids or not isinstance(step_ids, list):
        return jsonify({"message": "Field 'step_ids' must be provided as a list"}), 400

    steps = Step.query.filter(Step.id.in_(step_ids)).all()
    user_steps = []
    for step in steps:
        if step.goal.user_id == int(current_user_id):
            user_steps.append({
                "id": step.id,
                "goal_id": step.goal.id,
                "goal_name": step.goal.title,
                "color": step.goal.color,
                "title": step.title,
                "description": step.description,
                "status": step.status,
                "date": step.date.isoformat() if step.date else None,
                "created_at": step.created_at.isoformat(),
                "updated_at": step.updated_at.isoformat()
            })

    return jsonify({"steps": user_steps}), 200


@goals_routes.route('/goals/<int:goal_id>/steps/bulk', methods=['POST'])
@jwt_required()
def add_steps_bulk(goal_id):
    """
    Импорт календаря iOS — массовое добавление шагов к цели "Повседневные дела".
    Ожидает JSON {"steps": [{"description": str, "date": "YYYY-MM-DDTHH:MM:SS"} , …]}
    """
    from datetime import datetime
    from dateutil import parser  

    current_user_id = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user_id).first()
    if not goal:
        return jsonify({"message": "Goal not found"}), 404

    data = request.get_json(silent=True) or {}
    steps_data = data.get('steps', [])
    if not isinstance(steps_data, list) or not steps_data:
        return jsonify({"message": "No steps data provided"}), 400

    created_steps = []

    for step_info in steps_data:
        desc = step_info.get('description', '').strip()
        if not desc:
            continue

        date_str = step_info.get('date')
        date_val = None
        if date_str:
            try:
                date_val = parser.isoparse(date_str)
            except (ValueError, TypeError):
                date_val = None

        new_step = Step(
            goal_id=goal.id,
            title="Импорт IOS календарь",
            description=desc,
            date=date_val
        )
        db.session.add(new_step)
        db.session.flush()  # чтобы получить new_step.id до commit

        created_steps.append({
            "step_id": new_step.id,
            "title": new_step.title,
            "description": new_step.description,
            "date": date_val.isoformat() if date_val else None
        })

    db.session.commit()

    goal.update_progress()
    db.session.commit()

    return jsonify({
        "message": "Steps added successfully",
        "created_steps": created_steps
    }), 201

