import os
import sqlite3
import time
from threading import Thread
from flask import Flask
import telebot

# --- 1. ВЕБ-СЕРВЕР ДЛЯ ПОДДЕРЖАНИЯ ЖИЗНИ (KEEP-ALIVE) ---
app = Flask('')


@app.route('/')
def home():
    return 'Бот работает 24/7!'


def run_flask():
    # Render автоматически передаёт порт через переменную окружения PORT
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()


# --- 2. ИНИЦИАЛИЗАЦИЯ БОТА И БАЗЫ ДАННЫХ ---
TOKEN = os.environ.get('BOT_TOKEN', 'ТВОЙ_ТОКЕН_ЕСЛИ_ТЕСТИРУЕШЬ_ЛОКАЛЬНО')
bot = telebot.TeleBot(TOKEN)


def init_db():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            coins INTEGER DEFAULT 0,
            power INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()


init_db()


def get_player(user_id, name):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute(
        'SELECT user_id, name, coins, power FROM players WHERE user_id = ?',
        (user_id,),
    )
    row = c.fetchone()

    if not row:
        c.execute(
            'INSERT INTO players (user_id, name, coins, power) VALUES (?, ?, 0, 1)',
            (user_id, name),
        )
        conn.commit()
        player = {'user_id': user_id, 'name': name, 'coins': 0, 'power': 1}
    else:
        player = {
            'user_id': row[0],
            'name': row[1],
            'coins': row[2],
            'power': row[3],
        }

    conn.close()
    return player


def save_player(player):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute(
        'UPDATE players SET name = ?, coins = ?, power = ? WHERE user_id = ?',
        (player['name'], player['coins'], player['power'], player['user_id']),
    )
    conn.commit()
    conn.close()


# --- 3. КОМАНДЫ БОТА ---
@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.reply_to(
        message,
        '🎰 **Добро пожаловать в Чатовый Кликер!**\n\n'
        'Команды:\n'
        '💎 `/click` — майнить монеты\n'
        '💰 `/balance` — твой баланс\n'
        '🛒 `/shop` — купить видеокарту (+5 к клику)\n'
        '🏆 `/top` — топ богачей чата',
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['click'])
def click(message):
    user = get_player(message.from_user.id, message.from_user.first_name)
    user['coins'] += user['power']
    save_player(user)
    bot.reply_to(
        message,
        f"⚡ +{user['power']} монет! Ваш баланс: **{user['coins']}** 🪙",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['balance'])
def balance(message):
    user = get_player(message.from_user.id, message.from_user.first_name)
    bot.reply_to(
        message,
        f"📊 Игрок: **{user['name']}**\n💰 Монет: **{user['coins']}**\n⚡ Сила клика: **{user['power']}**",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['shop'])
def shop(message):
    user = get_player(message.from_user.id, message.from_user.first_name)
    cost = user['power'] * 20

    if user['coins'] >= cost:
        user['coins'] -= cost
        user['power'] += 5
        save_player(user)
        bot.reply_to(
            message,
            f"🚀 Вы купили новую видеокарту за {cost} монет! Теперь ваш клик дает **+{user['power']}** монет!",
            parse_mode='Markdown',
        )
    else:
        bot.reply_to(
            message,
            f"❌ Не хватает монет! Нужно: **{cost}** 🪙 (У вас: {user['coins']})",
            parse_mode='Markdown',
        )


@bot.message_handler(commands=['top'])
def top(message):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT name, coins FROM players ORDER BY coins DESC LIMIT 5')
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(
            message, 'Топ пока пуст! Начните играть с команды /click'
        )
        return

    text = '🏆 **ТОП-5 МАЙНЕРОВ ЧАТА:**\n\n'
    for i, (name, coins) in enumerate(rows, 1):
        text += f'{i}. {name} — **{coins}** 🪙\n'

    bot.reply_to(message, text, parse_mode='Markdown')


# --- 4. ЗАПУСК ВЕБ-СЕРВЕРА И ПОЛЛИНГА ---
if __name__ == '__main__':
    keep_alive()  # Запускает Flask-сервер в фоне

    # Автоматический перезапуск поллинга при сетевых сбоях
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            time.sleep(3)