import json
import os
import random
import sqlite3
import time
from threading import Thread
from flask import Flask
import telebot

# Попытка импорта psycopg2 для работы с PostgreSQL
try:
    import psycopg2

    HAS_PG = True
except ImportError:
    HAS_PG = False

# --- 1. ВЕБ-СЕРВЕР DLYA RENDER (KEEP-ALIVE) ---
app = Flask('')


@app.route('/')
def home():
    return 'Мега-Бот запущен и работает со ВСЕМ функционалом!'


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()


# --- 2. ИНИЦИАЛИЗАЦИЯ И БАЗА ДАННЫХ ---
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
DATABASE_URL = os.environ.get('DATABASE_URL')


def get_db_connection():
    if DATABASE_URL and HAS_PG:
        conn = psycopg2.connect(DATABASE_URL)
        return conn, 'pg'
    else:
        conn = sqlite3.connect('bot_database.db')
        return conn, 'sqlite'


def init_db():
    conn, db_type = get_db_connection()
    c = conn.cursor()

    if db_type == 'pg':
        c.execute('''
            CREATE TABLE IF NOT EXISTS players (
                user_id BIGINT PRIMARY KEY,
                name TEXT,
                coins BIGINT DEFAULT 100,
                bank BIGINT DEFAULT 0,
                power INT DEFAULT 1,
                rep INT DEFAULT 0,
                status TEXT DEFAULT 'Игрок',
                last_rob BIGINT DEFAULT 0,
                last_daily BIGINT DEFAULT 0,
                daily_streak INT DEFAULT 0,
                last_work BIGINT DEFAULT 0,
                last_rep BIGINT DEFAULT 0,
                last_collect BIGINT DEFAULT 0,
                last_bank_interest BIGINT DEFAULT 0,
                businesses TEXT DEFAULT '{"coffee":0, "startup":0, "mining":0}',
                inventory TEXT DEFAULT '[]',
                pet TEXT DEFAULT 'None',
                clan_id INT DEFAULT 0,
                quests TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS clans (
                clan_id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                owner_id BIGINT,
                bank BIGINT DEFAULT 0,
                boss_hp INT DEFAULT 50000
            );

            CREATE TABLE IF NOT EXISTS market (
                lot_id SERIAL PRIMARY KEY,
                seller_id BIGINT,
                item_name TEXT,
                price BIGINT
            );
        ''')
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                coins INTEGER DEFAULT 100,
                bank INTEGER DEFAULT 0,
                power INTEGER DEFAULT 1,
                rep INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Игрок',
                last_rob INTEGER DEFAULT 0,
                last_daily INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_work INTEGER DEFAULT 0,
                last_rep INTEGER DEFAULT 0,
                last_collect INTEGER DEFAULT 0,
                last_bank_interest INTEGER DEFAULT 0,
                businesses TEXT DEFAULT '{"coffee":0, "startup":0, "mining":0}',
                inventory TEXT DEFAULT '[]',
                pet TEXT DEFAULT 'None',
                clan_id INTEGER DEFAULT 0,
                quests TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS clans (
                clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                owner_id INTEGER,
                bank INTEGER DEFAULT 0,
                boss_hp INTEGER DEFAULT 50000
            );
            CREATE TABLE IF NOT EXISTS market (
                lot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER,
                item_name TEXT,
                price INTEGER
            );
        ''')

    conn.commit()
    conn.close()


init_db()

# Оперативные данные в памяти
bounties = {}  # {target_id: reward}
airdrop_active = {'active': False, 'code': '', 'reward': 0}
active_math = {'active': False, 'answer': None, 'reward': 300}
lottery_tickets = []

BUSINESSES = {
    'coffee': {'name': 'Кофейня', 'cost': 1000, 'income': 100},
    'startup': {'name': 'IT-Стартап', 'cost': 10000, 'income': 1500},
    'mining': {'name': 'Сеть майнинг-ферм', 'cost': 100000, 'income': 20000},
}

PETS = {
    'cat': {'name': '🐱 Геймерский Кот', 'cost': 2000, 'feed_cost': 100},
    'dragon': {'name': '🐉 Дракончик', 'cost': 15000, 'feed_cost': 500},
}

CASES = {
    'обычный': {
        'cost': 500,
        'drop': [
            ('100 🪙', 100),
            ('500 🪙', 500),
            ('🐱 Кот', 'cat'),
            ('Ничего', 0),
        ],
    }
}


# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def get_player(user_id, name):
    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    c.execute(f'SELECT * FROM players WHERE user_id = {ph}', (user_id,))
    row = c.fetchone()

    if not row:
        default_quests = json.dumps({
            'date': time.strftime('%Y-%m-%d'),
            'clicks': 0,
            'duels': 0,
            'feed': 0,
            'claimed': False,
        })
        c.execute(
            f'''
            INSERT INTO players (user_id, name, quests) 
            VALUES ({ph}, {ph}, {ph})
        ''',
            (user_id, name, default_quests),
        )
        conn.commit()
        c.execute(f'SELECT * FROM players WHERE user_id = {ph}', (user_id,))
        row = c.fetchone()

    conn.close()

    return {
        'user_id': row[0],
        'name': row[1],
        'coins': row[2],
        'bank': row[3],
        'power': row[4],
        'rep': row[5],
        'status': row[6],
        'last_rob': row[7],
        'last_daily': row[8],
        'daily_streak': row[9],
        'last_work': row[10],
        'last_rep': row[11],
        'last_collect': row[12],
        'last_bank_interest': row[13],
        'businesses': json.loads(row[14]),
        'inventory': json.loads(row[15]),
        'pet': json.loads(row[16]) if row[16] != 'None' else None,
        'clan_id': row[17],
        'quests': json.loads(row[18]),
    }


def save_player(p):
    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    c.execute(
        f'''
        UPDATE players SET
            name = {ph}, coins = {ph}, bank = {ph}, power = {ph}, rep = {ph}, status = {ph},
            last_rob = {ph}, last_daily = {ph}, daily_streak = {ph}, last_work = {ph},
            last_rep = {ph}, last_collect = {ph}, last_bank_interest = {ph},
            businesses = {ph}, inventory = {ph}, pet = {ph}, clan_id = {ph}, quests = {ph}
        WHERE user_id = {ph}
    ''',
        (
            p['name'],
            p['coins'],
            p['bank'],
            p['power'],
            p['rep'],
            p['status'],
            p['last_rob'],
            p['last_daily'],
            p['daily_streak'],
            p['last_work'],
            p['last_rep'],
            p['last_collect'],
            p['last_bank_interest'],
            json.dumps(p['businesses']),
            json.dumps(p['inventory']),
            json.dumps(p['pet']) if p['pet'] else 'None',
            p['clan_id'],
            json.dumps(p['quests']),
            p['user_id'],
        ),
    )
    conn.commit()
    conn.close()


def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False


# --- СПРАВКА И СТАРТ ---
@bot.message_handler(commands=['start', 'help'])
def start(message):
    text = (
        '🔥 **ПОЛНЫЙ МЕГА-ИГРОВОЙ БОТ** 🔥\n\n'
        '🎮 **Заработок:**\n'
        '🔹 `/click` — майнить монеты\n'
        '🔹 `/daily` — ежедневная награда\n'
        '🔹 `/work` — пойти работать\n'
        '🔹 `/balance` / `/top` — профиль и топ игроков\n\n'
        '💼 **Бизнес и Инвентарь:**\n'
        '🔹 `/business` — купить бизнес\n'
        '🔹 `/collect` — собрать доход\n'
        '🔹 `/inventory` — инвентарь и питомцы\n'
        '🔹 `/feed` — покормить питомца\n'
        '🔹 `/case` — открыть кейс (500 🪙)\n\n'
        '🏦 **Банк и Рынок:**\n'
        '🔹 `/bank` / `/deposit` / `/withdraw` — управление банком\n'
        '🔹 `/market` — просмотр рынка\n'
        '🔹 `/sell <предмет> <цена>` — выставить лот\n'
        '🔹 `/buy_item <ID>` — купить лот\n\n'
        '🎲 **Мини-игры и Социал:**\n'
        '🔹 `/dice`, `/slots`, `/darts`, `/casino <ставка>` — азартные игры\n'
        '🔹 `/duel` — дуэль (ответом)\n'
        '🔹 `/rob` — ограбление (ответом)\n'
        '🔹 `/rep` — плюс карме (ответом)\n'
        '🔹 `/bounty <@юзер> <сумма>` — заказ на игрока\n'
        '🔹 `/math` — пример на скорость\n'
        '🔹 `/ticket` — билет лотереи (50 🪙)\n\n'
        '🛡 **Кланы и Квесты:**\n'
        '🔹 `/clan_create <имя>` / `/clan_boss` — клановые активности\n'
        '🔹 `/quests` — квесты дня\n\n'
        '👑 `/airdrop <сумма> <код>` / `/claim <code>`'
    )
    bot.reply_to(message, text, parse_mode='Markdown')


# --- ОСНОВНЫЕ КОМАНДЫ (DAILY, WORK, CLICK) ---
@bot.message_handler(commands=['click'])
def click(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += p['power']

    today = time.strftime('%Y-%m-%d')
    if p['quests'].get('date') == today:
        p['quests']['clicks'] = p['quests'].get('clicks', 0) + 1

    save_player(p)
    bot.reply_to(
        message,
        f"⚡ +{p['power']} монет! Баланс: **{p['coins']}** 🪙",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['daily'])
def daily(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()

    if now - p['last_daily'] < 86400:
        wait = int((86400 - (now - p['last_daily'])) / 3600)
        bot.reply_to(
            message,
            f'⏳ Ежедневный бонус можно забрать через **{wait} ч.**',
            parse_mode='Markdown',
        )
        return

    p['daily_streak'] = (
        p['daily_streak'] + 1 if (now - p['last_daily']) < 172800 else 1
    )
    p['last_daily'] = now
    reward = 500 + (p['daily_streak'] * 100)
    p['coins'] += reward
    save_player(p)

    bot.reply_to(
        message,
        f"🎁 Ежедневный бонус забран! Вы получили **{reward}** 🪙! (Стрик: {p['daily_streak']} дн.)",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['work'])
def work(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()

    if now - p['last_work'] < 3600:
        wait = int((3600 - (now - p['last_work'])) / 60)
        bot.reply_to(message, f'⏳ Следующая смена через {wait} мин.')
        return

    salary = random.randint(200, 800)
    p['coins'] += salary
    p['last_work'] = now
    save_player(p)
    bot.reply_to(
        message,
        f'🛠 Вы отлично поработали и заработали **{salary}** 🪙!',
        parse_mode='Markdown',
    )


# --- РИНЕК И ИНВЕНТАРЬ ---
@bot.message_handler(commands=['inventory'])
def inventory(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    inv = ', '.join(p['inventory']) if p['inventory'] else 'Пусто'
    pet = (
        PETS[p['pet']['type']]['name']
        if p['pet'] and 'type' in p['pet']
        else 'Нет'
    )

    bot.reply_to(
        message,
        f"🎒 **Инвентарь {p['name']}:**\n📦 Предметы: {inv}\n🐾 Питомец: {pet}",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['sell'])
def sell_item(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        _, item, price = message.text.split()
        price = int(price)
    except Exception:
        bot.reply_to(
            message,
            '⚠️ Формат: `/sell <предмет> <цена>` (Пример: `/sell Меч 1000`)',
            parse_mode='Markdown',
        )
        return

    if item not in p['inventory']:
        bot.reply_to(message, '❌ У вас нет этого предмета в инвентаре!')
        return

    p['inventory'].remove(item)
    save_player(p)

    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'
    c.execute(
        f'INSERT INTO market (seller_id, item_name, price) VALUES ({ph}, {ph}, {ph})',
        (p['user_id'], item, price),
    )
    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        f'✅ Предмет **{item}** выставлен на рынок за **{price}** 🪙!',
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['market'])
def show_market(message):
    conn, _ = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT lot_id, item_name, price FROM market LIMIT 10')
    lots = c.fetchall()
    conn.close()

    if not lots:
        bot.reply_to(message, '🏪 Рынок пока пуст!')
        return

    text = '🏪 **Рынок предметов:**\n\n'
    for lot in lots:
        text += f'🔹 ID `{lot[0]}`: **{lot[1]}** — {lot[2]} 🪙\n'
    text += '\nКупить: `/buy_item <ID>`'
    bot.reply_to(message, text, parse_mode='Markdown')


@bot.message_handler(commands=['buy_item'])
def buy_item(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        lot_id = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, '⚠️ Пример: `/buy_item 1`')
        return

    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    c.execute(
        f'SELECT lot_id, seller_id, item_name, price FROM market WHERE lot_id = {ph}',
        (lot_id,),
    )
    lot = c.fetchone()

    if not lot:
        conn.close()
        bot.reply_to(message, '❌ Лот не найден!')
        return

    _, seller_id, item_name, price = lot

    if p['coins'] < price:
        conn.close()
        bot.reply_to(message, '❌ Недостаточно средств!')
        return

    p['coins'] -= price
    p['inventory'].append(item_name)
    save_player(p)

    # Перевод денег продавцу
    seller = get_player(seller_id, 'Продавец')
    seller['coins'] += price
    save_player(seller)

    c.execute(f'DELETE FROM market WHERE lot_id = {ph}', (lot_id,))
    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        f'🎉 Вы купили **{item_name}** за **{price}** 🪙!',
        parse_mode='Markdown',
    )


# --- БИЗНЕС, ПИТОМЦЫ И КЕЙСЫ ---
@bot.message_handler(commands=['business'])
def business(message):
    text = '💼 **Список бизнесов:**\n\n'
    for k, v in BUSINESSES.items():
        text += f"🔹 `{k}`: {v['name']} | Цена: {v['cost']} 🪙 | Доход: {v['income']}/ч\n"
    text += '\nКупить: `/buy_biz <код>`'
    bot.reply_to(message, text, parse_mode='Markdown')


@bot.message_handler(commands=['buy_biz'])
def buy_biz(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        biz = message.text.split()[1]
    except Exception:
        bot.reply_to(message, '⚠️ Укажите бизнес: `/buy_biz coffee`')
        return

    if biz not in BUSINESSES:
        bot.reply_to(message, '❌ Такого бизнеса нет!')
        return

    b = BUSINESSES[biz]
    if p['coins'] < b['cost']:
        bot.reply_to(message, '❌ Недостаточно монет!')
        return

    p['coins'] -= b['cost']
    p['businesses'][biz] = p['businesses'].get(biz, 0) + 1
    save_player(p)
    bot.reply_to(
        message,
        f"🎉 Вы купили **{b['name']}**!",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['collect'])
def collect(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()
    hours = (now - p['last_collect']) / 3600

    if hours < 1:
        bot.reply_to(
            message, '⏳ Собирать доход можно не чаще 1 раза в час!'
        )
        return

    total = 0
    for biz_code, count in p['businesses'].items():
        if biz_code in BUSINESSES:
            total += int(BUSINESSES[biz_code]['income'] * count * hours)

    p['coins'] += total
    p['last_collect'] = now
    save_player(p)

    bot.reply_to(
        message,
        f'💵 Вы собрали **{total}** 🪙 дохода с ваших бизнесов!',
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['case'])
def open_case(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    cost = CASES['обычный']['cost']

    if p['coins'] < cost:
        bot.reply_to(message, '❌ Открытие кейса стоит 500 🪙!')
        return

    p['coins'] -= cost
    drop_name, drop_val = random.choice(CASES['обычный']['drop'])

    if isinstance(drop_val, int):
        p['coins'] += drop_val
    elif drop_val == 'cat':
        p['pet'] = {'type': 'cat', 'fed': time.time()}

    save_player(p)
    bot.reply_to(
        message,
        f'🎁 Из кейса вам выпало: **{drop_name}**!',
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['feed'])
def feed_pet(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if not p['pet']:
        bot.reply_to(message, '❌ У вас нет питомца!')
        return

    p_type = p['pet'].get('type', 'cat')
    cost = PETS[p_type]['feed_cost']

    if p['coins'] < cost:
        bot.reply_to(message, f'❌ Корм стоит {cost} 🪙!')
        return

    p['coins'] -= cost
    p['pet']['fed'] = time.time()
    save_player(p)
    bot.reply_to(
        message,
        f"🐾 Вы покормили {PETS[p_type]['name']}!",
        parse_mode='Markdown',
    )


# --- ДУЭЛИ, КАРМА И МИНИ-ИГРЫ ---
@bot.message_handler(commands=['duel'])
def duel(message):
    if not message.reply_to_message:
        bot.reply_to(message, '⚠️ Ответьте этой командой сопернику!')
        return

    p1 = get_player(message.from_user.id, message.from_user.first_name)
    p2 = get_player(
        message.reply_to_message.from_user.id,
        message.reply_to_message.from_user.first_name,
    )

    winner, loser = (p1, p2) if random.random() < 0.5 else (p2, p1)
    prize = 200
    winner['coins'] += prize
    save_player(winner)

    bot.reply_to(
        message,
        f"⚔️ В дуэли победил **{winner['name']}** и забрал **{prize}** 🪙!",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['rep'])
def rep(message):
    if not message.reply_to_message:
        bot.reply_to(message, '⚠️ Ответьте пользователю!')
        return

    if message.reply_to_message.from_user.id == message.from_user.id:
        bot.reply_to(message, '❌ Нельзя менять карму себе!')
        return

    target = get_player(
        message.reply_to_message.from_user.id,
        message.reply_to_message.from_user.first_name,
    )
    target['rep'] += 1
    save_player(target)
    bot.reply_to(
        message,
        f"✨ Вы подняли карму {target['name']}! (Карма: {target['rep']})",
    )


@bot.message_handler(commands=['math'])
def math_game(message):
    global active_math
    a, b = random.randint(10, 99), random.randint(10, 99)
    active_math = {'active': True, 'answer': a + b, 'reward': 300}
    bot.reply_to(
        message,
        f'🧮 Решите пример на скорость: `{a} + {b}`\nОтвет отправьте сообщением!',
        parse_mode='Markdown',
    )


@bot.message_handler(
    func=lambda m: active_math['active']
    and m.text.isdigit()
    and int(m.text) == active_math['answer']
)
def check_math(message):
    global active_math
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += active_math['reward']
    save_player(p)

    bot.reply_to(
        message,
        f"🎉 Правильно! **{p['name']}** забирает **{active_math['reward']}** 🪙!",
        parse_mode='Markdown',
    )
    active_math['active'] = False


# --- КЛАНЫ И КВЕСТЫ ---
@bot.message_handler(commands=['clan_create'])
def clan_create(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        c_name = message.text.split()[1]
    except Exception:
        bot.reply_to(message, '⚠️ Укажите название: `/clan_create Империя`')
        return

    if p['coins'] < 50000:
        bot.reply_to(message, '❌ Создание клана стоит 50 000 🪙!')
        return

    p['coins'] -= 50000
    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    try:
        c.execute(
            f'INSERT INTO clans (name, owner_id) VALUES ({ph}, {ph})',
            (c_name, p['user_id']),
        )
        conn.commit()
        bot.reply_to(
            message,
            f'🛡 Клан **{c_name}** создан!',
            parse_mode='Markdown',
        )
    except Exception:
        bot.reply_to(message, '❌ Клан с таким именем уже существует!')
    finally:
        conn.close()
        save_player(p)


@bot.message_handler(commands=['quests'])
def quests(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    q = p['quests']
    bot.reply_to(
        message,
        f"📜 **Ежедневные Квесты:**\n\n⚡ Клики: {q.get('clicks', 0)}/50\n Награда за выполнение: 1000 🪙",
        parse_mode='Markdown',
    )


# --- КЛИЕНТ АИРДРОПОВ ---
@bot.message_handler(commands=['airdrop'])
def airdrop(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, '❌ Доступно только админам!')
        return

    try:
        _, reward, code = message.text.split()
        global airdrop_active
        airdrop_active = {
            'active': True,
            'code': code,
            'reward': int(reward),
        }
        bot.send_message(
            message.chat.id,
            f'📦 **СБРОШЕН АИРДРОП!**\n\nНаграда: **{reward}** 🪙\nНапишите `/claim {code}`, чтобы забрать!',
            parse_mode='Markdown',
        )
    except Exception:
        bot.reply_to(message, '⚠️ Формат: `/airdrop 1000 секрет`')


@bot.message_handler(commands=['claim'])
def claim_airdrop(message):
    global airdrop_active
    if not airdrop_active['active']:
        bot.reply_to(message, '❌ Сейчас нет активного аирдропа.')
        return

    try:
        code = message.text.split()[1]
        if code == airdrop_active['code']:
            p = get_player(message.from_user.id, message.from_user.first_name)
            p['coins'] += airdrop_active['reward']
            save_player(p)

            bot.reply_to(
                message,
                f"🎁 Вы забили Аирдроп на **{airdrop_active['reward']}** 🪙!",
                parse_mode='Markdown',
            )
            airdrop_active['active'] = False
        else:
            bot.reply_to(message, '❌ Неверный код!')
    except Exception:
        bot.reply_to(message, '⚠️ Введите код: `/claim <code>`')


# --- СБРОС И ЗАПУСК ---
if __name__ == '__main__':
    keep_alive()

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass

    print('🚀 Полный Бот запущен!')

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f'⚠️ Ошибка сети: {e}')
            time.sleep(3)
