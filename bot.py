import os
import telebot
import requests
import json
import random
import string
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from threading import Thread
from telebot import TeleBot, types
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

TOKEN = os.getenv('TOKEN')
WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN')
BITRIX24_URL = os.getenv('BITRIX24_URL')
CHAT_ID = os.getenv('CHAT_ID')
SMTP_PORT = os.getenv('SMTP_PORT')
SMTP_SRV = os.getenv('SMTP_SRV')
SMTP_USR = os.getenv('SMTP_USR')
SMTP_PSWD = os.getenv('SMTP_PSWD')
BITRIX_TASK_URL = os.getenv('BITRIX_TASK_URL') 

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

user_sessions = {}



def generate_verification_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

def send_verification_email(email, code):
    smtp_server = (SMTP_SRV)
    smtp_port = (SMTP_PORT)
    smtp_user = (SMTP_USR)
    smtp_password = (SMTP_PSWD)
    # Создаем сообщение
    message = MIMEMultipart()
    message["From"] = smtp_user
    message["To"] = email
    message["Subject"] = "Ваш уникальный код авторизации"
    
    # Здесь вы можете использовать любую кодировку, например "UTF-8"
    body = f"Ваш уникальный код авторизации: {code}"
    message.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(message)
    except Exception as e:
        print(f"Ошибка при отправке email: {e}")

def check_user_in_bitrix(email):
    url = BITRIX24_URL + 'user.get.json'
    params = {'FILTER[EMAIL]': email}
    response = requests.get(url, params=params)

    if response.status_code == 200:
        users = response.json().get("result", [])
        if users:
            user_data = users[0]
            
            # Проверка статуса пользователя
            if not user_data.get('ACTIVE'):
                return None, "access_denied"

            return user_data, None
    return None, None

def get_department_head(user_id):
    url = BITRIX24_URL + 'user.get.json'
    params = {'FILTER[ID]': user_id}
    response = requests.get(url, params=params)

    if response.status_code == 200:
        users = response.json().get("result", [])
        if users:
            user_data = users[0]
            department_id = user_data.get('UF_DEPARTMENT')
            if department_id:
                department_url = BITRIX24_URL + 'department.get.json'
                department_params = {'ID': department_id}
                department_response = requests.get(department_url, params=department_params)
                if department_response.status_code == 200:
                    departments = department_response.json().get("result", [])
                    if departments:
                        department_data = departments[0]
                        department_head_id = department_data.get('HEAD')
                        return department_head_id
    return None

def create_task(task_title, task_description, user_data, deadline):
    url = BITRIX24_URL + 'task.item.add.json'
    headers = {'Content-Type': 'application/json'}
    user_name = f"{user_data['NAME']} {user_data['LAST_NAME']} ({user_data['EMAIL']})"
    
    department_head_id = get_department_head(user_data['ID'])

    # Если постановщик задачи является руководителем отдела
    if user_data['ID'] == department_head_id:
        observers = [user_data['ID'], 25]
    else:
        observers = [user_data['ID'], department_head_id, 25]

    task_data = {
        "fields": {
            "TITLE": task_title,
            "DESCRIPTION": f"{task_description}\n\nПостановщик: {user_name}",
            "RESPONSIBLE_ID": 69,
            "CREATED_BY": 1985,  
            'GROUP_ID': 453,
            'AUDITORS': [obs for obs in observers if obs],
            'ACCOMPLICES': [1177],
            "DEADLINE": deadline,
        }
    }

    response = requests.post(url, headers=headers, json=task_data)

    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()
        
    return response.json()
    
def main_menu_markup(authenticated=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if not authenticated:
        markup.add(types.KeyboardButton("Авторизация"))
    else:
        markup.add(types.KeyboardButton("Создать задачу"))
    return markup

@bot.message_handler(commands=['start'])
def start_bot(message):
    bot.send_message(message.chat.id, "Добро пожаловать! Выберите действие:", reply_markup=main_menu_markup())

@bot.message_handler(func=lambda message: message.text == "Авторизация")
def auth_user(message):
    msg = bot.send_message(message.chat.id, "Введите ваш email для авторизации:")
    bot.register_next_step_handler(msg, process_email)

def process_email(message):
    email = message.text
    user_data, error = check_user_in_bitrix(email)

    if error == "access_denied":
        bot.send_message(message.from_user.id, "Ваша учетная запись в Битрикс24 заблокирована, доступ запрещен.")
        return

    if user_data:
        user_sessions[message.from_user.id] = {'email': email, 'user_data': user_data}

        verification_code = generate_verification_code()
        send_verification_email(email, verification_code)

        msg = bot.send_message(message.from_user.id, "Введите уникальный код, отправленный на вашу электронную почту:")
        user_sessions[message.from_user.id]['verification_code'] = verification_code
        bot.register_next_step_handler(msg, process_verification_code)
    else:
        bot.send_message(message.from_user.id, "Ошибка: Пользователь с таким email не найден в Битрикс24. Пожалуйста, проверьте ввод и попробуйте снова.")
        # Уберите эту строку, она не нужна, если сообщение отправляется:
         #bot.delete_message(message.chat.id, message.message_id)
        msg = bot.send_message(message.from_user.id, "Введите ваш email для авторизации:")
        bot.register_next_step_handler(msg, process_email)

def process_verification_code(message):
    user_id = message.from_user.id
    entered_code = message.text

    if user_id in user_sessions and entered_code == user_sessions[user_id].get('verification_code'):
        user_data = user_sessions[user_id]['user_data']
        bot.send_message(user_id, f"{user_data['NAME']} {user_data['LAST_NAME']} успешно авторизован.")
        
        bot.send_message(user_id, "Теперь выберите действие:", reply_markup=main_menu_markup(authenticated=True))
    else:
        bot.send_message(user_id, "Неверный код. Попробуйте снова.")
        msg = bot.send_message(user_id, "Введите ваш email для авторизации:")
        bot.register_next_step_handler(msg, process_email)

@bot.message_handler(func=lambda message: message.text == "Создать задачу")
def create_task_step1(message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        bot.send_message(user_id, "Сначала авторизуйтесь, чтобы создать задачу.")
    else:
        msg = bot.send_message(user_id, "Введите заголовок задачи:")
        bot.register_next_step_handler(msg, process_task_title)

def process_task_title(message):
    user_id = message.from_user.id
    task_title = message.text  
    user_sessions[user_id]['task_title'] = task_title  
    msg = bot.send_message(user_id, "Введите описание задачи:")
    bot.register_next_step_handler(msg, process_task_description)

def process_task_description(message):
    user_id = message.from_user.id
    task_description = message.text
    user_sessions[user_id]['task_description'] = task_description
    
    bot.send_message(user_id, "Выберите крайний срок задачи.", reply_markup=deadline_options_markup())
    
@bot.message_handler(func=lambda message: message.text == "Да")
def ask_deadline_options(message):
    user_id = message.from_user.id
    bot.send_message(user_id, "Выберите крайний срок:", reply_markup=deadline_options_markup())
def deadline_options_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    now = datetime.now()
    two_hours_later = now + timedelta(hours=2)

    today_deadline = two_hours_later.replace(hour=19, minute=0, second=0, microsecond=0)
    tomorrow_deadline = (two_hours_later + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
    
    if today_deadline < two_hours_later:
        today_deadline = two_hours_later

    markup.add(types.KeyboardButton(f"Сегодня {today_deadline.strftime('%H:%M')}"),
                types.KeyboardButton(f"Завтра {tomorrow_deadline.strftime('%H:%M')}"),
                types.KeyboardButton("Назначить вручную"))
    
    return markup
    
@bot.message_handler(func=lambda message: message.text in ["Сегодня 19:00", "Завтра 19:00"])
def process_predefined_deadline(message):
    user_id = message.from_user.id
    now = datetime.now()
    two_hours_later = now + timedelta(hours=2)

    if message.text.startswith("Сегодня"):
        deadline = (two_hours_later.replace(hour=19, minute=0, second=0, microsecond=0))
    else:
        deadline = ((two_hours_later + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0))

    user_sessions[user_id]['deadline'] = deadline.strftime('%Y-%m-%d %H:%M')
    create_task_and_notify(user_id)

@bot.message_handler(func=lambda message: message.text == "Назначить вручную")
def process_custom_deadline(message):
    user_id = message.from_user.id
    bot.send_message(user_id, "Введите дедлайн задачи в формате 'YYYY-MM-DD HH:mm':")
    bot.register_next_step_handler(message, process_task_deadline)

def process_task_deadline(message):
    user_id = message.from_user.id
    user_deadline = message.text

    # Проверить, что дедлайн не раньше, чем через 2 часа от текущего времени
    if datetime.strptime(user_deadline, '%Y-%m-%d %H:%M') < datetime.now() + timedelta(hours=2):
        bot.send_message(user_id, "Дедлайн не должен быть раньше, чем через 2 часа. Пожалуйста, введите снова:")
        bot.register_next_step_handler(message, process_task_deadline)
        return

    user_sessions[user_id]['deadline'] = user_deadline
    create_task_and_notify(user_id)

def create_task_and_notify(user_id):
    task_title = user_sessions[user_id]['task_title']
    task_description = user_sessions[user_id]['task_description']
    user_data = user_sessions[user_id]['user_data']
    user_deadline = user_sessions[user_id]['deadline']

    response = create_task(task_title, task_description, user_data, user_deadline)

if 'error' in response:
    bot.send_message(user_id, response['error'], reply_markup=main_menu_markup(authenticated=True))
elif response.get('result'):
    task_url = f'{BITRIX_TASK_URL}{response["result"]}/'
    bot.send_message(user_id, f"Задача создана: {task_url}", reply_markup=main_menu_markup(authenticated=True))
    bot.send_message(CHAT_ID, f"Создана задача: {task_url}")
else:
    bot.send_message(user_id, "Не удалось создать задачу. Пожалуйста, попробуйте позже.", reply_markup=main_menu_markup(authenticated=True))

if __name__ == "__main__":
    bot.polling(none_stop=True)

    
