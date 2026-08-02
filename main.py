import json
import os
import random
import sqlite3
import time
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# ==========================================
# 1. СЕРВЕР ДЛЯ RENDER (KEEP-ALIVE)
# ==========================================
app = Flask('')


@app.route('/')
def home():
    return 'Game Bot is Online 24/7!'


def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()


# ==========================================
# 2. НАСТРОЙКИ И БАЗА ДАННЫХ
# ==========================================
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# ID Главного Администратора
ADMIN_IDS = [810823857]
# Обязательный канал для подписки
REQUIRED_CHANNEL = '@qfenixqa'

# Временная память для игровых сессий "Мины"
mines_sessions = {}


def get_db_connection():
    return sqlite3.connect('bot_database.db')


def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Таблица игроков
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
            eq_weapon TEXT DEFAULT 'None',
            eq_armor TEXT DEFAULT 'None',
            pet TEXT DEFAULT '{"name": "None", "level": 0, "fed": 0}',
            businesses TEXT DEFAULT '{"coffee":0, "farm":0, "mine":0}',
            last_feed INTEGER DEFAULT 0,
            last_wheel INTEGER DEFAULT 0,
            last_collect INTEGER DEFAULT 0,
            last_bank_interest INTEGER DEFAULT 0,
            bp_level INTEGER DEFAULT 1,
            bp_exp INTEGER DEFAULT 0
        )
    ''')

    # Таблица P2P Рынка
    c.execute('''
        CREATE TABLE IF NOT EXISTS market (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER,
            item_name TEXT,
            price INTEGER
        )
    ''')

    # Таблица промокодов
    c.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            reward INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            used_users TEXT DEFAULT '[]'
        )
    ''')

    # Таблица мирового босса
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


# ==========================================
# 3. ВПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def check_sub(user_id):
    """Проверка обязательной подписки на канал"""
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return True


def get_sub_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            '🔴 📢 Подписаться на канал',
            url=f'https://t.me/{REQUIRED_CHANNEL[1:]}',
        ),
        InlineKeyboardButton(
            '🟩 ✅ Проверить подписку', callback_data='check_subscription'
        ),
    )
    return kb


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
            'INSERT INTO players (user_id, name, last_collect) VALUES (?, ?,'
            ' ?)',
            (user_id, name, int(time.time())),
        )
        conn.commit()
        c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        row = c.fetchone()

    conn.close()

    pet_data = (
        json.loads(row[13])
        if row[13] and row[13] != 'None'
        else {'name': 'None', 'level': 0, 'fed': 0}
    )

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
        'eq_weapon': row[11],
        'eq_armor': row[12],
        'pet': pet_data,
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
            is_banned = ?, inventory = ?, eq_weapon = ?, eq_armor = ?, pet = ?, businesses = ?,
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
            p['eq_weapon'],
            p['eq_armor'],
            json.dumps(p['pet']),
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


# ==========================================
# 4. ЦВЕТНОЕ ГЛАВНОЕ МЕНЮ
# ==========================================
def main_menu_kb(user_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('🟨 ⚡ Майнить (Клик)', callback_data='menu_click'),
        InlineKeyboardButton(
            '🟦 👤 Профиль & Шмот', callback_data='menu_profile'
        ),
        InlineKeyboardButton('🟩 💼 Бизнесы', callback_data='menu_biz'),
        InlineKeyboardButton('🟦 🏦 Банк и Сейф', callback_data='menu_bank'),
        InlineKeyboardButton('🟥 💣 Игра "Мины"', callback_data='start_mines'),
        InlineKeyboardButton('🟧 🎲 Кубик Удачи', callback_data='game_dice_anim'),
        InlineKeyboardButton(
            '🟪 📦 Лутбоксы/Кейсы', callback_data='menu_cases'
        ),
        InlineKeyboardButton('🟧 🐶 Мой Питомец', callback_data='menu_pet'),
        InlineKeyboardButton('🟥 ⚔️ PVP & Босс', callback_data='menu_pvp'),
        InlineKeyboardButton('🟨 🛒 P2P Рынок', callback_data='menu_market'),
        InlineKeyboardButton('🟪 🏆 Топ Богачей', callback_data='menu_top'),
        InlineKeyboardButton('🟩 🎁 Ввести Промокод', callback_data='menu_promo'),
    )
    if user_id in ADMIN_IDS:
        kb.add(
            InlineKeyboardButton('🟥 👑 АДМИН-ПАНЕЛЬ', callback_data='menu_admin')
        )
    return kb


def back_kb():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton('⬛ ⬅️ В Главное Меню', callback_data='menu_main')
    )


# ==========================================
# 5. ОБРАБОТКА КОМАНД И ВХОДА
# ==========================================
@bot.message_handler(commands=['start', 'menu'])
def start_cmd(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['is_banned']:
        bot.reply_to(message, '❌ Ваш аккаунт заблокирован!')
        return

    if not check_sub(message.from_user.id):
        bot.send_message(
            message.chat.id,
            f'⚠️ **Для доступа к игре подпишитесь на наш канал {REQUIRED_CHANNEL}!**',
            reply_markup=get_sub_keyboard(),
            parse_mode='Markdown',
        )
        return

    now = time.time()
    hours_passed = int((now - p['last_collect']) // 3600)
    income_per_hour = (
        (p['businesses']['coffee'] * 100)
        + (p['businesses']['farm'] * 500)
        + (p['businesses']['mine'] * 2000)
    )
    offline_earned = hours_passed * income_per_hour

    welcome_text = f'✨ **С возвращением, {p["name"]}!**\n\n'
    if offline_earned > 0:
        p['coins'] += offline_earned
        p['last_collect'] = now
        save_player(p)
        welcome_text += (
            f'💰 **Офлайн доход:** Пока вас не было, бизнесы принесли'
            f' **+{offline_earned}** 🪙!\n\n'
        )

    bot.send_message(
        message.chat.id,
        welcome_text + 'Используйте интерактивное меню ниже для игры:',
        reply_markup=main_menu_kb(p['user_id']),
        parse_mode='Markdown',
    )


# ==========================================
# 6. ОСНОВНОЙ CALLBACK ОБРАБОТЧИК
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    p = get_player(call.from_user.id, call.from_user.first_name)

    if p['is_banned']:
        bot.answer_callback_query(call.id, '❌ Доступ ограничен!', show_alert=True)
        return

    if call.data == 'check_subscription':
        if check_sub(call.from_user.id):
            bot.answer_callback_query(call.id, '✅ Подписка подтверждена!')
            bot.edit_message_text(
                '🎮 **Главное Меню:**',
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_menu_kb(p['user_id']),
            )
        else:
            bot.answer_callback_query(
                call.id, '❌ Вы всё ещё не подписаны!', show_alert=True
            )
        return

    if not check_sub(call.from_user.id):
        bot.send_message(
            call.message.chat.id,
            f'⚠️ **Подпишитесь на канал {REQUIRED_CHANNEL} для игры!**',
            reply_markup=get_sub_keyboard(),
        )
        return

    # --- 🎮 Главное Меню ---
    if call.data == 'menu_main':
        title = get_user_title(p['level'])
        bot.edit_message_text(
            f'🎮 **Главное Меню**\n\nСтатус: **{title}**\nИгрок:'
            f' **{p["name"]}** | Уровень: **{p["level"]}**',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu_kb(p['user_id']),
            parse_mode='Markdown',
        )

    # --- 🟨 КЛИКЕР С КРИТАМИ И БОНУСОМ ПИТОМЦА ---
    elif call.data == 'menu_click':
        mult = 1.0 + (p['prestige'] * 0.5)
        weapon_bonus = 15 if p['eq_weapon'] == '🔥 Огненный клинок' else 0
        pet_bonus = 5 if p['pet']['name'] != 'None' else 0

        is_crit = random.random() <= 0.15
        crit_mult = 3.0 if is_crit else 1.0

        earned = int(
            ((p['power'] + weapon_bonus + pet_bonus) * mult) * crit_mult
        )
        p['coins'] += earned
        p['exp'] += 1

        max_exp = p['level'] * 25
        if p['exp'] >= max_exp:
            p['level'] += 1
            p['power'] += 1

        save_player(p)
        msg_text = (
            f'💥 КРИТ x3! +{earned} 🪙'
            if is_crit
            else f'⚡ +{earned} 🪙 (Всего: {p["coins"]})'
        )
        bot.answer_callback_query(call.id, msg_text)

    # --- 🟪 КЕЙСЫ (LOOTBOXES) ---
    elif call.data == 'menu_cases':
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                '🟫 Бронзовый Кейс (1 000 🪙)', callback_data='open_case_bronze'
            ),
            InlineKeyboardButton(
                '⬜ Серебряный Кейс (5 000 🪙)', callback_data='open_case_silver'
            ),
            InlineKeyboardButton(
                '🟨 Легендарный Кейс (25 000 🪙)', callback_data='open_case_gold'
            ),
            InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            '🟪 **МАГАЗИН КЕЙСОВ**\nИспытайте удачу и выбейте монетный куш или'
            ' редкое оружие!',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data.startswith('open_case_'):
        case_type = call.data.split('_')[2]
        costs = {'bronze': 1000, 'silver': 5000, 'gold': 25000}
        cost = costs[case_type]

        if p['coins'] < cost:
            bot.answer_callback_query(
                call.id, '❌ Недостаточно монет!', show_alert=True
            )
            return

        p['coins'] -= cost
        rand = random.randint(1, 100)

        if rand <= 60:
            win = int(cost * random.uniform(0.5, 1.5))
            p['coins'] += win
            msg = f'🪙 Вы выиграли **{win} 🪙**!'
        elif rand <= 90:
            if '🔥 Огненный клинок' not in p['inventory']:
                p['inventory'].append('🔥 Огненный клинок')
            msg = '⚔️ Вы выбили **🔥 Огненный клинок**!'
        else:
            win = cost * 3
            p['coins'] += win
            msg = f'💥 ДЖЕКПОТ! Вы выиграли **{win} 🪙**!'

        save_player(p)
        bot.edit_message_text(
            f'📦 **Открытие кейса...**\n\n{msg}',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_kb(),
            parse_mode='Markdown',
        )

    # --- 🟧 ПИТОМЕЦ ---
    elif call.data == 'menu_pet':
        kb = InlineKeyboardMarkup(row_width=1)
        if p['pet']['name'] == 'None':
            kb.add(
                InlineKeyboardButton(
                    '🟩 Купить Дракончика (10 000 🪙)', callback_data='buy_pet_dragon'
                )
            )
        else:
            kb.add(
                InlineKeyboardButton(
                    '🟨 Накормить питомца (500 🪙)', callback_data='feed_pet'
                )
            )

        kb.add(InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'))

        pet_name = (
            p['pet']['name']
            if p['pet']['name'] != 'None'
            else 'Отсутствует'
        )
        text = (
            f'🟧 **МОЙ ПИТОМЕЦ**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'Питомец: **{pet_name}**\n'
            f'💡 *Питомец даёт +5 ко всем кликам!*'
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'buy_pet_dragon':
        if p['coins'] >= 10000:
            p['coins'] -= 10000
            p['pet'] = {'name': '🐲 Дракончик', 'level': 1, 'fed': time.time()}
            save_player(p)
            bot.answer_callback_query(
                call.id, '🎉 Вы приобрели Дракончика!', show_alert=True
            )
        else:
            bot.answer_callback_query(call.id, '❌ Недостаточно монет!')

    elif call.data == 'feed_pet':
        if p['coins'] >= 500:
            p['coins'] -= 500
            p['pet']['fed'] = time.time()
            save_player(p)
            bot.answer_callback_query(
                call.id, '🍖 Питомец сыт и доволен!', show_alert=True
            )
        else:
            bot.answer_callback_query(call.id, '❌ Недостаточно монет!')

    # --- 🟨 P2P РЫНОК ---
    elif call.data == 'menu_market':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'SELECT id, item_name, price FROM market ORDER BY id DESC LIMIT 5'
        )
        items = c.fetchall()
        conn.close()

        kb = InlineKeyboardMarkup(row_width=1)
        for it in items:
            kb.add(
                InlineKeyboardButton(
                    f'🟩 Купить {it[1]} за {it[2]} 🪙',
                    callback_data=f'buy_m_{it[0]}',
                )
            )

        kb.add(
            InlineKeyboardButton(
                '🟦 Выставить предмет на продажу', callback_data='sell_market'
            )
        )
        kb.add(InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'))

        bot.edit_message_text(
            '🟨 **P2P ТОРГОВАЯ ПЛОЩАДКА**\nПокупайте редкие предметы у других'
            ' игроков!',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'sell_market':
        if '🔥 Огненный клинок' in p['inventory']:
            p['inventory'].remove('🔥 Огненный клинок')
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                'INSERT INTO market (seller_id, item_name, price) VALUES (?,'
                ' ?, ?)',
                (p['user_id'], '🔥 Огненный клинок', 15000),
            )
            conn.commit()
            conn.close()
            save_player(p)
            bot.answer_callback_query(
                call.id,
                '✅ Предмет выставлен на рынок за 15 000 🪙!',
                show_alert=True,
            )
        else:
            bot.answer_callback_query(
                call.id, '❌ У вас нет предметов для продажи!', show_alert=True
            )

    # --- 🟦 ПРОФИЛЬ И ИНВЕНТАРЬ ---
    elif call.data == 'menu_profile':
        title = get_user_title(p['level'])
        max_exp = p['level'] * 25
        exp_bar = make_progress_bar(p['exp'], max_exp)

        kb = InlineKeyboardMarkup(row_width=1)
        if (
            '🔥 Огненный клинок' in p['inventory']
            and p['eq_weapon'] != '🔥 Огненный клинок'
        ):
            kb.add(
                InlineKeyboardButton(
                    '⚔️ Надеть "Огненный клинок"',
                    callback_data='equip_weapon_fire',
                )
            )

        if p['level'] >= 50:
            kb.add(
                InlineKeyboardButton(
                    '🔄 Совершить Перерождение (Prestige)',
                    callback_data='do_prestige',
                )
            )

        kb.add(InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'))

        text = (
            f'👤 **ПРОФИЛЬ ИГРОКА:**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'⚜️ Титул: **{title}**\n'
            f'🏷 Имя: **{p["name"]}**\n'
            f'💰 На руках: **{p["coins"]}** 🪙\n'
            f'🏦 В Банке: **{p["bank"]}** 🪙 | 🔒 В Сейфе: **{p["safe"]}** 🪙\n'
            f'⚡ Сила клика: **{p["power"]}** | 💎 Престиж:'
            f' **x{1 + p["prestige"] * 0.5}**\n\n'
            f'🗡 Оружие: **{p["eq_weapon"]}**\n'
            f'🐶 Питомец: **{p["pet"]["name"]}**\n\n'
            f'⭐ Уровень: **{p["level"]}**\n'
            f'[`{exp_bar}`] {p["exp"]}/{max_exp} EXP'
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'equip_weapon_fire':
        p['eq_weapon'] = '🔥 Огненный клинок'
        save_player(p)
        bot.answer_callback_query(call.id, '⚔️ Оружие экипировано!', show_alert=True)

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
            '🎉 Вы совершили ПЕРЕРОЖДЕНИЕ! Получен множитель к доходам!',
            show_alert=True,
        )

    # --- 🟥 МИНЫ ---
    elif call.data == 'start_mines':
        if p['coins'] < 200:
            bot.answer_callback_query(
                call.id,
                '❌ Минимальная ставка в Мины: 200 монет!',
                show_alert=True,
            )
            return

        p['coins'] -= 200
        save_player(p)

        board = ['safe'] * 7 + ['mine'] * 2
        random.shuffle(board)

        mines_sessions[p['user_id']] = {
            'board': board,
            'opened': [False] * 9,
            'step': 0,
            'bet': 200,
            'mult': 1.0,
        }

        render_mines_game(call.message, p['user_id'])

    elif call.data.startswith('mine_open_'):
        idx = int(call.data.split('_')[2])
        session = mines_sessions.get(p['user_id'])

        if not session:
            bot.answer_callback_query(
                call.id, 'Сессия игры истекла!', show_alert=True
            )
            return

        if session['opened'][idx]:
            return

        if session['board'][idx] == 'mine':
            del mines_sessions[p['user_id']]
            bot.edit_message_text(
                '💥 **БУУУМ! Вы подорвались на мине и потеряли 200 монет!**',
                call.message.chat.id,
                call.message.message_id,
                reply_markup=back_kb(),
                parse_mode='Markdown',
            )
        else:
            session['opened'][idx] = True
            session['step'] += 1
            session['mult'] += 0.4
            render_mines_game(call.message, p['user_id'])

    elif call.data == 'mines_take':
        session = mines_sessions.get(p['user_id'])
        if session:
            win = int(session['bet'] * session['mult'])
            p['coins'] += win
            save_player(p)
            del mines_sessions[p['user_id']]
            bot.edit_message_text(
                f'🎉 **ВЫ ЗАБРАЛИ ВЫИГРЫШ: +{win} 🪙!**',
                call.message.chat.id,
                call.message.message_id,
                reply_markup=back_kb(),
                parse_mode='Markdown',
            )

    # --- 🟧 АНИМИРОВАННЫЕ КОСТИ ---
    elif call.data == 'game_dice_anim':
        if p['coins'] < 100:
            bot.answer_callback_query(
                call.id, '❌ Для броска нужно 100 монет!', show_alert=True
            )
            return

        p['coins'] -= 100
        save_player(p)

        msg = bot.send_dice(call.message.chat.id, emoji='🎲')
        val = msg.dice.value
        time.sleep(2.5)

        if val >= 4:
            win = val * 50
            p['coins'] += win
            save_player(p)
            bot.send_message(
                call.message.chat.id,
                f'🎉 Выпало **{val}**! Вы выиграли **+{win}** 🪙!',
                reply_markup=back_kb(),
            )
        else:
            bot.send_message(
                call.message.chat.id,
                f'📉 Выпало **{val}**. К сожалению, ставка сгорела.',
                reply_markup=back_kb(),
            )

    # --- 🟩 БИЗНЕCЫ ---
    elif call.data == 'menu_biz':
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                '☕ Купить Кофейню (2 000 🪙)', callback_data='buy_coffee'
            ),
            InlineKeyboardButton(
                '🚜 Купить Ферму (10 000 🪙)', callback_data='buy_farm'
            ),
            InlineKeyboardButton(
                '⛏️ Купить Шахту (50 000 🪙)', callback_data='buy_mine'
            ),
            InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'),
        )
        inc = (
            (p['businesses']['coffee'] * 100)
            + (p['businesses']['farm'] * 500)
            + (p['businesses']['mine'] * 2000)
        )
        text = (
            f'💼 **БИЗНЕС-ИМПЕРИЯ (Пассивный доход)**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'☕ Кофеен: **{p["businesses"]["coffee"]}** (+100 🪙/час)\n'
            f'🚜 Ферм: **{p["businesses"]["farm"]}** (+500 🪙/час)\n'
            f'⛏️ Шахт: **{p["businesses"]["mine"]}** (+2 000 🪙/час)\n\n'
            f'📈 Ваш общий доход: **+{inc}** 🪙/час\n'
            f'💡 *Доход накапливается автоматически, пока вы оффлайн!*'
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
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
                call.id, '🎉 Бизнес успешно приобретён!', show_alert=True
            )
        else:
            bot.answer_callback_query(
                call.id, '❌ Недостаточно монет!', show_alert=True
            )

    # --- 🟦 БАНК И СЕЙФ ---
    elif call.data == 'menu_bank':
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton('📥 В Банк (+5%)', callback_data='bank_dep'),
            InlineKeyboardButton('📤 Из Банка', callback_data='bank_with'),
            InlineKeyboardButton('🔒 В Сейф', callback_data='safe_dep'),
            InlineKeyboardButton('🔓 Из Сейфа', callback_data='safe_with'),
            InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'),
        )
        text = (
            f'🏦 **ФИНАНСОВЫЙ ЦЕНТР**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'💳 Депозит в Банке: **{p["bank"]}** 🪙 *(+5% в день)*\n'
            f'🔒 Сейф: **{p["safe"]}** 🪙 *(Защита 100% от грабежей)*\n'
            f'💵 На руках: **{p["coins"]}** 🪙'
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data in ['bank_dep', 'bank_with', 'safe_dep', 'safe_with']:
        act = call.data
        if act == 'bank_dep' and p['coins'] > 0:
            p['bank'] += p['coins']
            p['coins'] = 0
        elif act == 'bank_with' and p['bank'] > 0:
            p['coins'] += p['bank']
            p['bank'] = 0
        elif act == 'safe_dep' and p['coins'] > 0:
            p['safe'] += p['coins']
            p['coins'] = 0
        elif act == 'safe_with' and p['safe'] > 0:
            p['coins'] += p['safe']
            p['safe'] = 0
        save_player(p)
        bot.answer_callback_query(call.id, '✅ Операция выполнена!')

    # --- 🟥 PVP, ДУЭЛИ И БОСС ---
    elif call.data == 'menu_pvp':
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                '⚔️ Поединок Дуэль на 1 000 🪙', callback_data='pvp_duel'
            ),
            InlineKeyboardButton(
                '🥷 Ограбить случайного игрока', callback_data='rob_player'
            ),
            InlineKeyboardButton(
                '👹 Атаковать Мирового Босса', callback_data='menu_boss'
            ),
            InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            '⚔️ **PVP АРЕНА И СРАЖЕНИЯ**\nСражайтесь на дуэлях, грабьте'
            ' незащищенные монеты или бейте Босса!',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'pvp_duel':
        if p['coins'] < 1000:
            bot.answer_callback_query(
                call.id, '❌ Для дуэли нужно 1 000 монет!', show_alert=True
            )
            return

        if random.choice([True, False]):
            p['coins'] += 1000
            msg = '🎉 **ВЫ ПОБЕДИЛИ В ДУЭЛИ! +1 000 🪙**'
        else:
            p['coins'] -= 1000
            msg = '📉 **ВЫ ПРОИГРАЛИ ДУЭЛЬ! -1 000 🪙**'

        save_player(p)
        bot.edit_message_text(
            msg,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_kb(),
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
                call.id, '❌ Жертв с монетами на руках не найдено!', show_alert=True
            )
            return

        if random.choice([True, False]):
            stolen = int(target[2] * random.uniform(0.1, 0.3))
            p['coins'] += stolen

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
                f'🥷 Вы успешно украли {stolen} 🪙 у {target[1]}!',
                show_alert=True,
            )
        else:
            bot.answer_callback_query(
                call.id, '🚨 Ограбление провалилось!', show_alert=True
            )

    elif call.data == 'menu_boss':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT hp, max_hp FROM boss WHERE id = 1')
        hp, max_hp = c.fetchone()
        conn.close()

        hp_bar = make_progress_bar(hp, max_hp, length=10)
        pct = int((hp / max_hp) * 100) if max_hp > 0 else 0

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                '💥 Ударить Босса!', callback_data='attack_boss'
            ),
            InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            f'👹 **МИРОВОЙ БОСС**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'❤️ HP: [`{hp_bar}`] **{pct}%** ({hp}/{max_hp})\n\n'
            f'💥 Награда в **50 000 🪙** разделится между всеми участниками!',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode='Markdown',
        )

    elif call.data == 'attack_boss':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT hp, damage_log FROM boss WHERE id = 1')
        hp, log_raw = c.fetchone()
        damage_log = json.loads(log_raw)

        if hp <= 0:
            bot.answer_callback_query(
                call.id, '🎉 Босс уже повержен!', show_alert=True
            )
            conn.close()
            return

        dmg = p['power']
        new_hp = max(0, hp - dmg)
        damage_log[str(p['user_id'])] = (
            damage_log.get(str(p['user_id']), 0) + dmg
        )

        if new_hp == 0:
            total_dmg = sum(damage_log.values())
            for uid, user_dmg in damage_log.items():
                reward = int((user_dmg / total_dmg) * 50000)
                c.execute(
                    'UPDATE players SET coins = coins + ? WHERE user_id = ?',
                    (reward, int(uid)),
                )
            c.execute(
                'UPDATE boss SET hp = 100000, damage_log = "{}" WHERE id = 1'
            )
            bot.send_message(
                call.message.chat.id,
                '🎉 **БОСС ПОВЕРЖЕН!** Выплаты за урон распределены!',
            )
        else:
            c.execute(
                'UPDATE boss SET hp = ?, damage_log = ? WHERE id = 1',
                (new_hp, json.dumps(damage_log)),
            )

        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f'💥 Нанесено -{dmg} урона!')

    # --- 🟪 ТОП БОГАЧЕЙ ---
    elif call.data == 'menu_top':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'SELECT name, coins FROM players ORDER BY coins DESC LIMIT 10'
        )
        rows = c.fetchall()
        conn.close()

        text = '🟪 **ТОП-10 САМЫХ БОГАТЫХ ИГРОКОВ:**\n\n'
        for i, r in enumerate(rows, 1):
            text += f'{i}. {r[0]} — **{r[1]}** 🪙\n'

        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_kb(),
            parse_mode='Markdown',
        )

    # --- 🟩 ПРОМОКОД ---
    elif call.data == 'menu_promo':
        msg = bot.send_message(
            call.message.chat.id, '🔑 Введите ваш промокод:'
        )
        bot.register_next_step_handler(msg, process_use_promo)

    # --- 👑 АДМИН-ПАНЕЛЬ ---
    elif call.data == 'menu_admin':
        if p['user_id'] not in ADMIN_IDS:
            return

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(
                '📊 Общая Экономика', callback_data='adm_stats'
            ),
            InlineKeyboardButton('💰 Выдать / Забрать', callback_data='adm_money'),
            InlineKeyboardButton(
                '📢 Рассылка Всем', callback_data='adm_broadcast'
            ),
            InlineKeyboardButton('🔨 Бан / Разбан ID', callback_data='adm_ban'),
            InlineKeyboardButton(
                '🎁 Создать Промокод', callback_data='adm_create_promo'
            ),
            InlineKeyboardButton(
                '👹 Сбросить Босса', callback_data='adm_reset_boss'
            ),
            InlineKeyboardButton('⬛ ⬅️ Назад', callback_data='menu_main'),
        )
        bot.edit_message_text(
            '👑 **УПРАВЛЕНИЕ БОТОМ (АДМИНКА)**',
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
        r = c.fetchone()
        conn.close()

        bot.edit_message_text(
            f'📊 **СТАТИСТИКА ЭКОНОМИКИ:**\n\n'
            f'👥 Игроков: **{r[0]}**\n'
            f'💰 Всего монет: **{(r[1] or 0) + (r[2] or 0) + (r[3] or 0)}** 🪙',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_kb(),
            parse_mode='Markdown',
        )

    elif call.data == 'adm_money':
        msg = bot.send_message(
            call.message.chat.id,
            'Укажите ID игрока и сумму монет через пробел (Пример: `123456'
            ' 5000`):',
        )
        bot.register_next_step_handler(msg, process_adm_money)

    elif call.data == 'adm_broadcast':
        msg = bot.send_message(
            call.message.chat.id, 'Введите текст для рассылки всем игрокам:'
        )
        bot.register_next_step_handler(msg, process_adm_broadcast)

    elif call.data == 'adm_ban':
        msg = bot.send_message(
            call.message.chat.id, 'Введите Telegram ID для бана/разбана:'
        )
        bot.register_next_step_handler(msg, process_adm_ban)

    elif call.data == 'adm_create_promo':
        msg = bot.send_message(
            call.message.chat.id,
            'Формат создания промокода: `КОД СУММА ЛИМИТ` (Пример: `START'
            ' 1000 50`)',
        )
        bot.register_next_step_handler(msg, process_create_promo)

    elif call.data == 'adm_reset_boss':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('UPDATE boss SET hp = 100000, damage_log = "{}" WHERE id = 1')
        conn.commit()
        conn.close()
        bot.answer_callback_query(
            call.id, '✅ HP Босса восстановлено!', show_alert=True
        )


# ==========================================
# 7. РЕНДЕР ИГРЫ МИНЫ И ОБРАБОТЧИКИ ВВОДА
# ==========================================
def render_mines_game(message, user_id):
    session = mines_sessions[user_id]
    kb = InlineKeyboardMarkup(row_width=3)
    btns = []

    for i in range(9):
        if session['opened'][i]:
            btns.append(
                InlineKeyboardButton('💎', callback_data=f'mine_open_{i}')
            )
        else:
            btns.append(
                InlineKeyboardButton('🟩', callback_data=f'mine_open_{i}')
            )

    kb.add(*btns)
    if session['step'] > 0:
        win = int(session['bet'] * session['mult'])
        kb.add(
            InlineKeyboardButton(
                f'💰 Забрать {win} 🪙 (x{round(session["mult"], 1)})',
                callback_data='mines_take',
            )
        )

    bot.edit_message_text(
        f'💣 **ИГРА "МИНЫ"**\nКликайте по клеткам, избегая мин!\nМножитель:'
        f' **x{round(session["mult"], 1)}**',
        message.chat.id,
        message.message_id,
        reply_markup=kb,
        parse_mode='Markdown',
    )


def process_use_promo(message):
    code_text = message.text.strip()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM promo_codes WHERE code = ?', (code_text,))
    row = c.fetchone()

    if not row:
        bot.reply_to(message, '❌ Промокод не существует!')
        conn.close()
        return

    used_users = json.loads(row[4])
    if message.from_user.id in used_users:
        bot.reply_to(message, '❌ Вы уже активировали этот промокод!')
        conn.close()
        return

    if row[3] >= row[2]:
        bot.reply_to(message, '❌ Закончился лимит активаций промокода!')
        conn.close()
        return

    reward = row[1]
    used_users.append(message.from_user.id)
    c.execute(
        'UPDATE promo_codes SET used_count = used_count + 1, used_users = ?'
        ' WHERE code = ?',
        (json.dumps(used_users), code_text),
    )
    c.execute(
        'UPDATE players SET coins = coins + ? WHERE user_id = ?',
        (reward, message.from_user.id),
    )
    conn.commit()
    conn.close()

    bot.reply_to(message, f'🎉 Промокод успешно активирован! +{reward} 🪙!')


def process_adm_money(message):
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
        bot.reply_to(
            message, f'✅ Баланс игрока `{target_id}` изменён на `{amount}` 🪙!'
        )
    except Exception:
        bot.reply_to(
            message, '⚠️ Ошибка ввода! Используйте формат: `ID СУММА`'
        )


def process_adm_broadcast(message):
    text = message.text
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT user_id FROM players')
    users = c.fetchall()
    conn.close()

    count = 0
    for u in users:
        try:
            bot.send_message(
                u[0], f'📢 **ОБЪЯВЛЕНИЕ:**\n\n{text}', parse_mode='Markdown'
            )
            count += 1
            time.sleep(0.05)
        except Exception:
            pass
    bot.reply_to(message, f'✅ Рассылка отправлена {count} игрокам!')


def process_adm_ban(message):
    try:
        target_id = int(message.text.strip())
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'SELECT is_banned FROM players WHERE user_id = ?', (target_id,)
        )
        row = c.fetchone()
        if not row:
            bot.reply_to(message, '❌ Игрок не найден!')
            conn.close()
            return

        new_status = 0 if row[0] == 1 else 1
        c.execute(
            'UPDATE players SET is_banned = ? WHERE user_id = ?',
            (new_status, target_id),
        )
        conn.commit()
        conn.close()

        status_str = 'забанен' if new_status == 1 else 'разбанен'
        bot.reply_to(message, f'✅ Игрок `{target_id}` успешно {status_str}!')
    except Exception:
        bot.reply_to(message, '⚠️ Ошибка ввода ID!')


def process_create_promo(message):
    try:
        code, reward, max_uses = message.text.split()
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'INSERT INTO promo_codes (code, reward, max_uses) VALUES (?, ?,'
            ' ?)',
            (code, int(reward), int(max_uses)),
        )
        conn.commit()
        conn.close()
        bot.reply_to(
            message, f'✅ Промокод `{code}` на {reward} 🪙 создан!'
        )
    except Exception:
        bot.reply_to(message, '⚠️ Формат: `КОД СУММА ЛИМИТ`')


# ==========================================
# 8. ЗАПУСК БОТА
# ==========================================
if __name__ == '__main__':
    keep_alive()

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass

    print('🚀 Полноценный Бот Запущен!')

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            time.sleep(3)