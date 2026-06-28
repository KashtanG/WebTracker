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
    
    # ИЗМЕНЕНО: Новые дефолтные значения палитры (молочно-бежевый #fbf3e4 и лавандовый #a27bbc)
    theme_bg_color = db.Column(db.String(7), default='#fbf3e4', nullable=False)
    theme_accent_color = db.Column(db.String(7), default='#a27bbc', nullable=False)
    
    habits = db.relationship('Habit', backref='user', lazy=True, cascade="all, delete-orphan")
    custom_themes = db.relationship('Theme', backref='user', lazy=True, cascade="all, delete-orphan")

    def is_dark_theme(self):
        """Вычисляет относительную яркость фона пользователя по формуле YIQ, определяя темную тему."""
        hex_color = self.theme_bg_color.lstrip('#')
        if len(hex_color) == 6:
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                return brightness < 125  
            except ValueError:
                pass
        return False

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


class Theme(db.Model):
    """Таблица для сохранения персональных пользовательских тем."""
    __tablename__ = 'themes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    bg_color = db.Column(db.String(7), nullable=False)
    accent_color = db.Column(db.String(7), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Habit(db.Model):
    __tablename__ = 'habits'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    pinned_at = db.Column(db.DateTime, nullable=True)
    custom_color = db.Column(db.String(7), nullable=True)
    
    completions = db.relationship('Completion', backref='habit', lazy=True, cascade="all, delete-orphan")

    def get_color(self):
        if self.custom_color:
            return self.custom_color
        colors = ['#e76f51', '#ffb5a7', '#8ab17d', '#457b9d', '#f4a261', '#fcd5ce', '#2a9d8f', '#a8dadc', '#b5179e', '#9b5de5']
        return colors[self.id % len(colors)]

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
            'is_pinned': self.is_pinned,
            'color': self.get_color(),
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