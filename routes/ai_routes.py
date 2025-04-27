import json
import logging
from datetime import datetime, timedelta
from collections import Counter

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

import openai
from config.settings import OPENAI_API_KEY
from extensions import db
from models.goal_model import Goal
from models.step_model import Step
from models.user_model import User
from utils.color_utils import get_unique_pastel_color

logger = logging.getLogger(__name__)
ai_routes = Blueprint('ai_routes', __name__)

# Устанавливаем API-ключ OpenAI один раз
openai.api_key = OPENAI_API_KEY


def sanitize_gpt_response(response_text: str) -> str:
    """
    Удаляет обёртку markdown и любые строки, содержащие только 'json'.
    """
    lines = response_text.strip().splitlines()
    if lines and lines[0].strip().lower() == "json":
        lines = lines[1:]
    lines = [line for line in lines if not line.strip().startswith("```")]
    return "\n".join(lines).strip()


def get_user_day_load(user) -> dict:
    """
    Возвращает словарь вида { date: tasks_count }, где date — объект datetime.date,
    а tasks_count — число задач (steps), назначенных на этот день у данного пользователя.
    """
    steps = Step.query.join(Goal).filter(Goal.user_id == user.id).all()
    counts = Counter()
    for s in steps:
        if s.date:
            counts[s.date.date()] += 1
    return dict(counts)


def find_date_with_min_load(user, proposed_date: datetime.date, max_tasks_per_day=2) -> datetime.date:
    """
    Ищет ближайшую дату (начиная с proposed_date), где число задач < max_tasks_per_day.
    Сдвигается вперёд по одному дню, пока не найдёт достаточно свободный день.
    """
    day_load = get_user_day_load(user)
    candidate_date = proposed_date
    while day_load.get(candidate_date, 0) >= max_tasks_per_day:
        candidate_date += timedelta(days=1)
    return candidate_date


def find_next_free_date(user, proposed_date: datetime.date, exclude_task_id=None) -> datetime.date:
    """
    Ищет полностью свободную дату (без задач) для пользователя.
    exclude_task_id позволяет исключить текущую задачу из учёта.
    """
    query = Step.query.join(Goal).filter(Goal.user_id == user.id)
    if exclude_task_id:
        query = query.filter(Step.id != exclude_task_id)
    busy_dates = {step.date.date() for step in query.all() if step.date}
    candidate_date = proposed_date
    while candidate_date in busy_dates:
        candidate_date += timedelta(days=1)
    return candidate_date


@ai_routes.route('/ai/reschedule', methods=['POST'])
@jwt_required()
def reschedule_tasks():
    """
    Эндпоинт для переназначения дат задач с учетом запроса пользователя.
    1. Принимаем текст запроса (например, "Я буду занят с 1 по 20 апреля" или "Я буду занят 4 апреля").
    2. Через GPT парсим busy_start и busy_end (если не найдено, считаем, что завтра занят).
    3. Если задан диапазон (busy_start != busy_end), выбираем задачи, начиная с busy_start.
       Если указан один день (busy_start == busy_end), выбираем задачи в интервале [busy_start, busy_start+3 дня).
    4. Отправляем GPT системный промпт с требованием:
       - При диапазоне: никакие задачи не могут остаться в периоде [busy_start..busy_end],
         сохранить интервалы между задачами, и при совпадении дат сдвигать дату вперёд.
       - При одиночном запросе: задачи, назначенные на busy_start, нужно перенести на ближайшие свободные дни,
         учитывая задачи в ближайшие 2 дня.
       - Вернуть ТОЛЬКО JSON без комментариев.
    5. Сохраняем новые даты в БД.
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json() or {}
    problem = data.get("problem", "").strip()
    if not problem:
        return jsonify({"message": "Field 'problem' is required"}), 400

    today_date = datetime.today().date()

    # ЭТАП 1. Парсинг busy-периода
    try:
        parse_prompt = f"""ВНИМАНИЕ! Сегодня {today_date.isoformat()}.
        Проанализируй следующий запрос и выдели даты занятости в формате JSON:
        {{"busy_start": "YYYY-MM-DD", "busy_end": "YYYY-MM-DD"}}
        Если дат нет, верни null для обоих.
        Запрос: {problem}"""

        parse_response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": parse_prompt}],
            temperature=0,
            max_tokens=350
        )
        parse_message = parse_response.choices[0].message.content
        parse_message = sanitize_gpt_response(parse_message)
        busy_data = json.loads(parse_message)
        busy_start_str = busy_data.get("busy_start")
        busy_end_str = busy_data.get("busy_end")
        if busy_start_str and busy_end_str:
            busy_start = datetime.fromisoformat(busy_start_str).date()
            busy_end = datetime.fromisoformat(busy_end_str).date()
        else:
            busy_start = today_date + timedelta(days=1)
            busy_end = busy_start
    except Exception as e:
        logger.exception("Failed to parse busy period, fallback to 'tomorrow'")
        busy_start = today_date + timedelta(days=1)
        busy_end = busy_start

    # Определяем режим запроса: диапазон или один день
    if busy_start == busy_end:
        # Режим "одна дата": выбираем задачи только для периода [busy_start, busy_start+3 дня)
        end_date = busy_start + timedelta(days=3)
        tasks = Step.query.join(Goal).filter(
            Goal.user_id == user.id,
            db.func.date(Step.date) >= busy_start,
            db.func.date(Step.date) < end_date
        ).order_by(Step.date).all()
        single_date_mode = True
    else:
        # Режим диапазона: выбираем все задачи, начиная с busy_start
        tasks = Step.query.join(Goal).filter(
            Goal.user_id == user.id,
            db.func.date(Step.date) >= busy_start
        ).order_by(Step.date).all()
        single_date_mode = False

    if not tasks:
        return jsonify({
            "message": f"No tasks found for rescheduling starting from {busy_start.isoformat()}"
        }), 404

    tasks_info = []
    for t in tasks:
        tasks_info.append({
            "task_id": t.id,
            "title": t.title,
            "current_date": t.date.isoformat() if t.date else None
        })

    busy_duration = (busy_end - busy_start).days + 1
    if busy_duration < 1:
        busy_duration = 1

    # ЭТАП 3. Формирование промпта для GPT
    if single_date_mode:
        # Для одиночной даты уточняем, что переносим задачи только для указанного дня, с учётом ближайших 2 дней
        system_prompt = f"""ВНИМАНИЕ! Сегодня {today_date.isoformat()}.
У пользователя есть следующие задачи, запланированные на период с {busy_start.isoformat()} до {(busy_start + timedelta(days=2)).isoformat()}:
{json.dumps(tasks_info, ensure_ascii=False, indent=2)}

Пользователь занят {busy_start.isoformat()} (один день).
Требования:
1) Все задачи, назначенные на {busy_start.isoformat()}, должны быть перенесены на следующие ближайшие свободные дни.
   Учти, что для выбора оптимального свободного дня можно проанализировать также задачи, запланированные на следующие 2 дня.
2) Если новая дата совпадает с уже существующей задачей, сдвигай дату вперёд до первого свободного дня.
3) Верни ТОЛЬКО JSON формата:
{{
  "updates": [
    {{ "task_id": 123, "new_date": "YYYY-MM-DD" }},
    ...
  ]
}}
Без комментариев.
"""
    else:
        system_prompt = f"""ВНИМАНИЕ! Сегодня {today_date.isoformat()}.
У пользователя есть следующие задачи, начиная с {busy_start.isoformat()}:
{json.dumps(tasks_info, ensure_ascii=False, indent=2)}

Пользователь занят с {busy_start.isoformat()} по {busy_end.isoformat()} включительно.
Требования:
1) Ни одна задача НЕ может остаться внутри периода [{busy_start.isoformat()}..{busy_end.isoformat()}].
2) Всегда переноси задачи из периода [{busy_start.isoformat()}..{busy_end.isoformat()}] на последующие даты.
3) Сохраняй интервалы между задачами (если между ними было 5 дней, оставь эти 5 дней).
4) Если период занятости длится {busy_duration} дней, нельзя переносить всего на +1 день. Нужно освободить весь занятый период.
5) Если новая дата совпадает с уже существующей задачей, сдвигай дату вперёд, пока не будет свободной.
6) Верни ТОЛЬКО JSON формата:
{{
  "updates": [
    {{ "task_id": 123, "new_date": "YYYY-MM-DD" }},
    ...
  ]
}}
Без комментариев.
"""

    try:
        schedule_response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": ""}
            ],
            temperature=0,
            max_tokens=10000
        )
        schedule_message = schedule_response.choices[0].message.content
        schedule_message = sanitize_gpt_response(schedule_message)
    except Exception as e:
        logger.exception("OpenAI request for schedule generation failed")
        return jsonify({
            "message": "Failed to reach OpenAI for schedule generation",
            "error": str(e)
        }), 500

    try:
        schedule_data = json.loads(schedule_message)
    except Exception:
        return jsonify({
            "message": "OpenAI returned invalid JSON for schedule generation",
            "raw_response": schedule_message
        }), 500

    if "updates" not in schedule_data:
        return jsonify({
            "message": "AI response missing 'updates' field",
            "raw_response": schedule_message
        }), 500

    # ЭТАП 4. Применяем обновлённые даты
    updated_tasks = []
    for update in schedule_data["updates"]:
        task_id = update.get("task_id")
        new_date_str = update.get("new_date")
        try:
            new_date = datetime.fromisoformat(new_date_str)
        except Exception:
            new_date = None

        task = Step.query.get(task_id)
        if task and task.goal.user_id == user.id and new_date:
            corrected_date = find_next_free_date(user, new_date.date(), exclude_task_id=task.id)
            task.date = datetime.combine(corrected_date, datetime.min.time())
            updated_tasks.append({
                "task_id": task_id,

            })

    db.session.commit()

    return jsonify({
        "message": "Tasks rescheduled successfully",
        "updated_tasks": updated_tasks  # Теперь возвращается список объектов с task_id и new_date
    }), 200


@ai_routes.route('/ai/generate-goal', methods=['POST'])
@jwt_required()
def generate_goal():
    """
    Создание новой цели с шагами, равномерно распределяем шаги по дням,
    чтобы не перегружать один день.
    1) GPT генерирует goal_title и steps[] с датами.
    2) Проверяем загрузку: если день перегружен, сдвигаем шаг вперёд.
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json() or {}
    user_prompt = data.get('user_prompt', "").strip()
    if not user_prompt:
        return jsonify({"message": "user_prompt is required"}), 400

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is missing")
        return _create_goal_from_mock(user)

    today = datetime.today().strftime("%Y-%m-%d")
    day_load_dict = get_user_day_load(user)
    day_load_list = [{"date": d.isoformat(), "tasks_count": c}
                     for d, c in sorted(day_load_dict.items())]

    system_prompt = f"""
ВНИМАНИЕ: Сегодня {today}.
Ты — ассистент, который помогает разбивать цель пользователя на шаги по датам.

У пользователя уже есть задачи на некоторые даты. Ниже список (дата и количество задач):
{json.dumps(day_load_list, ensure_ascii=False, indent=2)}

Твоя задача:
1) Сгенерировать новую цель (объект с полем "goal_title").
2) goal_title максимальная выжимка из запроса пользовтеля, не больше трех слов, это словосочетание, которое описывает запрос.
3) Создать массив шагов (steps), где каждый шаг описан полями "title", "description", "date".
4) Пытайся сделать максимально подробное разбиение, если нужно используй больше шагов. Твоя задача направить пользовтеля.
5) Если в какой-то день уже 3 или более задач, старайся НЕ использовать эту дату — ищи менее загруженный день.
6) Если на какую-то дату стоит хотя бы одна задача, а ближайшие дни пусты, то ставь новый шаг на пустой день.
7) При разбиении цели на шаги учитывай логичную последовательность и устанавливай адекватные промежутки между датами — избегай слишком плотного или слишком растянутого графика. Почти никогда нельзя ставить шаги подряд! Лучше растянуть график шагов, нежели сбить в одну кучу!
8) Старайся избегать выходных дней. 
9) Обязательно ставь шаги на даты, которые стоят после текущей даты, можешь ставить первый шаг на текущую дату.
10) goal_title должен быть коротким и содержательным.
11) Формат даты: YYYY-MM-DD.
12) НЕЛЬЗЯ добавлять пояснения или текст вне JSON.
13) Верни результат СТРОГО в виде JSON, без комментариев, соблюдая следующую структуру:

{{
  "goal_title": "Пример цели",
  "steps": [
    {{
      "title": "Шаг один",
      "description": "Описание шага",
      "date": "2025-05-01"
    }},
    {{
      "title": "Шаг два",
      "description": "Описание шага",
      "date": "2025-05-10"
    }}
  ]
}}

Учитывай текст запроса пользователя:
{user_prompt}

Повторяю: никаких пояснений, только JSON по указанной структуре!
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt}
            ],
            temperature=0,
            max_tokens=2000
        )
        gpt_message = response.choices[0].message.content
        gpt_message = sanitize_gpt_response(gpt_message)
    except Exception as e:
        logger.exception("OpenAI request for generate-goal with free days failed")
        return jsonify({"message": "Failed to reach OpenAI", "error": str(e)}), 500

    try:
        ai_data = json.loads(gpt_message)
    except json.JSONDecodeError:
        return jsonify({
            "message": "OpenAI returned invalid JSON",
            "raw_response": gpt_message
        }), 500

    if "goal_title" not in ai_data or "steps" not in ai_data:
        return jsonify({
            "message": "AI response JSON missing required fields (goal_title, steps).",
            "raw_response": gpt_message
        }), 500

    return _create_goal_and_steps_from_ai(user, ai_data)



def _create_goal_and_steps_from_ai(user, ai_data):
    """
    Вспомогательная функция для сохранения новой цели и её шагов,
    с дополнительной проверкой загрузки дня. Если на день уже 2 задачи, сдвигаем шаг вперёд.
    """
    goal_title = ai_data.get("goal_title", "Новая цель")
    steps_data = ai_data.get("steps", [])

    user_goals = Goal.query.filter_by(user_id=user.id).all()
    used_colors = [g.color for g in user_goals if g.color]
    color = get_unique_pastel_color(used_colors) or "#D3D3D3"

    new_goal = Goal(
        user_id=user.id,
        title=goal_title,
        description="",
        color=color
    )
    db.session.add(new_goal)
    db.session.flush()

    MAX_TASKS_PER_DAY = 2

    for step_info in steps_data:
        raw_date = step_info.get("date")
        try:
            base_date = datetime.fromisoformat(raw_date).date() if raw_date else None
        except ValueError:
            base_date = None

        if base_date is None:
            base_date = datetime.today().date() + timedelta(days=1)

        correct_date = find_date_with_min_load(user, base_date, max_tasks_per_day=MAX_TASKS_PER_DAY)
        new_step = Step(
            goal_id=new_goal.id,
            title=step_info.get("title") or "Без названия",
            description=step_info.get("description") or "",
            date=datetime.combine(correct_date, datetime.min.time())
        )
        db.session.add(new_step)

    db.session.commit()

    new_goal.update_progress()
    db.session.commit()

    return jsonify({
        "message": "Goal created from AI suggestion with balanced scheduling",
        "goal_id": new_goal.id
    }), 201


def _create_goal_from_mock(user):
    """
    Если нет OPENAI_API_KEY, возвращаем тестовый пример.
    """
    mock_response = {
        "goal_title": "Построить дом мечты (mock)",
        "steps": [
            {
                "title": "Найти земельный участок (mock)",
                "description": "",
                "date": "2025-03-25"
            },
            {
                "title": "Разработать проект (mock)",
                "description": "",
                "date": "2025-04-01"
            }
        ]
    }
    return _create_goal_and_steps_from_ai(user, mock_response)
