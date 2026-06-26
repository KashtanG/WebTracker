import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from datetime import date, timedelta
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from flask_wtf.csrf import CSRFProtect
from models import db, User, Habit, Completion
from forms import RegistrationForm, LoginForm, HabitForm

app = Flask(__name__)

# Чтение DATABASE_URL из переменной окружения Render (по умолчанию SQLite)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///habits.db')

# Фикс для старого формата URL у баз данных PostgreSQL на Render/Heroku
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Стабильный секретный ключ из переменных окружения для корректной работы Gunicorn
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-secure-key-12345')

# Инициализация БД
db.init_app(app)

# Инициализация глобальной защиты от CSRF-атак
csrf = CSRFProtect(app)

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к трекеру.'
login_manager.login_message_category = 'warning'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Включаем поддержку Foreign Key каскадов ТОЛЬКО для SQLite
# Для PostgreSQL это не требуется, так как в ней внешние ключи включены по умолчанию
if database_url.startswith("sqlite"):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Создание таблиц при запуске приложения (работает и на SQLite, и на PostgreSQL)
with app.app_context():
    db.create_all()

@app.route('/')
@login_required
def index():
    form = HabitForm()
    habits = Habit.query.filter_by(user_id=current_user.id).order_by(Habit.created_at.desc()).all()
    return render_template('index.html', habits=habits, form=form)

@app.route('/add', methods=['POST'])
@login_required
def add_habit():
    form = HabitForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        
        existing = Habit.query.filter_by(user_id=current_user.id, name=name).first()
        if existing:
            return "Такая привычка уже добавлена", 400

        try:
            new_habit = Habit(name=name, user_id=current_user.id)
            db.session.add(new_habit)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Ошибка сервера: {str(e)}", 500

        return render_template('habit_item.html', habit=new_habit)
    else:
        errors = ", ".join([f"{field}: {', '.join(errs)}" for field, errs in form.errors.items()])
        return f"Ошибка валидации: {errors}", 400

@app.route('/delete/<int:habit_id>', methods=['DELETE'])
@login_required
def delete_habit(habit_id):
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(habit)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return f"Ошибка при удалении: {str(e)}", 500

    return "", 200

@app.route('/toggle/<int:habit_id>', methods=['POST'])
@login_required
def toggle_habit(habit_id):
    # Безопасная выборка: только привычки текущего пользователя
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    
    # Считываем дату (поддерживаем и классическую HTML-форму, и JSON-тело от календаря)
    date_str = None
    if request.is_json:
        json_data = request.get_json(silent=True)
        if json_data:
            date_str = json_data.get('date')
    else:
        date_str = request.form.get('date')

    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return "Неверный формат даты", 400
    else:
        target_date = date.today()

    # Запрещаем отмечать привычки будущим числом
    if target_date > date.today():
        return "Нельзя отмечать привычки будущим числом", 400

    completion = Completion.query.filter_by(habit_id=habit_id, date=target_date).first()

    try:
        if completion:
            # Если отметка за эту дату уже была — удаляем её
            db.session.delete(completion)
        else:
            # Если отметки не было — создаем новую
            new_completion = Completion(habit_id=habit_id, date=target_date)
            db.session.add(new_completion)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return f"Ошибка при изменении статуса: {str(e)}", 500

    # Если запрос пришел в формате JSON (из нашего календаря в статистике)
    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify({
            'status': 'success',
            'completed': not completion,
            'date': date_str
        })

    # Обычный HTMX-запрос с главной страницы (возвращает фрагмент li)
    return render_template('habit_item.html', habit=habit)

@app.route('/stats')
@login_required
def stats():
    # Сортируем привычки по названию для таблицы
    habits = Habit.query.filter_by(user_id=current_user.id).order_by(Habit.name).all()
    
    # Подготовка данных для круговой диаграммы (включая список ID)
    pie_data = {
        'labels': [h.name for h in habits],
        'percentages': [h.completion_percentage_30_days() for h in habits],
        'ids': [h.id for h in habits]  # Добавили ID для сопоставления цветов
    }
    
    return render_template('stats.html', habits=habits, pie_data=pie_data)

# Замените старый маршрут /stats/chart_data на следующий:
@app.route('/stats/calendar_data/<int:habit_id>')
@login_required
def calendar_data(habit_id):
    # Безопасная выборка только для привычек текущего пользователя
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    
    # Извлекаем все даты выполнения привычки в формате ISO (ГГГГ-ММ-ДД)
    completed_dates = [c.date.isoformat() for c in habit.completions]
    
    # Единая палитра цветов
    colors = ['#0d6efd', '#198754', '#0dcaf0', '#ffc107', '#dc3545', '#6610f2', '#6f42c1', '#d63384', '#fd7e14', '#20c997']
    color = colors[habit.id % len(colors)]
    
    return jsonify({
        'completed_dates': completed_dates,
        'color': color
    })

# --- Маршруты авторизации ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = RegistrationForm()
    
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip()
        password = form.password.data
        
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Пользователь с таким email уже зарегистрирован.', 'danger')
            return render_template('register.html', form=form)
            
        existing_username = User.query.filter_by(username=username).first()
        if existing_username:
            flash('Имя пользователя уже занято.', 'danger')
            return render_template('register.html', form=form)
            
        try:
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            login_user(new_user)
            flash('Регистрация прошла успешно! Добро пожаловать.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при регистрации: {str(e)}', 'danger')
            
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = LoginForm()
    
    if form.validate_on_submit():
        email = form.email.data.strip()
        password = form.password.data
        
        user = User.query.filter_by(email=email).first()
        
        if user is None or not user.check_password(password):
            flash('Неверный адрес электронной почты или пароль.', 'danger')
            return render_template('login.html', form=form)
            
        login_user(user)
        flash('Вы успешно вошли в систему.', 'success')
        return redirect(url_for('index'))
        
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=False)