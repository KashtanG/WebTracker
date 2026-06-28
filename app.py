import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from datetime import date, timedelta, datetime
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from flask_wtf.csrf import CSRFProtect
from models import db, User, Habit, Completion, Theme
from forms import RegistrationForm, LoginForm, HabitForm

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///habits.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-habit-tracker')

db.init_app(app)

csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к Routinery.'
login_manager.login_message_category = 'warning'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# Создание таблиц при запуске
with app.app_context():
    db.create_all()

@app.route('/')
@login_required
def index():
    form = HabitForm()
    habits = Habit.query.filter_by(user_id=current_user.id).order_by(
        Habit.is_pinned.desc(), 
        Habit.pinned_at.asc(), 
        Habit.created_at.desc()
    ).all()
    
    total_habits = len(habits)
    completed_today = sum(1 for h in habits if h.is_completed_today())
    completion_rate = round((completed_today / total_habits * 100), 1) if total_habits > 0 else 0
    
    days_of_week = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    months = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    
    today = date.today()
    day_name = days_of_week[today.weekday()]
    month_name = months[today.month - 1]
    formatted_date = f"{day_name}, {month_name} {today.day}, {today.year}"
    
    return render_template('index.html', 
                           habits=habits, 
                           form=form, 
                           total_habits=total_habits, 
                           completed_today=completed_today, 
                           completion_rate=completion_rate,
                           formatted_date=formatted_date)

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
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    today = date.today()

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

    if target_date > date.today():
        return "Нельзя отмечать привычки будущим числом", 400

    completion = Completion.query.filter_by(habit_id=habit_id, date=target_date).first()

    try:
        if completion:
            db.session.delete(completion)
        else:
            new_completion = Completion(habit_id=habit_id, date=target_date)
            db.session.add(new_completion)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return f"Ошибка при изменении статуса: {str(e)}", 500

    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify({
            'status': 'success',
            'completed': not completion,
            'date': date_str
        })

    return render_template('habit_item.html', habit=habit)

@app.route('/stats')
@login_required
def stats():
    habits = Habit.query.filter_by(user_id=current_user.id).order_by(
        Habit.is_pinned.desc(), 
        Habit.pinned_at.asc(), 
        Habit.created_at.desc()
    ).all()
    
    pie_data = {
        'labels': [h.name for h in habits],
        'percentages': [h.completion_percentage_30_days() for h in habits],
        'colors': [h.get_color() for h in habits]
    }
    
    return render_template('stats.html', habits=habits, pie_data=pie_data)

@app.route('/stats/calendar_data/<int:habit_id>')
@login_required
def calendar_data(habit_id):
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    completed_dates = [c.date.isoformat() for c in habit.completions]
    
    stats_data = {
        'last_7': habit.completions_in_last_days(7),
        'last_30': habit.completions_in_last_days(30),
        'streak': habit.current_streak(),
        'percentage': habit.completion_percentage_30_days()
    }
    
    return jsonify({
        'completed_dates': completed_dates,
        'color': habit.get_color(),
        'stats': stats_data
    })

# --- Раздел настроек ---

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    habits = Habit.query.filter_by(user_id=current_user.id).order_by(
        Habit.is_pinned.desc(), 
        Habit.pinned_at.asc(), 
        Habit.created_at.desc()
    ).all()
    
    user_themes = Theme.query.filter_by(user_id=current_user.id).order_by(Theme.created_at.desc()).all()
    
    if request.method == 'POST':
        theme_bg = request.form.get('theme_bg_color')
        theme_accent = request.form.get('theme_accent_color')
        
        if theme_bg and theme_accent:
            current_user.theme_bg_color = theme_bg
            current_user.theme_accent_color = theme_accent
            try:
                db.session.commit()
                flash('Оформление Routinery сохранено!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Ошибка сохранения: {str(e)}', 'danger')
            return redirect(url_for('settings'))
            
    return render_template('settings.html', habits=habits, user_themes=user_themes)

@app.route('/settings/apply_preset', methods=['POST'])
@login_required
def apply_preset():
    preset = request.form.get('preset')
    if preset == 'default':
        current_user.theme_bg_color = '#fbf3e4'
        current_user.theme_accent_color = '#a27bbc'
    elif preset == 'light':
        current_user.theme_bg_color = '#f8f9fa'
        current_user.theme_accent_color = '#2d3748'
    elif preset == 'dark':
        current_user.theme_bg_color = '#1e1e24'
        current_user.theme_accent_color = '#a29bfe'
        
    try:
        db.session.commit()
        flash('Предустановленная тема успешно применена!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
    return redirect(url_for('settings'))

@app.route('/settings/save_theme', methods=['POST'])
@login_required
def save_theme():
    theme_name = request.form.get('theme_name', '').strip()
    if not theme_name:
        flash('Пожалуйста, укажите название вашей темы.', 'danger')
        return redirect(url_for('settings'))
        
    try:
        new_theme = Theme(
            user_id=current_user.id,
            name=theme_name,
            bg_color=current_user.theme_bg_color,
            accent_color=current_user.theme_accent_color
        )
        db.session.add(new_theme)
        db.session.commit()
        flash(f'Ваша персональная тема "{theme_name}" успешно сохранена!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Не удалось сохранить тему: {str(e)}', 'danger')
    return redirect(url_for('settings'))

@app.route('/settings/apply_theme/<int:theme_id>', methods=['POST'])
@login_required
def apply_theme(theme_id):
    theme = Theme.query.filter_by(id=theme_id, user_id=current_user.id).first_or_404()
    current_user.theme_bg_color = theme.bg_color
    current_user.theme_accent_color = theme.accent_color
    try:
        db.session.commit()
        flash(f'Тема "{theme.name}" успешно применена!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка применения темы: {str(e)}', 'danger')
    return redirect(url_for('settings'))

@app.route('/settings/delete_theme/<int:theme_id>', methods=['POST'])
@login_required
def delete_theme(theme_id):
    theme = Theme.query.filter_by(id=theme_id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(theme)
        db.session.commit()
        flash(f'Персональная тема "{theme.name}" удалена.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка удаления: {str(e)}', 'danger')
    return redirect(url_for('settings'))

@app.route('/settings/toggle_pin/<int:habit_id>', methods=['POST'])
@login_required
def toggle_pin(habit_id):
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    habit.is_pinned = not habit.is_pinned
    
    if habit.is_pinned:
        habit.pinned_at = datetime.utcnow()
    else:
        habit.pinned_at = None
        
    try:
        db.session.commit()
        flash(f'Закрепление привычки "{habit.name}" обновлено.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
        
    return redirect(request.referrer or url_for('index'))

@app.route('/settings/set_color/<int:habit_id>', methods=['POST'])
@login_required
def set_habit_color(habit_id):
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    custom_color = request.form.get('custom_color')
    
    if custom_color:
        habit.custom_color = custom_color
        try:
            db.session.commit()
            flash(f'Для привычки "{habit.name}" успешно сохранен выбранный цвет.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {str(e)}', 'danger')
    return redirect(url_for('settings'))

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
        confirm_password = request.form.get('confirm_password', '')
        
        if not username or not email or not password or not confirm_password:
            flash('Пожалуйста, заполните все поля формы.', 'danger')
            return render_template('register.html', form=form)
            
        if password != confirm_password:
            flash('Введенные пароли не совпадают.', 'danger')
            return render_template('register.html', form=form)
            
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
    app.run(debug=True)