import os
import random
import sqlite3
import time
from threading import Thread
from flask import Flask
import telebot

# --- 1. ВЕБ-СЕРВЕР ДЛЯ ВЕБХУКА / RENDER ---
app = Flask('')


@app.route('/')
def home():
    return 'Мега-Бот запущен и работает с SQLite!'


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()


# --- 2. ИНИЦИАЛИЗАЦИЯ И ИНИЦИАЛИЗАЦИЯ БД ---
TOKEN = os.environ.get('BOT_TOKEN', 'ВАШ_ТОКЕН_ЕСЛИ_ЛОКАЛЬНО')
bot = telebot.TeleBot(TOKEN)

DB_NAME = 'bot_database.db'


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Таблица игроков
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
        )
    ''')

    # Таблица кланов
    c.execute('''
        CREATE TABLE IF NOT EXISTS clans (
            clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            owner_id INTEGER,
            bank INTEGER DEFAULT 0,
            boss_hp INTEGER DEFAULT 50000
        )
    ''')

    # Таблица рынка
    c.execute('''
        CREATE TABLE IF NOT EXISTS market (
            lot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER,
            item_name TEXT,
            price INTEGER
        )
    ''')

    conn.commit()
    conn.close()


init_db()

# Оперативные данные в памяти
bounties = {}  # {target_id: reward}
airdrop_active = {'active': False, 'code': '', 'reward': 0}
active_math = {'active': False, 'answer': None, 'reward': 300}

BUSINESSES = {
    'coffee': {'name': 'Кофейня', 'cost': 1000, 'income': 100},
    'startup': {'name': 'IT-Стартап', 'cost': 10000, 'income': 1500},
    'mining': {'name': 'Сеть майнинг-ферм', 'cost': 100000, 'income': 20000},
}

PETS = {
    'cat': {'name': '🐱 Геймерский Кот', 'cost': 2000, 'feed_cost': 100},
    'dragon': {'name': '🐉 Дракончик', 'cost': 15000, 'feed_cost': 500},
}


# --- ХЕЛПЕРЫ ДЛЯ РАБОТЫ С БД ---
def get_db_connection():
    return sqlite3.connect(DB_NAME)


def get_player(user_id, name):
    import json

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
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
            '''
            INSERT INTO players (user_id, name, quests) 
            VALUES (?, ?, ?)
        ''',
            (user_id, name, default_quests),
        )
        conn.commit()
        c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        row = c.fetchone()

    conn.close()

    p = {
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
    return p


def save_player(p):
    import json

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        '''
        UPDATE players SET
            name = ?, coins = ?, bank = ?, power = ?, rep = ?, status = ?,
            last_rob = ?, last_daily = ?, daily_streak = ?, last_work = ?,
            last_rep = ?, last_collect = ?, last_bank_interest = ?,
            businesses = ?, inventory = ?, pet = ?, clan_id = ?, quests = ?
        WHERE user_id = ?
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


# --- 3. СТАРТ И СПРАВКА ---
@bot.message_handler(commands=['start', 'help'])
def start(message):
    text = (
        '🔥 **МЕГА-ИГРОВОЙ БОТ (ВЕРСИЯ С БД)** 🔥\n\n'
        '🎮 **Экономика и Прогресс:**\n'
        '🔹 `/click` — майнить монеты\n'
        '🔹 `/balance` — профиль и счет\n'
        '🔹 `/bank` — управление депозитом в банке (+2% в день)\n'
        '🔹 `/rob` — попробовать ограбить игрока\n'
        '🔹 `/daily` — ежедневный бонус\n'
        '🔹 `/work` — пойти на работу\n\n'
        '🎲 **Телеграм-Азарт:**\n'
        '🔹 `/dice <ставка>` — бросок кубика\n'
        '🔹 `/slots <ставка>` — крутить слоты 🎰\n'
        '🔹 `/darts <ставка>` — дартс 🎯\n\n'
        '🛡 **Кланы и Банды:**\n'
        '🔹 `/clan` — инфо о клане / управление\n'
        '🔹 `/clan_create <имя>` — создать клан (50 000 🪙)\n'
        '🔹 `/clan_boss` — атаковать босса клана\n\n'
        '📜 **Квесты и Рынок:**\n'
        '🔹 `/quests` — ежедневные задания\n'
        '🔹 `/market` — рынок предметов чата\n'
        '🔹 `/sell <предмет> <цена>` — выставить на рынок\n'
        '🔹 `/buy_item <ID_лота>` — купить с рынка'
    )
    bot.reply_to(message, text, parse_mode='Markdown')


# --- КЛИКЕР, ПРОФИЛЬ, ГРАБЕЖ ---
@bot.message_handler(commands=['click'])
def click(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += p['power']

    # Прогресс квеста "Клики"
    today = time.strftime('%Y-%m-%d')
    if p['quests'].get('date') == today:
        p['quests']['clicks'] = p['quests'].get('clicks', 0) + 1

    save_player(p)
    bot.reply_to(
        message,
        f"⚡ +{p['power']} монет! Баланс: **{p['coins']}** 🪙",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['balance'])
def balance(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    pet_info = (
        PETS[p['pet']['type']]['name']
        if p['pet'] and 'type' in p['pet']
        else 'Нет'
    )

    text = (
        f"📊 **Профиль {p['name']}:**\n"
        f"🏷 Статус: **{p['status']}**\n"
        f"💰 Монет на руках: **{p['coins']}** 🪙\n"
        f"🏦 В банке: **{p['bank']}** 🪙\n"
        f"⚡ Сила клика: **{p['power']}**\n"
        f"🔮 Карма: **{p['rep']}**\n"
        f'🐾 Питомец: **{pet_info}**'
    )
    bot.reply_to(message, text, parse_mode='Markdown')


@bot.message_handler(commands=['rob'])
def rob(message):
    if not message.reply_to_message:
        bot.reply_to(
            message, '⚠️ Ответьте этой командой на сообщение жертвы!'
        )
        return

    p1 = get_player(message.from_user.id, message.from_user.first_name)
    p2 = get_player(
        message.reply_to_message.from_user.id,
        message.reply_to_message.from_user.first_name,
    )

    if p1['user_id'] == p2['user_id']:
        bot.reply_to(message, '❌ Нельзя грабить самого себя!')
        return

    now = time.time()
    if now - p1['last_rob'] < 3600:
        bot.reply_to(message, '⏳ Грабить можно не чаще раза в час!')
        return

    p1['last_rob'] = now

    if 'Щит от грабежа' in p2['inventory']:
        p2['inventory'].remove('Щит от грабежа')
        save_player(p1)
        save_player(p2)
        bot.reply_to(
            message,
            f"🛡 У **{p2['name']}** сработал **Щит от грабежа**! Ограбление провалено.",
            parse_mode='Markdown',
        )
        return

    if p2['coins'] < 100:
        bot.reply_to(
            message,
            f"💰 У **{p2['name']}** слишком мало монет на руках! (Монеты в банке защищены)",
            parse_mode='Markdown',
        )
        save_player(p1)
        return

    if random.random() < 0.5:
        stolen = random.randint(10, int(p2['coins'] * 0.3))
        p2['coins'] -= stolen
        p1['coins'] += stolen
        save_player(p1)
        save_player(p2)
        bot.reply_to(
            message,
            f"🥷 Успех! Вы украли **{stolen}** 🪙 у **{p2['name']}**!",
            parse_mode='Markdown',
        )
    else:
        fine = 200
        p1['coins'] = max(0, p1['coins'] - fine)
        save_player(p1)
        bot.reply_to(
            message,
            f'🚨 Вас поймала полиция! Вы заплатили штраф **{fine}** 🪙.',
            parse_mode='Markdown',
        )


# --- 1. БАНК И ДЕПОЗИТЫ ---
@bot.message_handler(commands=['bank'])
def bank_info(message):
    p = get_player(message.from_user.id, message.from_user.first_name)

    # Начисление 2% за каждые 24ч
    now = time.time()
    if p['bank'] > 0 and (now - p['last_bank_interest']) >= 86400:
        p['bank'] = int(p['bank'] * 1.02)
        p['last_bank_interest'] = now
        save_player(p)

    text = (
        f"🏦 **Центральный Банк**\n\n"
        f"💰 На вашем счете: **{p['bank']}** 🪙\n"
        f"📈 Начисляемый процент: **+2% в сутки**\n"
        f"🛡 *Монеты в банке полностью защищены от `/rob`!*\n\n"
        f"Пополнить: `/deposit <сумма>`\n"
        f"Снять: `/withdraw <сумма>`"
    )
    bot.reply_to(message, text, parse_mode='Markdown')


@bot.message_handler(commands=['deposit'])
def deposit(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        amount = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, '⚠️ Укажите сумму. Пример: `/deposit 500`')
        return

    if amount <= 0 or p['coins'] < amount:
        bot.reply_to(message, '❌ Недостаточно наличных монет!')
        return

    p['coins'] -= amount
    p['bank'] += amount
    save_player(p)
    bot.reply_to(
        message,
        f'🏦 Вы положили **{amount}** 🪙 в банк! Баланс банка: **{p["bank"]}** 🪙',
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['withdraw'])
def withdraw(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        amount = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, '⚠️ Укажите сумму. Пример: `/withdraw 500`')
        return

    if amount <= 0 or p['bank'] < amount:
        bot.reply_to(message, '❌ Недостаточно средств в банке!')
        return

    p['bank'] -= amount
    p['coins'] += amount
    save_player(p)
    bot.reply_to(
        message,
        f'💵 Вы сняли **{amount}** 🪙 со счета! На руках: **{p["coins"]}** 🪙',
        parse_mode='Markdown',
    )


# --- 2. ИГРЫ С АНИМИРОВАННЫМИ КУБИКАМИ TELEGRAM ---
@bot.message_handler(commands=['dice', 'slots', 'darts'])
def play_tg_dice(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    cmd = message.text.split()[0].replace('/', '')

    try:
        bet = int(message.text.split()[1])
    except Exception:
        bot.reply_to(
            message,
            f'⚠️ Укажите ставку! Пример: `/{cmd} 100`',
            parse_mode='Markdown',
        )
        return

    if bet <= 0 or p['coins'] < bet:
        bot.reply_to(message, '❌ Недостаточно средств!')
        return

    p['coins'] -= bet
    save_player(p)

    emoji_map = {'dice': '🎲', 'slots': '🎰', 'darts': '🎯'}

    msg = bot.send_dice(message.chat.id, emoji=emoji_map[cmd])
    val = msg.dice.value
    time.sleep(2)  # Ждем завершения анимации

    win = 0
    if cmd == 'dice':
        if val >= 4:
            win = int(bet * 1.8)
    elif cmd == 'darts':
        if val == 6:  # Попадание в яблочко
            win = bet * 3
        elif val >= 4:
            win = int(bet * 1.3)
    elif cmd == 'slots':
        if val in [1, 22, 43, 64]:  # Три одинаковых символа в слотах Telegram
            win = bet * 7

    if win > 0:
        p['coins'] += win
        save_player(p)
        bot.reply_to(
            message,
            f'🎉 Результат: {val}! Вы выиграли **+{win}** 🪙!',
            parse_mode='Markdown',
        )
    else:
        bot.reply_to(
            message,
            f'Увы, результат: {val}. Вы проиграли {bet} 🪙.',
            parse_mode='Markdown',
        )


# --- 3. КЛАНЫ И БАНДЫ ---
@bot.message_handler(commands=['clan_create'])
def clan_create(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['clan_id'] != 0:
        bot.reply_to(message, '❌ Вы уже состоите в клане!')
        return

    try:
        clan_name = message.text.split(maxsplit=1)[1]
    except Exception:
        bot.reply_to(message, '⚠️ Пример: `/clan_create НазваниеКлана`')
        return

    if p['coins'] < 50000:
        bot.reply_to(message, '❌ Создание клана стоит 50 000 🪙!')
        return

    p['coins'] -= 50000

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            'INSERT INTO clans (name, owner_id) VALUES (?, ?)',
            (clan_name, p['user_id']),
        )
        clan_id = c.lastrowid
        conn.commit()
        p['clan_id'] = clan_id
        save_player(p)
        bot.reply_to(
            message,
            f'🛡 Клан **{clan_name}** успешно создан!',
            parse_mode='Markdown',
        )
    except sqlite3.IntegrityError:
        bot.reply_to(message, '❌ Клан с таким названием уже существует!')
    finally:
        conn.close()


@bot.message_handler(commands=['clan_boss'])
def clan_boss(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['clan_id'] == 0:
        bot.reply_to(message, '❌ Вы не состоите в клане!')
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'SELECT name, boss_hp FROM clans WHERE clan_id = ?', (p['clan_id'],)
    )
    clan = c.fetchone()

    if not clan:
        conn.close()
        return

    damage = random.randint(100, 500) * p['power']
    new_hp = max(0, clan[1] - damage)

    if new_hp == 0:
        c.execute(
            'UPDATE clans SET boss_hp = 50000 WHERE clan_id = ?',
            (p['clan_id'],),
        )
        p['coins'] += 10000
        save_player(p)
        bot.reply_to(
            message,
            f"⚔️ Вы нанесли **{damage}** урона и повергли Босса! Награда: **+10 000** 🪙 всем Участникам!",
            parse_mode='Markdown',
        )
    else:
        c.execute(
            'UPDATE clans SET boss_hp = ? WHERE clan_id = ?',
            (new_hp, p['clan_id']),
        )
        bot.reply_to(
            message,
            f'⚔️ Удар по Клановому Боссу! Нанесено: **{damage}** урона. У Босса осталось HP: **{new_hp}**.',
            parse_mode='Markdown',
        )

    conn.commit()
    conn.close()


# --- 4. ЕЖЕДНЕВНЫЕ КВЕСТЫ ---
@bot.message_handler(commands=['quests'])
def show_quests(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    today = time.strftime('%Y-%m-%d')

    q = p['quests']
    if q.get('date') != today:
        q = {'date': today, 'clicks': 0, 'duels': 0, 'feed': 0, 'claimed': False}
        p['quests'] = q
        save_player(p)

    status_c = '✅' if q['clicks'] >= 50 else f"{q['clicks']}/50"
    status_d = '✅' if q['duels'] >= 2 else f"{q['duels']}/2"
    status_f = '✅' if q['feed'] >= 1 else f"{q['feed']}/1"

    text = (
        f"📜 **Ежедневные квесты для {p['name']}:**\n\n"
        f"1. Сделать 50 кликов (`/click`): [{status_c}]\n"
        f"2. Сыграть 2 дуэли (`/duel`): [{status_d}]\n"
        f"3. Покормить питомца (`/feed`): [{status_f}]\n\n"
    )

    if q['clicks'] >= 50 and q['duels'] >= 2 and q['feed'] >= 1:
        if not q['claimed']:
            p['coins'] += 3000
            q['claimed'] = True
            save_player(p)
            text += "🎉 **Поздравляем! Вы получили бонус +3000 🪙 за выполнение всех квестов!**"
        else:
            text += '🎁 Награда за сегодня уже получена!'
    else:
        text += '💡 Выполните все задания, чтобы получить 3 000 🪙!'

    bot.reply_to(message, text, parse_mode='Markdown')


# --- 5. РЫНОК И ТОРГОВЛЯ ---
@bot.message_handler(commands=['sell'])
def sell_item(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    args = message.text.split(maxsplit=2)

    if len(args) < 3:
        bot.reply_to(
            message,
            '⚠️ Формат: `/sell <название_предмета> <цена>`',
            parse_mode='Markdown',
        )
        return

    item_name = args[1]
    try:
        price = int(args[2])
    except ValueError:
        bot.reply_to(message, '❌ Цена должна быть числом!')
        return

    if item_name not in p['inventory']:
        bot.reply_to(message, '❌ У вас нет этого предмета в инвентаре!')
        return

    p['inventory'].remove(item_name)
    save_player(p)

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'INSERT INTO market (seller_id, item_name, price) VALUES (?, ?, ?)',
        (p['user_id'], item_name, price),
    )
    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        f'🏪 Предмет **{item_name}** выставлен на рынок за **{price}** 🪙!',
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['market'])
def market_list(message):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT lot_id, item_name, price FROM market LIMIT 10')
    lots = c.fetchall()
    conn.close()

    if not lots:
        bot.reply_to(message, '🏪 Рынок пока пуст!')
        return

    text = '🏪 **Рынок предметов:**\n\n'
    for lot in lots:
        text += f"📦 Лот `#{lot[0]}`: **{lot[1]}** — Цена: **{lot[2]}** 🪙\n"
    text += '\nКупить предмет: `/buy_item <ID_лота>`'

    bot.reply_to(message, text, parse_mode='Markdown')


@bot.message_handler(commands=['buy_item'])
def buy_item(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        lot_id = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, '⚠️ Укажите ID лота! Пример: `/buy_item 1`')
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'SELECT lot_id, seller_id, item_name, price FROM market WHERE lot_id = ?',
        (lot_id,),
    )
    lot = c.fetchone()

    if not lot:
        conn.close()
        bot.reply_to(message, '❌ Лот не найден!')
        return

    seller_id, item_name, price = lot[1], lot[2], lot[3]

    if p['coins'] < price:
        conn.close()
        bot.reply_to(message, '❌ Недостаточно средств!')
        return

    # Транзакция
    p['coins'] -= price
    p['inventory'].append(item_name)
    save_player(p)

    seller = get_player(seller_id, 'Продавец')
    seller['coins'] += price
    save_player(seller)

    c.execute('DELETE FROM market WHERE lot_id = ?', (lot_id,))
    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        f'🎉 Вы успешно купили **{item_name}** за **{price}** 🪙!',
        parse_mode='Markdown',
    )


# --- ДУЭЛИ И ПРОЧИЕ СЕКЦИИ ---
@bot.message_handler(commands=['duel'])
def duel(message):
    if not message.reply_to_message:
        bot.reply_to(
            message, '⚠️ Пишите `/duel` ответом на сообщение оппонента!'
        )
        return

    p1 = get_player(message.from_user.id, message.from_user.first_name)
    p2 = get_player(
        message.reply_to_message.from_user.id,
        message.reply_to_message.from_user.first_name,
    )

    if p1['user_id'] == p2['user_id']:
        return

    winner, loser = (
        (p1, p2) if random.choice([True, False]) else (p2, p1)
    )
    prize = 150

    winner['coins'] += prize

    # Фиксация квеста
    today = time.strftime('%Y-%m-%d')
    if p1['quests'].get('date') == today:
        p1['quests']['duels'] = p1['quests'].get('duels', 0) + 1
    if p2['quests'].get('date') == today:
        p2['quests']['duels'] = p2['quests'].get('duels', 0) + 1

    save_player(p1)
    save_player(p2)

    bot.reply_to(
        message,
        f"⚔️ **ДУЭЛЬ!**\n🏆 **{winner['name']}** одолел **{loser['name']}** и забрал **+{prize}** 🪙!",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['feed'])
def feed(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if not p['pet']:
        bot.reply_to(message, '❌ У вас нет питомца!')
        return

    cost = PETS[p['pet']['type']]['feed_cost']
    if p['coins'] >= cost:
        p['coins'] -= cost
        p['pet']['fed_time'] = time.time()

        today = time.strftime('%Y-%m-%d')
        if p['quests'].get('date') == today:
            p['quests']['feed'] = p['quests'].get('feed', 0) + 1

        save_player(p)
        bot.reply_to(
            message, f'🍖 Вы покормили питомца за {cost} 🪙! Бонусы активны.'
        )
    else:
        bot.reply_to(message, f'❌ Не хватает {cost} 🪙 на кормежку!')


# --- ЗАПУСК БОТА ---
keep_alive()
bot.polling(none_stop=True)
