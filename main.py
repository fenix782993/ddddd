import json
import os
import random
import sqlite3
import time
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- 1. ВЕБ-СЕРВЕР DLYA RENDER (KEEP-ALIVE) ---
app = Flask('')


@app.route('/')
def home():
    return 'Ультимативный Кликер-Бот с Проверкой Подписки Запущен!'


def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()


# --- 2. ИНИЦИАЛИЗАЦИЯ И НАСТРОЙКИ ---
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Настройки Администратора и Канала
ADMIN_IDS = [810823857]
REQUIRED_CHANNEL = '@qfenixqa'  # Обязательный канал для подписки


def get_db_connection():
    return sqlite3.connect('bot_database.db')


def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Игроки
    c.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            coins INTEGER DEFAULT 100,
            bank INTEGER DEFAULT 0,
            safe INTEGER DEFAULT 0,
            power INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            prestige INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            inventory TEXT DEFAULT '[]',
            equip_weapon TEXT DEFAULT 'None',
            equip_armor TEXT DEFAULT 'None',
            pet TEXT DEFAULT 'None',
            businesses TEXT DEFAULT '{"coffee":0, "farm":0, "mine":0}',
            last_feed INTEGER DEFAULT 0,
            last_wheel INTEGER DEFAULT 0,
            last_collect INTEGER DEFAULT 0,
            last_bank_interest INTEGER DEFAULT 0,
            bp_level INTEGER DEFAULT 1,
            bp_exp INTEGER DEFAULT 0
        )
    ''')

    # Промокоды
    c.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            reward INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            used_users TEXT DEFAULT '[]'
        )
    ''')

    # Босс
    c.execute('''
        CREATE TABLE IF NOT EXISTS boss (
            id INTEGER PRIMARY KEY,
            hp INTEGER DEFAULT 100000,
            max_hp INTEGER DEFAULT 100000,
            damage_log TEXT DEFAULT '{}'
        )
    ''')

    c.execute('SELECT COUNT(*) FROM boss')
    if c.fetchone()[0] == 0:
        c.execute(
            'INSERT INTO boss (id, hp, max_hp, damage_log) VALUES (1, 100000,'
            ' 100000, "{}")'
        )

    conn.commit()
    conn.close()


init_db()


# --- 3. ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ---
def check_sub(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception:
        # В случае ошибки проверки (если бот еще не админ в канале) пропускаем
        return True


def get_sub_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            '📢 Подписаться на канал', url=f'https://t.me/{REQUIRED_CHANNEL[1:]}'
        ),
        InlineKeyboardButton(
            '✅ Я подписался / Проверить', callback_data='check_subscription'
        ),
    )
    return kb


# --- 4. ВСПРАМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def make_progress_bar(current, maximum, length=10):
    if maximum <= 0:
        return '░' * length
    fraction = min(max(current / maximum, 0), 1)
    filled = int(fraction * length)
    return '█' * filled + '░' * (length - filled)


def get_user_title(level):
    if level < 5:
        return '🥉 Новичок'
    elif level < 15:
        return '🥈 Опытный'
    elif level < 30:
        return '🥇 Мастер'
    elif level < 50:
        return '💎 Магнат'
    else:
        return '👑 ЛЕГЕНДА'


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
        'safe': row[4],
        'power': row[5],
        'exp': row[6],
        'level': row[7],
        'prestige': row[8],
        'is_banned': row[9],
        'inventory': json.loads(row[10]),
        'equip_weapon': row[11],
        'equip_armor': row[12],
        'pet': json.loads(row[13]) if row[13] != 'None' else None,
        'businesses': json.loads(row[14]),
        'last_feed': row[15],
        'last_wheel': row[16],
        'last_collect': row[17],
        'last_bank_interest': row[18],
        'bp_level': row[19],
        'bp_exp': row[20],
    }


def save_player(p):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        '''
        UPDATE players SET
            name = ?, coins = ?, bank = ?, safe = ?, power = ?, exp = ?, level = ?, prestige = ?,
            is_banned = ?, inventory = ?, equip_weapon = ?, equip_armor = ?, pet = ?, businesses = ?,
            last_feed = ?, last_wheel = ?, last_collect = ?, last_bank_interest = ?, bp_level = ?, bp_exp = ?
        WHERE user_id = ?
    ''',
        (
            p['name'],
            p['coins'],
            p['bank'],
            p['safe'],
            p['power'],
            p['exp'],
            p['level'],
            p['prestige'],
            p['is_banned'],
            json.dumps(p['inventory']),
            p['equip_weapon'],
            p['equip_armor'],
            json.dumps(p['pet']) if p['pet'] else 'None',
            json.dumps(p['businesses']),
            p['last_feed'],
            p['last_wheel'],
            p['last_collect'],
            p['last_bank_interest'],
            p['bp_level'],
            p['bp_exp'],
            p['user_id'],
        ),
    )
    conn.commit()
    conn.close()


# --- 5. КЛАВИАТУРЫ ИНТЕРФЕЙСА ---
def main_menu_kb(user_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('⚡ Кликер', callback_data='menu_click'),
        InlineKeyboardButton('📊 Профиль', callback_data='menu_profile'),
        InlineKeyboardButton('💼 Бизнес и Доход', callback_data='menu_biz'),
        InlineKeyboardButton('🏦 Банк и Сейф', callback_data='menu_bank'),
        InlineKeyboardButton('🐱 Питомец', callback_data='menu_pet'),
        InlineKeyboardButton('🎲 Мини-Игры', callback_data='menu_games'),
        InlineKeyboardButton('⚔️ Босс и PVP', callback_data='menu_pvp'),
        InlineKeyboardButton('🔮 Крафт', callback_data='menu_craft'),
        InlineKeyboardButton('🎫 Battle Pass', callback_data='menu_bp'),
        InlineKeyboardButton('🎁 Промокод', callback_data='menu_promo'),
    )
    if user_id in ADMIN_IDS:
        kb.add(
            InlineKeyboardButton('👑 АДМИН-ПАНЕЛЬ', callback_data='menu_admin')
        )
    return kb


def back_kb():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton('⬅️ Назад в Меню', callback_data='menu_main')
    )


# --- 6. ОСНОВНЫЕ ОБРАБОТЧИКИ ---
@bot.message_handler(commands=['start', 'menu'])
def start_cmd(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['is_banned']:
        bot.reply_to(message, '❌ Вы забанены!')
        return

    # Проверка Обязательной Подписки
    if not check_sub(message.from_user.id):
        bot.send_message(
            message.chat.id,
            f'⚠️ **Для доступа к боту необходимо подписаться на наш канал {REQUIRED_CHANNEL}!**',
            reply_markup=get_sub_keyboard(),
            parse_mode='Markdown',
        )
        return

    title = get_user_title(p['level'])
    bot.send_message(
        message.chat.id,
        f'✨ **Добро пожаловать, {title} {p["name"]}!**\nВыберите раздел:',
        reply_markup=main_menu_kb(p['user_id']),
        parse_mode='Markdown',
    )


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    p = get_player(call.from_user.id, call.from_user.first_name)

    if p['is_banned']:
        bot.answer_callback_query(call.id, '❌ Вы забанены!', show_alert=True)
        return

    # Обработка кнопки проверки подписки
    if call.data == 'check_subscription':
        if check_sub(call.from_user.id):
            bot.answer_callback_query(
                call.id, '✅ Подписка подтверждена!', show_alert=True
            )
            bot.edit_message_text(
                '🎮 **Главное меню доступно:**',
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_menu_kb(p['user_id']),
            )
        else:
            bot.answer_callback_query(
                call.id, '❌ Вы всё ещё не подписались!', show_alert=True
            )
        return

    # Строгая проверка подписки при любом клике
    if not check_sub(call.from_user.id):
        bot.send_message(
            call.message.chat.id,
            f'⚠️ **Подпишитесь на {REQUIRED_CHANNEL} для игры!**',
            reply_markup=get_sub_keyboard(),
            parse_mode='Markdown',
        )
        return

    # --- Главное Меню ---
    if call.data == 'menu_main':
        bot.edit_message_text(
            f'🎮 **Главное меню:**\nИгрок: **{p["name"]}** | Уровень:'
            f' **{p["level"]}**',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu_kb(p['user_id']),
            parse_mode='Markdown',
        )

    # --- ⚡ Кликер ---
    elif call.data == 'menu_click':
        mult = 1.0 + (p['prestige'] * 0.5)  # Престиж даёт +50% ко всем кликам
        if p['pet'] and (time.time() - p['last_feed'] < 86400):
            mult += 0.2

        earned = int(p['power'] * mult)
        p['coins'] += earned
        p['exp'] += 1
        p['bp_exp'] += 1

        if p['bp_exp'] >= 10 and p['bp_level'] < 100:
            p['bp_level'] += 1
            p['bp_exp'] = 0

        if p['exp'] >= p['level'] * 25:
            p['level'] += 1
            p['power'] += 1

        save_player(p)
        bot.answer_callback_query(
            call.id, f'⚡ +{earned} монет! (Баланс: {p["coins"]} 🪙)'
        )

    # --- 📊 Профиль ---
    elif call.data == 'menu_profile':
        title = get_user_title(p['level'])
        exp_bar = make_progress_bar(p['exp'], p['level'] * 25)

        kb = InlineKeyboardMarkup(row_width=1)
        if p['level'] >= 50:
            kb.add(
                InlineKeyboardButton(
                    '🔄 Сделать Перерождение (Prestige)',
                    callback_data='do_prestige',
                )
            )
        kb.add(InlineKeyboardButton('⬅️ Назад', callback_data='menu_main'))

        text = (
            f'👤 **ПРОФИЛЬ:** {title} **{p["name"]}**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'💰 Монет: **{p["coins"]}** 🪙 | 🏦 Банк: **{p["bank"]}** 🪙 | 🔒'
            f' Сейф: **{p["safe"]}** 🪙\n'
            f'⚡ Сила клика: **{p["power"]}** | 💎 Множитель Перерождений:'
            f' **x{1 + p["prestige"] * 0.5}**\n\n'
            f'⭐ Уровень: **{p["level"]}**\n'
            f'[`{exp_bar}`] {p["exp"]}/{p["level"]*25} EXP'
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'do_prestige':
        p['coins'] = 0
        p['bank'] = 0
        p['level'] = 1
        p['exp'] = 0
        p['power'] = 1
        p['prestige'] += 1
        save_player(p)
        bot.answer_callback_query(
            call.id,
            '🎉 Вы совершили ПЕРЕРОЖДЕНИЕ! Получен постоянный множитель ко всем'
            ' доходам!',
            show_alert=True,
        )

    # --- 💼 Бизнес и Пассивный доход ---
    elif call.data == 'menu_biz':
        now = time.time()
        hours_passed = int((now - p['last_collect']) // 3600)

        # Доходность бизнесов в час
        biz_income = (
            (p['businesses']['coffee'] * 100)
            + (p['businesses']['farm'] * 500)
            + (p['businesses']['mine'] * 2000)
        )
        total_uncollected = hours_passed * biz_income

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                f'🧺 Собрать кассу ({total_uncollected} 🪙)',
                callback_data='collect_biz',
            ),
            InlineKeyboardButton(
                '☕ Купить Кофейню (2 000 🪙)', callback_data='buy_coffee'
            ),
            InlineKeyboardButton(
                '🚜 Купить Ферму (10 000 🪙)', callback_data='buy_farm'
            ),
            InlineKeyboardButton(
                '⛏️ Купить Шахту (50 000 🪙)', callback_data='buy_mine'
            ),
            InlineKeyboardButton('⬅️ Назад', callback_data='menu_main'),
        )
        text = (
            f'💼 **ВАША БИЗНЕС-ИМПЕРИЯ:**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'☕ Кофеен: **{p["businesses"]["coffee"]}** шт.\n'
            f'🚜 Ферм: **{p["businesses"]["farm"]}** шт.\n'
            f'⛏️ Шахт: **{p["businesses"]["mine"]}** шт.\n\n'
            f'📈 Общий доход: **+{biz_income}** 🪙/час\n'
            f'⏳ Накоплено к сбору: **{total_uncollected}** 🪙'
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'collect_biz':
        now = time.time()
        hours_passed = int((now - p['last_collect']) // 3600)
        biz_income = (
            (p['businesses']['coffee'] * 100)
            + (p['businesses']['farm'] * 500)
            + (p['businesses']['mine'] * 2000)
        )
        total_uncollected = hours_passed * biz_income

        if total_uncollected > 0:
            p['coins'] += total_uncollected
            p['last_collect'] = now
            save_player(p)
            bot.answer_callback_query(
                call.id, f'✅ Собрано +{total_uncollected} монет!', show_alert=True
            )
        else:
            bot.answer_callback_query(
                call.id, '⏳ Касса пока пуста! Зайдите позже.', show_alert=True
            )

    elif call.data in ['buy_coffee', 'buy_farm', 'buy_mine']:
        costs = {'buy_coffee': 2000, 'buy_farm': 10000, 'buy_mine': 50000}
        keys = {'buy_coffee': 'coffee', 'buy_farm': 'farm', 'buy_mine': 'mine'}
        cost = costs[call.data]
        key = keys[call.data]

        if p['coins'] >= cost:
            p['coins'] -= cost
            p['businesses'][key] += 1
            save_player(p)
            bot.answer_callback_query(
                call.id, '🎉 Бизнес успешно куплен!', show_alert=True
            )
        else:
            bot.answer_callback_query(
                call.id, '❌ Недостаточно средств!', show_alert=True
            )

    # --- 🎲 Мини-игры ---
    elif call.data == 'menu_games':
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton('🎲 Кости (Dice)', callback_data='game_dice'),
            InlineKeyboardButton('🎡 Колесо Удачи', callback_data='menu_wheel'),
            InlineKeyboardButton('⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            '🎲 **ИГРОВОЙ КЛУБ / КАЗИНО**\nВыберите игру:',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'game_dice':
        if p['coins'] < 100:
            bot.answer_callback_query(
                call.id, '❌ Нужно минимум 100 монет!', show_alert=True
            )
            return

        p['coins'] -= 100
        roll = random.randint(1, 6)
        if roll >= 4:
            win = 200
            p['coins'] += win
            msg = f'🎲 Выпало **{roll}**! ВЫ ВЫИГРАЛИ {win} 🪙!'
        else:
            msg = f'🎲 Выпало **{roll}**! Вы проиграли 100 🪙.'

        save_player(p)
        bot.answer_callback_query(call.id, msg, show_alert=True)

    # --- ⚔️ PVP И ОГРАБЛЕНИЯ ---
    elif call.data == 'menu_pvp':
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                '🥷 Ограбить случайного игрока', callback_data='rob_player'
            ),
            InlineKeyboardButton(
                '👹 Атаковать Босса', callback_data='menu_boss'
            ),
            InlineKeyboardButton('⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            '⚔️ **PVP И ОГРАБЛЕНИЯ**\nНападайте на игроков и забирайте их'
            ' незащищенные монеты!',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'rob_player':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'SELECT user_id, name, coins FROM players WHERE user_id != ? AND'
            ' coins > 100 ORDER BY RANDOM() LIMIT 1',
            (p['user_id'],),
        )
        target = c.fetchone()
        conn.close()

        if not target:
            bot.answer_callback_query(
                call.id, '❌ Подходящих жертв не найдено!', show_alert=True
            )
            return

        success = random.choice([True, False])
        if success:
            stolen = int(target[2] * random.uniform(0.1, 0.3))
            p['coins'] += stolen

            # Списываем у жертвы
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                'UPDATE players SET coins = coins - ? WHERE user_id = ?',
                (stolen, target[0]),
            )
            conn.commit()
            conn.close()

            save_player(p)
            bot.answer_callback_query(
                call.id,
                f'🥷 Вы успешно ограбили {target[1]} на {stolen} 🪙!',
                show_alert=True,
            )
        else:
            bot.answer_callback_query(
                call.id, '🚨 Засада! Ограбление не удалось.', show_alert=True
            )

    # --- 👑 АДМИН-ПАНЕЛЬ (РАСШИРЕННАЯ) ---
    elif call.data == 'menu_admin':
        if p['user_id'] not in ADMIN_IDS:
            bot.answer_callback_query(call.id, '❌ Отказано!', show_alert=True)
            return

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(
                '📊 Статистика Бота', callback_data='adm_stats'
            ),
            InlineKeyboardButton('💰 Выдать Монеты', callback_data='adm_money'),
            InlineKeyboardButton(
                '📢 Рассылка Сообщения', callback_data='adm_broadcast'
            ),
            InlineKeyboardButton(
                '🔨 Забанить / Разбанить', callback_data='adm_ban'
            ),
            InlineKeyboardButton('⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            '👑 **АДМИН-ПАНЕЛЬ УПРАВЛЕНИЯ:**',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'adm_stats':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'SELECT COUNT(*), SUM(coins), SUM(bank), SUM(safe) FROM players'
        )
        row = c.fetchone()
        conn.close()

        total_users = row[0]
        total_econ = (row[1] or 0) + (row[2] or 0) + (row[3] or 0)

        bot.edit_message_text(
            f'📊 **ЭКОНОМИКА И СТАТИСТИКА БОТА:**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'👥 Всего пользователей: **{total_users}**\n'
            f'💰 Монет в экономике: **{total_econ}** 🪙',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_kb(),
            parse_mode='Markdown',
        )


# --- 7. БЕЗОПАСНЫЙ ЗАПУСК ---
if __name__ == '__main__':
    keep_alive()

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass

    print('🚀 Ультимативный Бот с проверкой подписки запущен!')

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            time.sleep(3)