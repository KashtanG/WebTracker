from datetime import datetime, date, timedelta
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Связь с таблицей Habit (при удалении пользователя удалятся и его привычки)
    habits = db.relationship('Habit', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


class Habit(db.Model):
    __tablename__ = 'habits'
    
    id = db.Column(db.Integer, primary_key=True)
    # Внешний ключ, связывающий привычку с конкретным пользователем
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(120), nullable=False)  # Снято ограничение глобальной уникальности
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    completions = db.relationship('Completion', backref='habit', lazy=True, cascade="all, delete-orphan")

    def is_completed_today(self):
        today = date.today()
        return any(c.date == today for c in self.completions)

    def total_completions(self):
        return len(self.completions)

    def current_streak(self):
        completion_dates = {c.date for c in self.completions}
        if not completion_dates:
            return 0

        today = date.today()
        yesterday = today - timedelta(days=1)

        if today in completion_dates:
            current_date = today
        elif yesterday in completion_dates:
            current_date = yesterday
        else:
            return 0

        streak = 0
        while current_date in completion_dates:
            streak += 1
            current_date -= timedelta(days=1)
            
        return streak

    def completions_in_last_days(self, days_count):
        today = date.today()
        start_date = today - timedelta(days=days_count - 1)
        return sum(1 for c in self.completions if start_date <= c.date <= today)

    def completion_percentage_30_days(self):
        count = self.completions_in_last_days(30)
        return round((count / 30) * 100, 1)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Completion(db.Model):
    __tablename__ = 'completions'
    
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habits.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'habit_id': self.habit_id,
            'date': self.date.isoformat() if self.date else None
        }