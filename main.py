import json
import os
import random
import sqlite3
import time
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- 1. ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')


@app.route('/')
def home():
    return 'Бот с админкой и интерактивом запущен!'


def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()


# --- 2. БАЗА ДАННЫХ И ИНИЦИАЛИЗАЦИЯ ---
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_TOKEN_HERE')
bot = telebot.TeleBot(TOKEN)

# Список ID админов (добавь свой Telegram ID через запятую)
ADMIN_IDS = [123456789]


def get_db_connection():
    conn = sqlite3.connect('bot_database.db')
    return conn


def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            coins INTEGER DEFAULT 100,
            bank INTEGER DEFAULT 0,
            power INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            is_banned INTEGER DEFAULT 0,
            inventory TEXT DEFAULT '[]'
        )
    ''')
    conn.commit()
    conn.close()


init_db()


def get_player(user_id, name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
    row = c.fetchone()

    if not row:
        c.execute(
            'INSERT INTO players (user_id, name) VALUES (?, ?)', (user_id, name)
        )
        conn.commit()
        c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        row = c.fetchone()

    conn.close()

    return {
        'user_id': row[0],
        'name': row[1],
        'coins': row[2],
        'bank': row[3],
        'power': row[4],
        'exp': row[5],
        'level': row[6],
        'is_banned': row[7],
        'inventory': json.loads(row[8]),
    }


def save_player(p):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        '''
        UPDATE players SET
            name = ?, coins = ?, bank = ?, power = ?, exp = ?, level = ?, is_banned = ?, inventory = ?
        WHERE user_id = ?
    ''',
        (
            p['name'],
            p['coins'],
            p['bank'],
            p['power'],
            p['exp'],
            p['level'],
            p['is_banned'],
            json.dumps(p['inventory']),
            p['user_id'],
        ),
    )
    conn.commit()
    conn.close()


# --- 3. КЛАВИАТУРЫ ---
def main_menu_kb(user_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('⚡ Клик', callback_data='menu_click'),
        InlineKeyboardButton('📊 Профиль', callback_data='menu_profile'),
        InlineKeyboardButton('🎰 Игры', callback_data='menu_games'),
        InlineKeyboardButton('📦 Кейсы', callback_data='menu_cases'),
        InlineKeyboardButton('🏆 Топ', callback_data='menu_top'),
    )
    if user_id in ADMIN_IDS:
        kb.add(
            InlineKeyboardButton('👑 Админ-Панель', callback_data='menu_admin')
        )
    return kb


def games_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('🎁 3 Коробки', callback_data='game_boxes'),
        InlineKeyboardButton('🃏 Блекджек (21)', callback_data='game_bj'),
        InlineKeyboardButton('⬅️ В меню', callback_data='menu_main'),
    )
    return kb


def admin_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton('💰 Выдать монеты', callback_data='adm_give_money'),
        InlineKeyboardButton('🔨 Забанить/Разбанить', callback_data='adm_ban'),
        InlineKeyboardButton('⬅️ Назад', callback_data='menu_main'),
    )
    return kb


# --- 4. ОСНОВНАЯ ЛОГИКА И МЕНЮ ---
@bot.message_handler(commands=['start', 'menu'])
def start_cmd(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['is_banned']:
        bot.reply_to(message, '❌ Вы забанены в боте!')
        return

    bot.send_message(
        message.chat.id,
        f"🎮 **Добро пожаловать, {p['name']}!**\nИспользуй кнопки для управления:",
        reply_markup=main_menu_kb(p['user_id']),
        parse_mode='Markdown',
    )


# --- 5. ОБРАБОТКА CALLBACK-КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    p = get_player(call.from_user.id, call.from_user.first_name)

    if p['is_banned']:
        bot.answer_callback_query(
            call.id, '❌ Вы забанены в системе!', show_alert=True
        )
        return

    # --- Навигация ---
    if call.data == 'menu_main':
        bot.edit_message_text(
            f"🎮 **Главное меню:**\nИгрок: {p['name']} | Уровень: {p['level']}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu_kb(p['user_id']),
            parse_mode='Markdown',
        )

    elif call.data == 'menu_click':
        p['coins'] += p['power']
        p['exp'] += 1
        if p['exp'] >= p['level'] * 20:
            p['level'] += 1
            p['power'] += 1
            bot.answer_callback_query(
                call.id, f"🎉 НОВЫЙ УРОВЕНЬ! Теперь уровень {p['level']}!"
            )
        else:
            bot.answer_callback_query(
                call.id, f"+{p['power']} монет! (Всего: {p['coins']} 🪙)"
            )
        save_player(p)

    elif call.data == 'menu_profile':
        text = (
            f"📊 **Профиль {p['name']}:**\n\n"
            f"💰 Монет: **{p['coins']}** 🪙\n"
            f"⭐ Уровень: **{p['level']}** (EXP: {p['exp']}/{p['level'] * 20})\n"
            f"⚡ Сила клика: **{p['power']}**\n"
            f"🎒 Предметов: {len(p['inventory'])} шт."
        )
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton('⬅️ Назад', callback_data='menu_main')
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'menu_games':
        bot.edit_message_text(
            '🎰 **Выбери мини-игру:**',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=games_kb(),
            parse_mode='Markdown',
        )

    # --- Игра «3 Коробки» ---
    elif call.data == 'game_boxes':
        kb = InlineKeyboardMarkup(row_width=3)
        kb.add(
            InlineKeyboardButton('🎁 1', callback_data='box_1'),
            InlineKeyboardButton('🎁 2', callback_data='box_2'),
            InlineKeyboardButton('🎁 3', callback_data='box_3'),
        )
        kb.add(InlineKeyboardButton('⬅️ Назад', callback_data='menu_games'))
        bot.edit_message_text(
            '🎁 **Угадай, в какой коробке 500 монет!** (Цена игры: 100 🪙)',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data.startswith('box_'):
        if p['coins'] < 100:
            bot.answer_callback_query(
                call.id, '❌ Нужно 100 монет!', show_alert=True
            )
            return

        p['coins'] -= 100
        win = random.choice([True, False, False])

        if win:
            p['coins'] += 500
            res_text = '🎉 **ПОБЕДА!** Вы нашли **500** 🪙!'
        else:
            res_text = '😢 **Увы, коробка была пуста!**'

        save_player(p)
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton('🔄 Играть снова', callback_data='game_boxes'),
            InlineKeyboardButton('⬅️ Назад', callback_data='menu_games'),
        )
        bot.edit_message_text(
            res_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    # --- Кейсы ---
    elif call.data == 'menu_cases':
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton('📦 Открыть кейс (300 🪙)', callback_data='open_case'),
            InlineKeyboardButton('⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            '📦 **Магазин Кейсов:**\nШанс выбить от 50 до 2000 монет!',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'open_case':
        if p['coins'] < 300:
            bot.answer_callback_query(
                call.id, '❌ Недостаточно монет!', show_alert=True
            )
            return

        p['coins'] -= 300
        save_player(p)

        # Анимация открытия
        for status in [
            '📦 Открываем кейс.',
            '📦 Открываем кейс..',
            '📦 Открываем кейс...',
        ]:
            bot.edit_message_text(
                status, call.message.chat.id, call.message.message_id
            )
            time.sleep(0.5)

        prize = random.choice([50, 200, 500, 1000, 2000])
        p['coins'] += prize
        save_player(p)

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton('📦 Ещё раз', callback_data='open_case'),
            InlineKeyboardButton('⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            f'🎉 Из кейса выпало: **{prize}** 🪙!',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    # --- АДМИН-ПАНЕЛЬ ---
    elif call.data == 'menu_admin':
        if p['user_id'] not in ADMIN_IDS:
            bot.answer_callback_query(call.id, '❌ Нет прав!', show_alert=True)
            return

        bot.edit_message_text(
            '👑 **Панель Администратора:**',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=admin_kb(),
            parse_mode='Markdown',
        )

    elif call.data == 'adm_give_money':
        msg = bot.send_message(
            call.message.chat.id,
            'Введите ID пользователя и сумму через пробел (Пример: `12345678 5000`):',
        )
        bot.register_next_step_handler(msg, process_give_money)


def process_give_money(message):
    try:
        target_id, amount = map(int, message.text.split())
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'UPDATE players SET coins = coins + ? WHERE user_id = ?',
            (amount, target_id),
        )
        conn.commit()
        conn.close()
        bot.reply_to(message, f'✅ Успешно выдано {amount} монет пользователю `{target_id}`!')
    except Exception:
        bot.reply_to(message, '⚠️ Ошибка! Проверьте правильность введенных данных.')


# --- 6. СПОНТАННОЕ СОБЫТИЕ: ГОБЛИН В ЧАТЕ ---
@bot.message_handler(commands=['goblin'])
def spawn_goblin(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton('⚔️ УДАРИТЬ ГОБЛИНА!', callback_data='hit_goblin')
    )
    bot.send_message(
        message.chat.id,
        '👺 **НА ЧАТ НАПАЛ ГОБЛИН-ВОРИШКА!**\nКто успеет первым нажать на кнопку, заберет 1000 монет!',
        reply_markup=kb,
        parse_mode='Markdown',
    )


@bot.callback_query_handler(func=lambda call: call.data == 'hit_goblin')
def hit_goblin(call):
    p = get_player(call.from_user.id, call.from_user.first_name)
    p['coins'] += 1000
    save_player(p)

    bot.edit_message_text(
        f"⚔️ **Гоблин повержен!** Награду в **1000** 🪙 забрал **{p['name']}**!",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
    )


# --- 7. ЗАПУСК ---
if __name__ == '__main__':
    keep_alive()

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass

    print('🚀 Бот с полноценными кнопками и Админкой запущен!')

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            time.sleep(3)