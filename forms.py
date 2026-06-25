from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[
        DataRequired(message='Поле обязательно для заполнения.')
    ])
    email = StringField('Email адрес', validators=[
        DataRequired(message='Поле обязательно для заполнения.'),
        Email(message='Некорректный формат адреса электронной почты.')
    ])
    password = PasswordField('Пароль', validators=[
        DataRequired(message='Поле обязательно для заполнения.')
    ])
    confirm_password = PasswordField('Подтверждение пароля', validators=[
        DataRequired(message='Поле обязательно для заполнения.'),
        EqualTo('password', message='Введенные пароли должны совпадать.')
    ])
    submit = SubmitField('Создать аккаунт')


class LoginForm(FlaskForm):
    email = StringField('Email адрес', validators=[
        DataRequired(message='Поле обязательно для заполнения.'),
        Email(message='Некорректный формат адреса электронной почты.')
    ])
    password = PasswordField('Пароль', validators=[
        DataRequired(message='Поле обязательно для заполнения.')
    ])
    submit = SubmitField('Войти')


class HabitForm(FlaskForm):
    name = StringField('Название привычки', validators=[
        DataRequired(message='Поле обязательно для заполнения.')
    ])
    submit = SubmitField('Добавить')