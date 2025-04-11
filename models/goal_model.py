from extensions import db
from datetime import datetime
from models.step_model import Step

class Goal(db.Model):
    __tablename__ = 'goals'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(50), nullable=True)
    progress = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связь "один ко многим" с шагами
    steps = db.relationship('Step', backref='goal', cascade="all, delete", lazy=True)

    def __init__(self, user_id, title, description=None, color=None):
        self.user_id = user_id
        self.title = title
        self.description = description
        self.color = color

    def update_progress(self):
        """
        Пересчитывает прогресс в зависимости от выполненных шагов.
        Например:
          progress = (кол-во выполненных шагов / общее кол-во шагов) * 100
        """
        total_steps = len(self.steps)
        if total_steps == 0:
            self.progress = 0
        else:
            completed_steps = sum(1 for step in self.steps if step.status == 'done')
            self.progress = int((completed_steps / total_steps) * 100)
