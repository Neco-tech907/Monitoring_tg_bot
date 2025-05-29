import os
from io import BytesIO
import re
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from dotenv import load_dotenv
import paramiko
import psycopg2
from psycopg2 import Error

# Загружаем переменные окружения из .env
load_dotenv()
TOKEN = os.getenv("TOKEN")
RM_HOST = os.getenv("RM_HOST")
RM_USER = os.getenv("RM_USER")
RM_PASSWORD = os.getenv("RM_PASSWORD")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_DATABASE = os.getenv("DB_DATABASE")


# Функция для подключения к базе данных
def db_connect():
    try:
        connection = psycopg2.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_DATABASE
        )
	 # Проверка существования таблиц
        cursor = connection.cursor()
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'emails')")
        emails_table_exists = cursor.fetchone()[0]
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'phone_numbers')")
        phones_table_exists = cursor.fetchone()[0]
        cursor.close()
        
        if not emails_table_exists or not phones_table_exists:
            raise Exception("Одна или обе таблицы (emails, phone_numbers) не существуют")
            
        logging.info("✅ Подключение к базе данных %s успешно", DB_DATABASE)
        return connection
    except Error as e:
        logging.error("❌ Ошибка подключения к базе данных: %s", str(e))
        raise Exception(f"Ошибка подключения к базе данных: {str(e)}")

# Настройка логирования
handler = logging.FileHandler("monitoring_bot.log", encoding="utf-8")
logging.basicConfig(handlers=[handler], level=logging.INFO)
# Загрузка токена
TOKEN = os.getenv("TOKEN")

# Определение состояний для ConversationHandler
FIND_EMAIL, FIND_PHONE, VERIFY_PASSWORD, SAVE_EMAIL, SAVE_PHONE = range(5)


# Функция для команды /start
def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Привет! Я бот для мониторинга и работы с базой данных. Используйте команды из меню.")
    logging.info("🚀 Пользователь %s вызвал /start", update.effective_user.username)

# Обработчик команды /find_email
def handle_find_email(update: Update, context: CallbackContext):
    update.message.reply_text("📧 Введите текст для поиска email-адресов:")
    logging.info("📧 Пользователь %s вызвал /find_email", update.effective_user.username)
    return FIND_EMAIL

# Обработчик текста для поиска email
def find_email(update: Update, context: CallbackContext):
    text = update.message.text
    logging.info("📧 Пользователь %s ввёл текст для поиска email: %s", update.effective_user.username, text)
    
    # Регулярное выражение для поиска email
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)

    if not emails:
        update.message.reply_text("📭 Email-адреса не найдены в тексте.")
        logging.info("📭 Email-адреса не найдены для пользователя %s", update.effective_user.username)
        return ConversationHandler.END

    # Сохраняем найденные email в контексте
    context.user_data['emails'] = emails
    output = "\n".join(emails)
    update.message.reply_text(f"📧 Найденные email-адреса:\n{output}\n\nХотите записать их в базу данных? Ответьте 'Да' или 'Нет'.")
    logging.info("✅ Найдено %d email-адресов для пользователя %s", len(emails), update.effective_user.username)
    return SAVE_EMAIL

# Обработчик подтверждения записи email
def save_email(update: Update, context: CallbackContext):
    response = update.message.text.lower()
    username = update.effective_user.username
    emails = context.user_data.get('emails', [])

    if response == 'да':
        try:
            connection = db_connect()
            cursor = connection.cursor()
            inserted_count = 0
            for email in emails:
                # Проверяем, существует ли email в базе
                cursor.execute("SELECT email FROM emails WHERE email = %s", (email,))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO emails (email) VALUES (%s)", (email,))
                    inserted_count += 1
            connection.commit()
            cursor.close()
            connection.close()
            if inserted_count > 0:
                update.message.reply_text(f"✅ {inserted_count} email-адреса успешно записаны в базу данных!")
                logging.info("✅ Пользователь %s записал %d email-адресов в базу данных", username, inserted_count)
            else:
                update.message.reply_text("ℹ️ Все email-адреса уже есть в базе данных.")
                logging.info("ℹ️ Пользователь %s: все email-адреса уже существуют", username)
        except Exception as e:
            update.message.reply_text(f"❌ Ошибка при записи email-адресов: {str(e)}")
            logging.error("❌ Ошибка при записи email-адресов для пользователя %s: %s", username, str(e))
    elif response == 'нет':
        update.message.reply_text("🚫 Запись email-адресов отменена.")
        logging.info("🚫 Пользователь %s отказался от записи email-адресов", username)
    else:
        update.message.reply_text("❓ Пожалуйста, ответьте 'Да' или 'Нет'.")
        return SAVE_EMAIL

    # Очищаем данные и завершаем диалог
    context.user_data.clear()
    return ConversationHandler.END

# Обработчик команды /find_phone_number
def handle_find_phone_number(update: Update, context: CallbackContext):
    update.message.reply_text("📞 Введите текст для поиска номеров телефонов:")
    logging.info("📞 Пользователь %s вызвал /find_phone_number", update.effective_user.username)
    return FIND_PHONE

# Обработчик текста для поиска номеров телефонов
def find_phone_number(update: Update, context: CallbackContext):
    text = update.message.text
    logging.info("📞 Пользователь %s ввёл текст для поиска номеров телефонов: %s", update.effective_user.username, text)
    
    # Регулярное выражение для поиска номеров телефонов
    phone_pattern = r'(\+?\d{1,2}\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}|\d{3}\s?\d{3}\s?\d{2}\s?\d{2}|\d{10})'
    phones = re.findall(phone_pattern, text)

    if not phones:
        update.message.reply_text("📭 Номера телефонов не найдены в тексте.")
        logging.info("📭 Номера телефонов не найдены для пользователя %s", update.effective_user.username)
        return ConversationHandler.END

    # Сохраняем найденные номера в контексте
    context.user_data['phones'] = phones
    output = "\n".join(phones)
    update.message.reply_text(f"📞 Найденные номера телефонов:\n{output}\n\nХотите записать их в базу данных? Ответьте 'Да' или 'Нет'.")
    logging.info("✅ Найдено %d номеров телефонов для пользователя %s", len(phones), update.effective_user.username)
    return SAVE_PHONE

# Обработчик подтверждения записи номеров телефонов
def save_phone(update: Update, context: CallbackContext):
    response = update.message.text.lower()
    username = update.effective_user.username
    phones = context.user_data.get('phones', [])

    if response == 'да':
        try:
            connection = db_connect()
            cursor = connection.cursor()
            inserted_count = 0
            for phone in phones:
                # Проверяем, существует ли номер телефона в базе
                cursor.execute("SELECT phone_number FROM phone_numbers WHERE phone_number = %s", (phone,))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO phone_numbers (phone_number) VALUES (%s)", (phone,))
                    inserted_count += 1
            connection.commit()
            cursor.close()
            connection.close()
            if inserted_count > 0:
                update.message.reply_text(f"✅ {inserted_count} номеров телефонов успешно записаны в базу данных!")
                logging.info("✅ Пользователь %s записал %d номеров телефонов в базу данных", username, inserted_count)
            else:
                update.message.reply_text("ℹ️ Все номера телефонов уже есть в базе данных.")
                logging.info("ℹ️ Пользователь %s: все номера телефонов уже существуют", username)
        except Exception as e:
            update.message.reply_text(f"❌ Ошибка при записи номеров телефонов: {str(e)}")
            logging.error("❌ Ошибка при записи номеров телефонов для пользователя %s: %s", username, str(e))
    elif response == 'нет':
        update.message.reply_text("🚫 Запись номеров телефонов отменена.")
        logging.info("🚫 Пользователь %s отказался от записи номеров телефонов", username)
    else:
        update.message.reply_text("❓ Пожалуйста, ответьте 'Да' или 'Нет'.")
        return SAVE_PHONE

    # Очищаем данные и завершаем диалог
    context.user_data.clear()
    return ConversationHandler.END

# Функции get_emails и get_phone_numbers
def get_emails(update: Update, context: CallbackContext):
    logging.info("📧 Пользователь %s вызвал /get_emails", update.effective_user.username)
    
    try:
        connection = db_connect()
        cursor = connection.cursor()
        cursor.execute("SELECT id, email FROM emails")
        emails = cursor.fetchall()
        cursor.close()
        connection.close()

        if not emails:
            update.message.reply_text("📭 Email-адреса не найдены в базе данных.")
            logging.info("📭 Email-адреса не найдены для пользователя %s", update.effective_user.username)
            return

        email_list = [f"{email[0]}: {email[1]}" for email in emails]
        output = "\n".join(email_list)

        if len(output) > 4000:
            file = BytesIO()
            file.write(output.encode())
            file.seek(0)
            update.message.reply_document(document=file, filename="emails.txt")
            logging.info("✅ Email-адреса отправлены как файл для пользователя %s", update.effective_user.username)
        else:
            update.message.reply_text(f"📧 Найденные email-адреса:\n{output}")
            logging.info("✅ Email-адреса отправлены текстом для пользователя %s", update.effective_user.username)

    except Exception as e:
        logging.error("❌ Ошибка при получении email-адресов: %s", str(e))
        update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")

def get_phone_numbers(update: Update, context: CallbackContext):
    logging.info("📞 Пользователь %s вызвал /get_phone_numbers", update.effective_user.username)
    
    try:
        connection = db_connect()
        cursor = connection.cursor()
        cursor.execute("SELECT id, phone_number FROM phone_numbers")
        phones = cursor.fetchall()
        cursor.close()
        connection.close()

        if not phones:
            update.message.reply_text("📭 Номера телефонов не найдены в базе данных.")
            logging.info("📭 Номера телефонов не найдены для пользователя %s", update.effective_user.username)
            return

        phone_list = [f"{phone[0]}: {phone[1]}" for phone in phones]
        output = "\n".join(phone_list)

        if len(output) > 4000:
            file = BytesIO()
            file.write(output.encode())
            file.seek(0)
            update.message.reply_document(document=file, filename="phone_numbers.txt")
            logging.info("✅ Номера телефонов отправлены как файл для пользователя %s", update.effective_user.username)
        else:
            update.message.reply_text(f"📞 Найденные номера телефонов:\n{output}")
            logging.info("✅ Номера телефонов отправлены текстом для пользователя %s", update.effective_user.username)

    except Exception as e:
        logging.error("❌ Ошибка при получении номеров телефонов: %s", str(e))
        update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")


# Функция для проверки сложности пароля
def verify_password(update: Update, context: CallbackContext):
    password = update.message.text  # Получаем сообщение пользователя
    logging.info("Пользователь %s проверяет пароль на сложность", update.effective_user.username)
    
    if re.search(r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$', password):
        update.message.reply_text("Пароль соответствует всем требованиям сложности!")
    else:
        update.message.reply_text("Пароль не соответствует требованиям сложности. Он должен содержать минимум 8 символов, включая заглавные и строчные буквы, цифры и специальные символы.")
    return ConversationHandler.END

# Инициализация SSH-клиента
def ssh_connect():
    logging.info("Устанавливается SSH-соединение с %s от имени пользователя %s", RM_HOST, RM_USER)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(RM_HOST, username=RM_USER, password=RM_PASSWORD)
    return ssh

# Команда для получения информации о релизе
def get_release(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_release", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("lsb_release -a")
    output = stdout.read().decode()
    update.message.reply_text(f"Информация о релизе:\n{output}")
    ssh.close()

# Команда для получения информации о времени работы системы
def get_uptime(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_uptime", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("uptime")
    output = stdout.read().decode()
    update.message.reply_text(f"Время работы системы:\n{output}")
    ssh.close()

# Команда для получения информации о состоянии дисков
def get_df(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_df", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("df -h")
    output = stdout.read().decode()
    update.message.reply_text(f"Информация о файловой системе:\n{output}")
    ssh.close()

# Команда для получения информации о системе
def get_uname(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_uname", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("uname -a")
    output = stdout.read().decode()
    update.message.reply_text(f"Информация о системе:\n{output}")
    ssh.close()

# Команда для получения информации о состоянии оперативной памяти
def get_free(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_free", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("free -h")
    output = stdout.read().decode()
    update.message.reply_text(f"Информация о памяти:\n{output}")
    ssh.close()

# Команда для получения информации о производительности системы
def get_mpstat(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_mpstat", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("mpstat")
    output = stdout.read().decode()
    update.message.reply_text(f"Информация о производительности:\n{output}")
    ssh.close()

# Команда для получения списка запущенных процессов
def get_ps(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_ps", update.effective_user.username)
    
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("ps aux")
    output = stdout.read().decode()
    ssh.close()

    # Проверка длины вывода до отправки
    if len(output) > 4000:
        file = BytesIO()
        file.write(output.encode())
        file.seek(0)
        update.message.reply_document(document=file, filename="ps_output.txt")
    else:
        update.message.reply_text(f"Список процессов:\n{output}")

# Команда для получения информации о пользователях
def get_w(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_w", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("w")
    output = stdout.read().decode()
    update.message.reply_text(f"Список пользователей:\n{output}")
    ssh.close()

# Команда для получения логов (последние 10 входов в систему)
def get_auths(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_auths", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("last -n 10")
    output = stdout.read().decode()
    update.message.reply_text(f"Последние 10 входов:\n{output}")
    ssh.close()

# Команда для получения последних 5 критических событий
def get_critical(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_critical", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("journalctl -p 3 -n 5")
    output = stdout.read().decode()
    update.message.reply_text(f"Последние 5 критических событий:\n{output}")
    ssh.close()

# Команда для получения информации об используемых портах
def get_ss(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_ss", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("ss -tuln")
    output = stdout.read().decode()
    update.message.reply_text(f"Информация об используемых портах:\n{output}")
    ssh.close()

# Команда для получения информации об установленных пакетах
def get_apt_list(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_apt_list", update.effective_user.username)
    
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("apt list --installed")
    output = stdout.read().decode()
    ssh.close()

    # Проверка длины вывода
    if len(output) > 4000:
        file = BytesIO()
        file.write(output.encode())
        file.seek(0)
        update.message.reply_document(document=file, filename="apt_list.txt")
    else:
        update.message.reply_text(f"Список установленных пакетов:\n{output}")

# Команда для получения информации о запущенных сервисах
def get_services(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_services", update.effective_user.username)
    ssh = ssh_connect()
    stdin, stdout, stderr = ssh.exec_command("systemctl list-units --type=service --state=running")
    output = stdout.read().decode()
    update.message.reply_text(f"Запущенные сервисы:\n{output}")
    ssh.close()

# Команда для разрыва SSH-соединения
def disconnect_ssh(update: Update, context: CallbackContext):
    logging.info("Пользователь %s разорвал SSH-соединение", update.effective_user.username)
    update.message.reply_text("Соединение с сервером разорвано.")
    return ConversationHandler.END


# Функции для обработки текстовых сообщений
def start(update: Update, context: CallbackContext):
    logging.info("Пользователь %s начал сессию через /start", update.effective_user.username)
    update.message.reply_text("Привет! Я могу помочь вам с различными задачами. Используйте команду /find_email, /find_phone_number или /verify_password.")
    return ConversationHandler.END

def handle_find_email(update: Update, context: CallbackContext):
    update.message.reply_text("Введите текст для поиска email-адресов:")
    return FIND_EMAIL

def handle_find_phone_number(update: Update, context: CallbackContext):
    update.message.reply_text("Введите текст для поиска номеров телефонов:")
    return FIND_PHONE

def handle_verify_password(update: Update, context: CallbackContext):
    update.message.reply_text("Введите пароль для проверки его сложности:")
    return VERIFY_PASSWORD






# Команда для получения логов репликации
def get_repl_logs(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_repl_logs", update.effective_user.username)
    
    try:
        ssh = ssh_connect()
        # Команда для чтения логов PostgreSQL и фильтрации строк, связанных с репликацией
        command = "grep -i 'replication\\|wal\\|streaming' /var/log/postgresql/postgresql.log | tail -n 50"
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        ssh.close()

        if error:
            update.message.reply_text(f"Ошибка при получении логов: {error}")
            return

        if not output:
            update.message.reply_text("Логи репликации не найдены или пусты.")
            return

        # Проверка длины вывода
        if len(output) > 4000:
            file = BytesIO()
            file.write(output.encode())
            file.seek(0)
            update.message.reply_document(document=file, filename="replication_logs.txt")
        else:
            update.message.reply_text(f"Логи репликации (последние 50 строк):\n{output}")

    except Exception as e:
        logging.error("Ошибка при получении логов репликации: %s", str(e))
        update.message.reply_text(f"Произошла ошибка: {str(e)}")
#-------------------------------------------------------------------


# Команда для получения email-адресов
def get_emails(update: Update, context: CallbackContext):
    logging.info("📧 Пользователь %s вызвал /get_emails", update.effective_user.username)
    
    try:
        connection = db_connect()
        cursor = connection.cursor()
        # Выбираем id и email из таблицы emails
        cursor.execute("SELECT id, email FROM emails")
        emails = cursor.fetchall()
        cursor.close()
        connection.close()

        if not emails:
            update.message.reply_text("📭 Email-адреса не найдены в базе данных.")
            logging.info("📭 Email-адреса не найдены для пользователя %s", update.effective_user.username)
            return

        # Формируем список email-адресов с id
        email_list = [f"{email[0]}: {email[1]}" for email in emails]
        output = "\n".join(email_list)

        # Проверка длины вывода
        if len(output) > 4000:
            file = BytesIO()
            file.write(output.encode())
            file.seek(0)
            update.message.reply_document(document=file, filename="emails.txt")
            logging.info("✅ Email-адреса отправлены как файл для пользователя %s", update.effective_user.username)
        else:
            update.message.reply_text(f"📧 Найденные email-адреса:\n{output}")
            logging.info("✅ Email-адреса отправлены текстом для пользователя %s", update.effective_user.username)

    except Exception as e:
        logging.error("❌ Ошибка при получении email-адресов: %s", str(e))
        update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")



# Команда для получения номеров телефонов
def get_phone_numbers(update: Update, context: CallbackContext):
    logging.info("📞 Пользователь %s вызвал /get_phone_numbers", update.effective_user.username)
    
    try:
        connection = db_connect()
        cursor = connection.cursor()
        # Выбираем id и phone_number из таблицы phone_numbers
        cursor.execute("SELECT id, phone_number FROM phone_numbers")
        phones = cursor.fetchall()
        cursor.close()
        connection.close()

        if not phones:
            update.message.reply_text("📭 Номера телефонов не найдены в базе данных.")
            logging.info("📭 Номера телефонов не найдены для пользователя %s", update.effective_user.username)
            return

        # Формируем список номеров телефонов с id
        phone_list = [f"{phone[0]}: {phone[1]}" for phone in phones]
        output = "\n".join(phone_list)

        # Проверка длины вывода
        if len(output) > 4000:
            file = BytesIO()
            file.write(output.encode())
            file.seek(0)
            update.message.reply_document(document=file, filename="phone_numbers.txt")
            logging.info("✅ Номера телефонов отправлены как файл для пользователя %s", update.effective_user.username)
        else:
            update.message.reply_text(f"📞 Найденные номера телефонов:\n{output}")
            logging.info("✅ Номера телефонов отправлены текстом для пользователя %s", update.effective_user.username)

    except Exception as e:
        logging.error("❌ Ошибка при получении номеров телефонов: %s", str(e))
        update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")





# Настройка ConversationHandler
def main():
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Обработчик состояний
    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
	    FIND_EMAIL: [MessageHandler(Filters.text & ~Filters.command, find_email)],
            FIND_PHONE: [MessageHandler(Filters.text & ~Filters.command, find_phone_number)],
            VERIFY_PASSWORD: [MessageHandler(Filters.text & ~Filters.command, verify_password)],
            SAVE_EMAIL: [MessageHandler(Filters.text & ~Filters.command, save_email)],
            SAVE_PHONE: [MessageHandler(Filters.text & ~Filters.command, save_phone)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Добавляем обработчики
    dispatcher.add_handler(conversation_handler)
    dispatcher.add_handler(CommandHandler("get_release", get_release))
    dispatcher.add_handler(CommandHandler("get_uptime", get_uptime))
    dispatcher.add_handler(CommandHandler("get_df", get_df))

    updater.start_polling()
    updater.idle()

def set_bot_commands(updater):
    updater.bot.set_my_commands([
        ('start', 'Приветственное сообщение'),
        ('find_email', 'Поиск email-адресов 📧'),
        ('find_phone_number', 'Поиск номеров телефонов 📞'),
        ('verify_password', 'Проверка пароля на сложность'),
        ('get_release', 'Информация о релизе системы'),
        ('get_uptime', 'Информация о времени работы системы'),
        ('get_df', 'Информация о файловой системе'),
        ('get_uname', 'Информация о системе'),
        ('get_free', 'Информация о памяти'),
        ('get_mpstat', 'Информация о производительности системы'),
        ('get_ps', 'Список процессов'),
        ('get_w', 'Список пользователей'),
        ('get_auths', 'Последние 10 входов в систему'),
        ('get_critical', 'Последние 5 критических событий'),
        ('get_ss', 'Информация об используемых портах'),
        ('get_apt_list', 'Информация об установленных пакетах'),
        ('get_services', 'Запущенные сервисы'),
        ('get_repl_logs', 'Логи репликации PostgreSQL 📜'),
        ('get_emails', 'Получить email-адреса из базы данных 📧'),
        ('get_phone_numbers', 'Получить номера телефонов из базы данных 📞'),
        ('disconnect_ssh', 'Разрыв SSH-соединения'),
    ])


#---
# Команда для получения логов репликации
def get_repl_logs(update: Update, context: CallbackContext):
    logging.info("Пользователь %s вызвал /get_repl_logs", update.effective_user.username)
    
    try:
        ssh = ssh_connect()
        # Команда для чтения логов PostgreSQL и фильтрации строк, связанных с репликацией
        command = "grep -i 'replication\\|wal\\|streaming' /var/log/postgresql/postgresql.log | tail -n 50"
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        ssh.close()

        if error:
            update.message.reply_text(f"Ошибка при получении логов: {error}")
            return

        if not output:
            update.message.reply_text("Логи репликации не найдены или пусты.")
            return

        # Проверка длины вывода
        if len(output) > 4000:
            file = BytesIO()
            file.write(output.encode())
            file.seek(0)
            update.message.reply_document(document=file, filename="replication_logs.txt")
        else:
            update.message.reply_text(f"Логи репликации (последние 50 строк):\n{output}")

    except Exception as e:
        logging.error("Ошибка при получении логов репликации: %s", str(e))
        update.message.reply_text(f"Произошла ошибка: {str(e)}")

#---


def main():
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Настройка команд бота
    set_bot_commands(updater)
    
    # Обработчик состояний
    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start), 
            CommandHandler('find_email', handle_find_email),
            CommandHandler('find_phone_number', handle_find_phone_number),
            CommandHandler('verify_password', handle_verify_password)
        ],
        states={
	    FIND_EMAIL: [MessageHandler(Filters.text & ~Filters.command, find_email)],
            FIND_PHONE: [MessageHandler(Filters.text & ~Filters.command, find_phone_number)],
            VERIFY_PASSWORD: [MessageHandler(Filters.text & ~Filters.command, verify_password)],
            SAVE_EMAIL: [MessageHandler(Filters.text & ~Filters.command, save_email)],
            SAVE_PHONE: [MessageHandler(Filters.text & ~Filters.command, save_phone)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # Добавляем обработчики
    dispatcher.add_handler(conversation_handler)
    dispatcher.add_handler(CommandHandler("get_release", get_release))
    dispatcher.add_handler(CommandHandler("get_uptime", get_uptime))
    dispatcher.add_handler(CommandHandler("get_df", get_df))
    dispatcher.add_handler(CommandHandler("get_uname", get_uname))
    dispatcher.add_handler(CommandHandler("get_free", get_free))
    dispatcher.add_handler(CommandHandler("get_mpstat", get_mpstat))
    dispatcher.add_handler(CommandHandler("get_ps", get_ps))
    dispatcher.add_handler(CommandHandler("get_w", get_w))
    dispatcher.add_handler(CommandHandler("get_auths", get_auths))
    dispatcher.add_handler(CommandHandler("get_critical", get_critical))
    dispatcher.add_handler(CommandHandler("get_ss", get_ss))
    dispatcher.add_handler(CommandHandler("get_apt_list", get_apt_list))
    dispatcher.add_handler(CommandHandler("get_services", get_services))
    dispatcher.add_handler(CommandHandler("get_repl_logs", get_repl_logs))
    dispatcher.add_handler(CommandHandler("get_emails", get_emails))
    dispatcher.add_handler(CommandHandler("get_phone_numbers", get_phone_numbers))
    dispatcher.add_handler(CommandHandler("disconnect_ssh", disconnect_ssh))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
