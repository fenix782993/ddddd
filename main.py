import json
import os
import random
import sqlite3
import time
from threading import Thread
from flask import Flask
import telebot

# Попытка импорта psycopg2 для работы с PostgreSQL на Render
try:
    import psycopg2
    HAS_PG = True
except ImportError:
    HAS_PG = False

# --- 1. ВЕБ-СЕРВЕР ДЛЯ RENDER (KEEP-ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return 'Мега-Бот запущен и работает с Облачной БД!'

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

SHOP_ITEMS = {
    'меч': {'name': '⚔️ Силовой Меч', 'cost': 1500, 'power': 5},
    'кирка': {'name': '⛏️ Алмазная Кирка', 'cost': 5000, 'power': 20},
    'щит': {'name': '🛡️ Защитный Щит', 'cost': 3000, 'power': 0}
}

BUSINESSES = {
    'coffee': {'name': '☕ Кофейня', 'cost': 1000, 'income': 100},
    'startup': {'name': '💻 IT-Стартап', 'cost': 10000, 'income': 1500},
    'mining': {'name': '🖥️ Сеть майнинг-ферм', 'cost': 100000, 'income': 20000}
}

PETS = {
    'cat': {'name': '🐱 Геймерский Кот', 'cost': 2000, 'feed_cost': 100},
    'dragon': {'name': '🐉 Дракончик', 'cost': 15000, 'feed_cost': 500}
}

CASES = {
    'обычный': {
        'cost': 500,
        'drop': [('100 🪙', 100), ('500 🪙', 500), ('🐱 Кот', 'cat'), ('Ничего', 0)]
    }
}

# --- 3. ФУНКЦИИ БАЗЫ ДАННЫХ ---
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
            'claimed': False
        })
        c.execute(f'''
            INSERT INTO players (user_id, name, quests) 
            VALUES ({ph}, {ph}, {ph})
        ''', (user_id, name, default_quests))
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
        'quests': json.loads(row[18])
    }

def save_player(p):
    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    c.execute(f'''
        UPDATE players SET
            name = {ph}, coins = {ph}, bank = {ph}, power = {ph}, rep = {ph}, status = {ph},
            last_rob = {ph}, last_daily = {ph}, daily_streak = {ph}, last_work = {ph},
            last_rep = {ph}, last_collect = {ph}, last_bank_interest = {ph},
            businesses = {ph}, inventory = {ph}, pet = {ph}, clan_id = {ph}, quests = {ph}
        WHERE user_id = {ph}
    ''', (
        p['name'], p['coins'], p['bank'], p['power'], p['rep'], p['status'],
        p['last_rob'], p['last_daily'], p['daily_streak'], p['last_work'],
        p['last_rep'], p['last_collect'], p['last_bank_interest'],
        json.dumps(p['businesses']), json.dumps(p['inventory']),
        json.dumps(p['pet']) if p['pet'] else 'None', p['clan_id'],
        json.dumps(p['quests']), p['user_id']
    ))
    conn.commit()
    conn.close()

def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False

# --- 4. СПРАВКА И ПРОФИЛЬ ---
@bot.message_handler(commands=['start', 'help'])
def start(message):
    text = (
        '🔥 **ПОЛНЫЙ МЕГА-ИГРОВОЙ БОТ** 🔥\n\n'
        '🎮 **Заработок и Профиль:**\n'
        '🔹 `/click` — майнить монеты\n'
        '🔹 `/balance` — ваш профиль\n'
        '🔹 `/top` — топ богачей сервера\n'
        '🔹 `/daily` — ежедневная награда\n'
        '🔹 `/work` — пойти работать\n\n'
        '🏪 **Магазины и Торговля:**\n'
        '🔹 `/shop` — официальный магазин системных предметов\n'
        '🔹 `/buy <предмет>` — купить системный предмет\n'
        '🔹 `/market` — рынок между игроками\n'
        '🔹 `/sell <предмет> <цена>` — выставить лот на рынок\n'
        '🔹 `/buy_item <ID>` — купить лот с рынка\n\n'
        '💼 **Бизнес и Инвентарь:**\n'
        '🔹 `/business` / `/buy_biz <код>` — покупка бизнеса\n'
        '🔹 `/collect` — забрать доход бизнесов\n'
        '🔹 `/inventory` — инвентарь и питомцы\n'
        '🔹 `/feed` — покормить питомца\n'
        '🔹 `/case` — открыть кейс (500 🪙)\n\n'
        '🏦 **Банк:**\n'
        '🔹 `/bank` / `/deposit <сумма>` / `/withdraw <сумма>`\n\n'
        '🎲 **Мини-игры и Социал:**\n'
        '🔹 `/dice`, `/slots`, `/darts`, `/casino <ставка>` / `/roulette <ставка>`\n'
        '🔹 `/duel` — дуэль с игроком (ответом)\n'
        '🔹 `/rob` — ограбить игрока (ответом)\n'
        '🔹 `/rep` — поднять карму (ответом)\n'
        '🔹 `/bounty <@юзер> <сумма>` — заказ на игрока\n'
        '🔹 `/math` — пример на скорость\n'
        '🔹 `/ticket` — купить лотерейный билет (50 🪙)\n\n'
        '🛡 **Кланы, Боссы и Квесты:**\n'
        '🔹 `/clan_create <имя>` — создать клан\n'
        '🔹 `/clan_boss` — просмотр босса\n'
        '🔹 `/boss_attack` — атаковать кланового босса\n'
        '🔹 `/quests` — ежедневные квесты\n\n'
        '👑 `/airdrop <сумма> <код>` / `/claim <code>`'
    )
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['balance'])
def balance(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    pet_info = PETS[p['pet']['type']]['name'] if p['pet'] and 'type' in p['pet'] else 'Нет'

    text = (
        f"📊 **Профиль {p['name']}:**\n"
        f"🏷 Статус: **{p['status']}**\n"
        f"💰 Монет на руках: **{p['coins']}** 🪙\n"
        f"🏦 В банке: **{p['bank']}** 🪙\n"
        f"⚡ Сила клика: **{p['power']}**\n"
        f"🔮 Карма: **{p['rep']}**\n"
        f"🐾 Питомец: **{pet_info}**"
    )
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['top'])
def top_players(message):
    conn, _ = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, coins + bank AS total FROM players ORDER BY total DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(message, "🏆 Таблица лидеров пока пуста!")
        return

    text = "🏆 **ТОП-10 БОГАЧЕЙ СЕРВЕРА:**\n\n"
    for idx, row in enumerate(rows, 1):
        text += f"{idx}. **{row[0]}** — {row[1]} 🪙\n"

    bot.reply_to(message, text, parse_mode='Markdown')

# --- 5. ЗАРАБОТОК И РАБОТА ---
@bot.message_handler(commands=['click'])
def click(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += p['power']

    today = time.strftime('%Y-%m-%d')
    if p['quests'].get('date') == today:
        p['quests']['clicks'] = p['quests'].get('clicks', 0) + 1

    save_player(p)
    bot.reply_to(message, f"⚡ +{p['power']} монет! Баланс: **{p['coins']}** 🪙", parse_mode='Markdown')

@bot.message_handler(commands=['daily'])
def daily(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()

    if now - p['last_daily'] < 86400:
        wait = int((86400 - (now - p['last_daily'])) / 3600)
        bot.reply_to(message, f"⏳ Ежедневный бонус можно забрать через **{wait} ч.**", parse_mode='Markdown')
        return

    p['daily_streak'] = p['daily_streak'] + 1 if (now - p['last_daily']) < 172800 else 1
    p['last_daily'] = now
    reward = 500 + (p['daily_streak'] * 100)
    p['coins'] += reward
    save_player(p)

    bot.reply_to(message, f"🎁 Ежедневный бонус забран! +**{reward}** 🪙! (Стрик: {p['daily_streak']} дн.)", parse_mode='Markdown')

@bot.message_handler(commands=['work'])
def work(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()

    if now - p['last_work'] < 3600:
        wait = int((3600 - (now - p['last_work'])) / 60)
        bot.reply_to(message, f"⏳ Следующая смена через {wait} мин.")
        return

    salary = random.randint(200, 800)
    p['coins'] += salary
    p['last_work'] = now
    save_player(p)
    bot.reply_to(message, f"🛠 Вы отлично поработали и заработали **{salary}** 🪙!", parse_mode='Markdown')

# --- 6. БАНК ---
@bot.message_handler(commands=['bank'])
def bank_info(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()

    if p['bank'] > 0 and (now - p['last_bank_interest']) >= 86400:
        p['bank'] = int(p['bank'] * 1.02)
        p['last_bank_interest'] = now
        save_player(p)

    bot.reply_to(message, f"🏦 **Центральный Банк**\n\n💰 Счет: **{p['bank']}** 🪙\n📈 Процент: **+2% в сутки**\n\nПоложить: `/deposit <сумма>`\nСнять: `/withdraw <сумма>`", parse_mode='Markdown')

@bot.message_handler(commands=['deposit'])
def deposit(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    args = message.text.split()

    if len(args) < 2 or not args[1].isdigit():
        bot.reply_to(message, "⚠️ Пример: `/deposit 500`", parse_mode='Markdown')
        return

    amount = int(args[1])
    if amount <= 0 or p['coins'] < amount:
        bot.reply_to(message, "❌ Недостаточно монет на руках!")
        return

    p['coins'] -= amount
    p['bank'] += amount
    save_player(p)
    bot.reply_to(message, f"🏦 Депозит пополнен на **{amount}** 🪙! В банке: **{p['bank']}** 🪙", parse_mode='Markdown')

@bot.message_handler(commands=['withdraw'])
def withdraw(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    args = message.text.split()

    if len(args) < 2 or not args[1].isdigit():
        bot.reply_to(message, "⚠️ Пример: `/withdraw 500`", parse_mode='Markdown')
        return

    amount = int(args[1])
    if amount <= 0 or p['bank'] < amount:
        bot.reply_to(message, "❌ Недостаточно средств в банке!")
        return

    p['bank'] -= amount
    p['coins'] += amount
    save_player(p)
    bot.reply_to(message, f"💵 Вы сняли **{amount}** 🪙! На руках: **{p['coins']}** 🪙", parse_mode='Markdown')

# --- 7. МАГАДЗИНЫ, РЫНОК И ИНВЕНТАРЬ ---
@bot.message_handler(commands=['shop'])
def show_shop(message):
    text = "🏪 **Официальный магазин предметов:**\n\n"
    for k, v in SHOP_ITEMS.items():
        text += f"🔹 `{k}`: {v['name']} | Цена: **{v['cost']}** 🪙 | Сила: +{v['power']}\n"
    text += "\nКупить: `/buy <код>` (например: `/buy меч`)"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['buy'])
def buy_shop(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    args = message.text.split()

    if len(args) < 2:
        bot.reply_to(message, "⚠️ Укажите предмет: `/buy меч`", parse_mode='Markdown')
        return

    item_code = args[1].lower()
    if item_code not in SHOP_ITEMS:
        bot.reply_to(message, "❌ Такого предмета нет в магазине! Смотрите `/shop`")
        return

    item = SHOP_ITEMS[item_code]
    if p['coins'] < item['cost']:
        bot.reply_to(message, "❌ Недостаточно монет!")
        return

    p['coins'] -= item['cost']
    p['power'] += item['power']
    p['inventory'].append(item['name'])
    save_player(p)

    bot.reply_to(message, f"🎉 Вы успешно купили **{item['name']}**!", parse_mode='Markdown')

@bot.message_handler(commands=['inventory'])
def inventory(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    inv = ", ".join(p['inventory']) if p['inventory'] else "Пусто"
    pet = PETS[p['pet']['type']]['name'] if p['pet'] and 'type' in p['pet'] else "Нет"

    bot.reply_to(message, f"🎒 **Инвентарь {p['name']}:**\n📦 Предметы: {inv}\n🐾 Питомец: {pet}", parse_mode='Markdown')

@bot.message_handler(commands=['sell'])
def sell_item(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        _, item, price = message.text.split()
        price = int(price)
    except Exception:
        bot.reply_to(message, "⚠️ Формат: `/sell <предмет> <цена>`", parse_mode='Markdown')
        return

    if item not in p['inventory']:
        bot.reply_to(message, "❌ У вас нет этого предмета в инвентаре!")
        return

    p['inventory'].remove(item)
    save_player(p)

    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'
    c.execute(f"INSERT INTO market (seller_id, item_name, price) VALUES ({ph}, {ph}, {ph})", (p['user_id'], item, price))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"✅ Предмет **{item}** выставлен на рынок за **{price}** 🪙!", parse_mode='Markdown')

@bot.message_handler(commands=['market'])
def show_market(message):
    conn, _ = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT lot_id, item_name, price FROM market LIMIT 10")
    lots = c.fetchall()
    conn.close()

    if not lots:
        bot.reply_to(message, "🏪 Рынок пока пуст!")
        return

    text = "🏪 **Рынок предметов (Игрок-Игрок):**\n\n"
    for lot in lots:
        text += f"🔹 ID `{lot[0]}`: **{lot[1]}** — {lot[2]} 🪙\n"
    text += "\nКупить: `/buy_item <ID>`"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['buy_item'])
def buy_item(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        lot_id = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "⚠️ Пример: `/buy_item 1`", parse_mode='Markdown')
        return

    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    c.execute(f"SELECT lot_id, seller_id, item_name, price FROM market WHERE lot_id = {ph}", (lot_id,))
    lot = c.fetchone()

    if not lot:
        conn.close()
        bot.reply_to(message, "❌ Лот не найден!")
        return

    _, seller_id, item_name, price = lot

    if p['coins'] < price:
        conn.close()
        bot.reply_to(message, "❌ Недостаточно средств!")
        return

    p['coins'] -= price
    p['inventory'].append(item_name)
    save_player(p)

    seller = get_player(seller_id, "Продавец")
    seller['coins'] += price
    save_player(seller)

    c.execute(f"DELETE FROM market WHERE lot_id = {ph}", (lot_id,))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"🎉 Вы купили **{item_name}** за **{price}** 🪙!", parse_mode='Markdown')

# --- 8. БИЗНЕСЫ, ПИТОМЦЫ И КЕЙСЫ ---
@bot.message_handler(commands=['business'])
def business(message):
    text = "💼 **Список бизнесов:**\n\n"
    for k, v in BUSINESSES.items():
        text += f"🔹 `{k}`: {v['name']} | Цена: {v['cost']} 🪙 | Доход: {v['income']}/ч\n"
    text += "\nКупить: `/buy_biz <код>` (например: `/buy_biz coffee`)"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['buy_biz'])
def buy_biz(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        biz = message.text.split()[1]
    except Exception:
        bot.reply_to(message, "⚠️ Укажите бизнес: `/buy_biz coffee`", parse_mode='Markdown')
        return

    if biz not in BUSINESSES:
        bot.reply_to(message, "❌ Такого бизнеса нет!")
        return

    b = BUSINESSES[biz]
    if p['coins'] < b['cost']:
        bot.reply_to(message, "❌ Недостаточно монет!")
        return

    p['coins'] -= b['cost']
    p['businesses'][biz] = p['businesses'].get(biz, 0) + 1
    save_player(p)
    bot.reply_to(message, f"🎉 Вы купили **{b['name']}**!", parse_mode='Markdown')

@bot.message_handler(commands=['collect'])
def collect(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()
    hours = (now - p['last_collect']) / 3600

    if hours < 1:
        bot.reply_to(message, "⏳ Собирать доход можно не чаще 1 раза в час!")
        return

    total = 0
    for biz_code, count in p['businesses'].items():
        if biz_code in BUSINESSES:
            total += int(BUSINESSES[biz_code]['income'] * count * hours)

    p['coins'] += total
    p['last_collect'] = now
    save_player(p)

    bot.reply_to(message, f"💵 Вы собрали **{total}** 🪙 дохода!", parse_mode='Markdown')

@bot.message_handler(commands=['case'])
def open_case(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    cost = CASES['обычный']['cost']

    if p['coins'] < cost:
        bot.reply_to(message, "❌ Открытие кейса стоит 500 🪙!")
        return

    p['coins'] -= cost
    drop_name, drop_val = random.choice(CASES['обычный']['drop'])

    if isinstance(drop_val, int):
        p['coins'] += drop_val
    elif drop_val == 'cat':
        p['pet'] = {'type': 'cat', 'fed': time.time()}

    save_player(p)
    bot.reply_to(message, f"🎁 Из кейса вам выпало: **{drop_name}**!", parse_mode='Markdown')

@bot.message_handler(commands=['feed'])
def feed_pet(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if not p['pet']:
        bot.reply_to(message, "❌ У вас нет питомца!")
        return

    p_type = p['pet'].get('type', 'cat')
    cost = PETS[p_type]['feed_cost']

    if p['coins'] < cost:
        bot.reply_to(message, f"❌ Корм стоит {cost} 🪙!")
        return

    p['coins'] -= cost
    p['pet']['fed'] = time.time()
    save_player(p)
    bot.reply_to(message, f"🐾 Вы покормили {PETS[p_type]['name']}!", parse_mode='Markdown')

# --- 9. МИНИ-ИГРЫ И СОЦИАЛ ---
@bot.message_handler(commands=['dice', 'slots', 'darts'])
def play_dice(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    cmd = message.text.split()[0].replace('/', '')

    try:
        bet = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, f"⚠️ Укажите ставку! Пример: `/{cmd} 100`", parse_mode='Markdown')
        return

    if bet <= 0 or p['coins'] < bet:
        bot.reply_to(message, "❌ Недостаточно средств на руках!")
        return

    p['coins'] -= bet
    save_player(p)

    emoji_map = {'dice': '🎲', 'slots': '🎰', 'darts': '🎯'}
    msg = bot.send_dice(message.chat.id, emoji=emoji_map[cmd])
    time.sleep(3)

    val = msg.dice.value
    win = 0
    if cmd == 'dice' and val >= 4:
        win = bet * 2
    elif cmd == 'slots' and val in [1, 22, 43, 64]:
        win = bet * 5
    elif cmd == 'darts' and val == 6:
        win = bet * 3

    if win > 0:
        p['coins'] += win
        bot.reply_to(message, f"🎉 **Победа!** Вы выиграли **{win}** 🪙!", parse_mode='Markdown')
    else:
        bot.reply_to(message, "😢 Увы, ставка не сыграла.")

    save_player(p)

@bot.message_handler(commands=['casino', 'roulette'])
def casino(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        bet = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "⚠️ Укажите ставку: `/casino 100`", parse_mode='Markdown')
        return

    if bet <= 0 or p['coins'] < bet:
        bot.reply_to(message, "❌ Недостаточно монет!")
        return

    p['coins'] -= bet
    if random.random() < 0.45:
        win = bet * 2
        p['coins'] += win
        bot.reply_to(message, f"🎰 **Победа!** Вы получили **{win}** 🪙!", parse_mode='Markdown')
    else:
        bot.reply_to(message, "💥 Ставка проиграна!")

    save_player(p)

@bot.message_handler(commands=['duel'])
def duel(message):
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Ответьте этой командой сопернику!")
        return

    p1 = get_player(message.from_user.id, message.from_user.first_name)
    p2 = get_player(message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name)

    winner, loser = (p1, p2) if random.random() < 0.5 else (p2, p1)
    prize = 200
    winner['coins'] += prize
    save_player(winner)

    bot.reply_to(message, f"⚔️ В дуэли победил **{winner['name']}** и забрал **{prize}** 🪙!", parse_mode='Markdown')

@bot.message_handler(commands=['rob'])
def rob(message):
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Ответьте сообщением на игрока, которого хотите ограбить!")
        return

    thief = get_player(message.from_user.id, message.from_user.first_name)
    target = message.reply_to_message.from_user
    victim = get_player(target.id, target.first_name)

    now = time.time()
    if now - thief['last_rob'] < 3600:
        wait = int((3600 - (now - thief['last_rob'])) / 60)
        bot.reply_to(message, f"⏳ Грабить можно раз в час! Подождите {wait} мин.")
        return

    if victim['coins'] < 100:
        bot.reply_to(message, "❌ У этого игрока слишком мало монет на руках!")
        return

    thief['last_rob'] = now

    if random.random() < 0.5:
        stolen = random.randint(1, int(victim['coins'] * 0.4))
        victim['coins'] -= stolen
        thief['coins'] += stolen
        bot.reply_to(message, f"🥷 Успех! Вы украли **{stolen}** 🪙 у {victim['name']}!", parse_mode='Markdown')
    else:
        fine = random.randint(50, 200)
        thief['coins'] = max(0, thief['coins'] - fine)
        bot.reply_to(message, f"🚔 Вас поймали! Штраф: **{fine}** 🪙", parse_mode='Markdown')

    save_player(thief)
    save_player(victim)

@bot.message_handler(commands=['rep'])
def rep(message):
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Ответьте пользователю!")
        return

    if message.reply_to_message.from_user.id == message.from_user.id:
        bot.reply_to(message, "❌ Нельзя менять карму себе!")
        return

    target = get_player(message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name)
    target['rep'] += 1
    save_player(target)
    bot.reply_to(message, f"✨ Вы подняли карму {target['name']}! (Карма: {target['rep']})")

@bot.message_handler(commands=['bounty'])
def bounty(message):
    try:
        _, target, amount = message.text.split()
        amount = int(amount)
        p = get_player(message.from_user.id, message.from_user.first_name)

        if p['coins'] < amount:
            bot.reply_to(message, "❌ Недостаточно средств!")
            return

        p['coins'] -= amount
        save_player(p)
        bot.reply_to(message, f"🎯 Заказ на **{target}** за **{amount}** 🪙 оформлен!", parse_mode='Markdown')
    except Exception:
        bot.reply_to(message, "⚠️ Пример: `/bounty @юзер 1000`", parse_mode='Markdown')

@bot.message_handler(commands=['ticket'])
def ticket(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['coins'] < 50:
        bot.reply_to(message, "❌ Билет стоит 50 🪙!")
        return

    p['coins'] -= 50
    lottery_tickets.append(p['user_id'])
    save_player(p)
    bot.reply_to(message, "🎟️ Вы успешно купили лотерейный билет!")

@bot.message_handler(commands=['math'])
def math_game(message):
    global active_math
    a, b = random.randint(10, 99), random.randint(10, 99)
    active_math = {'active': True, 'answer': a + b, 'reward': 300}
    bot.reply_to(message, f"🧮 Решите пример на скорость: `{a} + {b}`", parse_mode='Markdown')

@bot.message_handler(func=lambda m: active_math['active'] and m.text.isdigit() and int(m.text) == active_math['answer'])
def check_math(message):
    global active_math
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += active_math['reward']
    save_player(p)

    bot.reply_to(message, f"🎉 Правильно! **{p['name']}** забрал **{active_math['reward']}** 🪙!", parse_mode='Markdown')
    active_math['active'] = False

# --- 10. КЛАНИ И БОССЫ ---
@bot.message_handler(commands=['clan_create'])
def clan_create(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        c_name = message.text.split()[1]
    except Exception:
        bot.reply_to(message, "⚠️ Укажите название: `/clan_create Империя`", parse_mode='Markdown')
        return

    if p['coins'] < 50000:
        bot.reply_to(message, "❌ Создание клана стоит 50 000 🪙!")
        return

    p['coins'] -= 50000
    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    try:
        c.execute(f"INSERT INTO clans (name, owner_id) VALUES ({ph}, {ph})", (c_name, p['user_id']))
        conn.commit()
        bot.reply_to(message, f"🛡 Клан **{c_name}** создан!", parse_mode='Markdown')
    except Exception:
        bot.reply_to(message, "❌ Клан с таким именем уже существует!")
    finally:
        conn.close()
        save_player(p)

@bot.message_handler(commands=['clan_boss'])
def clan_boss(message):
    p = get_player(message.from_user.id, message.from_user.first_name)

    if p['clan_id'] == 0:
        bot.reply_to(message, "❌ Вы не состоите в клане! Создайте клан: `/clan_create`", parse_mode='Markdown')
        return

    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    c.execute(f"SELECT name, boss_hp FROM clans WHERE clan_id = {ph}", (p['clan_id'],))
    clan = c.fetchone()
    conn.close()

    if not clan:
        bot.reply_to(message, "❌ Клан не найден!")
        return

    bot.reply_to(message, f"👹 **Босс Клана «{clan[0]}»**\n\n❤️ HP Босса: **{clan[1]} / 50000**\n\nАтаковать: `/boss_attack`", parse_mode='Markdown')

@bot.message_handler(commands=['boss_attack'])
def boss_attack(message):
    p = get_player(message.from_user.id, message.from_user.first_name)

    if p['clan_id'] == 0:
        bot.reply_to(message, "❌ Вы не состоите в клане!")
        return

    conn, db_type = get_db_connection()
    c = conn.cursor()
    ph = '%s' if db_type == 'pg' else '?'

    c.execute(f"SELECT boss_hp FROM clans WHERE clan_id = {ph}", (p['clan_id'],))
    clan = c.fetchone()

    if not clan or clan[0] <= 0:
        conn.close()
        bot.reply_to(message, "🎉 Босс клана уже повержен!")
        return

    damage = p['power'] * random.randint(5, 15)
    new_hp = max(0, clan[0] - damage)

    c.execute(f"UPDATE clans SET boss_hp = {ph} WHERE clan_id = {ph}", (new_hp, p['clan_id']))
    conn.commit()
    conn.close()

    reward = damage * 2
    p['coins'] += reward
    save_player(p)

    bot.reply_to(message, f"⚔️ Урон боссу: **{damage}**! Вы получили **{reward}** 🪙!\nОсталось HP: **{new_hp}**", parse_mode='Markdown')

@bot.message_handler(commands=['quests'])
def quests(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    q = p['quests']
    bot.reply_to(message, f"📜 **Ежедневные Квесты:**\n\n⚡ Клики: {q.get('clicks', 0)}/50\n Награда за выполнение: 1000 🪙", parse_mode='Markdown')

# --- 11. АИРДРОПЫ ---
@bot.message_handler(commands=['airdrop'])
def airdrop(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Доступно только админам!")
        return

    try:
        _, reward, code = message.text.split()
        global airdrop_active
        airdrop_active = {'active': True, 'code': code, 'reward': int(reward)}
        bot.send_message(
            message.chat.id,
            f"📦 **СБРОШЕН АИРДРОП!**\n\n Награда: **{reward}** 🪙\n Напишите `/claim {code}`, чтобы забрать!",
            parse_mode='Markdown'
        )
    except Exception:
        bot.reply_to(message, "⚠️ Пример: `/airdrop 1000 секрет`", parse_mode='Markdown')

@bot.message_handler(commands=['claim'])
def claim_airdrop(message):
    global airdrop_active
    if not airdrop_active['active']:
        bot.reply_to(message, "❌ Сейчас нет активного аирдропа.")
        return

    try:
        code = message.text.split()[1]
        if code == airdrop_active['code']:
            p = get_player(message.from_user.id, message.from_user.first_name)
            p['coins'] += airdrop_active['reward']
            save_player(p)

            bot.reply_to(message, f"🎁 Вы успели забрали Аирдроп на **{airdrop_active['reward']}** 🪙!", parse_mode='Markdown')
            airdrop_active['active'] = False
        else:
            bot.reply_to(message, "❌ Неверный код!")
    except Exception:
        bot.reply_to(message, "⚠️ Введите код: `/claim <code>`", parse_mode='Markdown')

# --- 12. СБРОС ВЕБХУКА И БЕЗОПАСНЫЙ ЗАПУСК ---
if __name__ == '__main__':
    keep_alive()

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass

    print("🚀 Полный Бот со всем функционалом успешно запущен!")

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"⚠️ Ошибка сети, рестарт: {e}")
            time.sleep(3)
