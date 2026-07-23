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

# --- 1. ВЕБ-СЕРВЕР ДЛЯ РЕНДЕРА (KEEP-ALIVE) ---
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
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS clans (
                clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                owner_id INTEGER,
                bank INTEGER DEFAULT 0,
                boss_hp INTEGER DEFAULT 50000
            );
        ''')
        c.execute('''
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

BUSINESSES = {
    'coffee': {'name': 'Кофейня', 'cost': 1000, 'income': 100},
    'startup': {'name': 'IT-Стартап', 'cost': 10000, 'income': 1500},
    'mining': {'name': 'Сеть майнинг-ферм', 'cost': 100000, 'income': 20000},
}

PETS = {
    'cat': {'name': '🐱 Геймерский Кот', 'cost': 2000, 'feed_cost': 100},
    'dragon': {'name': '🐉 Дракончик', 'cost': 15000, 'feed_cost': 500},
}


# --- УПРАВЛЕНИЕ ИГРОКАМИ В БД ---
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


# --- 3. СТАРТ И СПРАВКА ---
@bot.message_handler(commands=['start', 'help'])
def start(message):
    text = (
        '🔥 **МЕГА-ИГРОВОЙ БОТ (С ОБЛАЧНОЙ БД)** 🔥\n\n'
        '🎮 **Экономика и Прогресс:**\n'
        '🔹 `/click` — майнить монеты\n'
        '🔹 `/balance` — ваш профиль и статусы\n'
        '🔹 `/daily` — ежедневный бонус\n'
        '🔹 `/work` — пойти на работу\n'
        '🔹 `/rob` — ограбить игрока (ответом)\n\n'
        '🏦 **Банк и Торговля:**\n'
        '🔹 `/bank` — счет в банке (+2% в сутки, защита от `/rob`)\n'
        '🔹 `/deposit <сумма>` — положить монеты в банк\n'
        '🔹 `/withdraw <сумма>` — снять монеты\n'
        '🔹 `/market` — рынок предметов\n'
        '🔹 `/sell <предмет> <цена>` — выставить на рынок\n'
        '🔹 `/buy_item <ID>` — купить предмет\n\n'
        '🎲 **Анимированные игры Telegram:**\n'
        '🔹 `/dice <ставка>` — бросок кубика 🎲\n'
        '🔹 `/slots <ставка>` — анимированные слоты 🎰\n'
        '🔹 `/darts <ставка>` — дартс 🎯\n\n'
        '🛡 **Кланы и Квесты:**\n'
        '🔹 `/clan_create <имя>` — создать клан (50 000 🪙)\n'
        '🔹 `/clan_boss` — битва с боссом дня\n'
        '🔹 `/quests` — 3 ежедневных квеста\n\n'
        '👑 **Админам:**\n'
        '🔹 `/airdrop <сумма> <код>` — сброс аирдропа'
    )
    bot.reply_to(message, text, parse_mode='Markdown')


# --- КЛИКЕР И ПРОФИЛЬ ---
@bot.message_handler(commands=['click'])
def click(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += p['power']

    # Фиксация квеста
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
        f"🐾 Питомец: **{pet_info}**"
    )
    bot.reply_to(message, text, parse_mode='Markdown')


# --- БАНК И ДЕПОЗИТЫ ---
@bot.message_handler(commands=['bank'])
def bank_info(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()

    if p['bank'] > 0 and (now - p['last_bank_interest']) >= 86400:
        p['bank'] = int(p['bank'] * 1.02)
        p['last_bank_interest'] = now
        save_player(p)

    text = (
        f"🏦 **Центральный Банк**\n\n"
        f"💰 Счет: **{p['bank']}** 🪙\n"
        f"📈 Процент: **+2% в сутки**\n"
        f"🛡 *Деньги в банке защищены от `/rob`!*\n\n"
        f"Положить: `/deposit <сумма>`\n"
        f"Снять: `/withdraw <сумма>`"
    )
    bot.reply_to(message, text, parse_mode='Markdown')


@bot.message_handler(commands=['deposit'])
def deposit(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        amount = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, '⚠️ Пример: `/deposit 500`')
        return

    if amount <= 0 or p['coins'] < amount:
        bot.reply_to(message, '❌ Недостаточно монет на руках!')
        return

    p['coins'] -= amount
    p['bank'] += amount
    save_player(p)
    bot.reply_to(
        message,
        f'🏦 Депозит пополнен на **{amount}** 🪙! В банке: **{p["bank"]}** 🪙',
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['withdraw'])
def withdraw(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        amount = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, '⚠️ Пример: `/withdraw 500`')
        return

    if amount <= 0 or p['bank'] < amount:
        bot.reply_to(message, '❌ Недостаточно средств в банке!')
        return

    p['bank'] -= amount
    p['coins'] += amount
    save_player(p)
    bot.reply_to(
        message,
        f'💵 Вы сняли **{amount}** 🪙! На руках: **{p["coins"]}** 🪙',
        parse_mode='Markdown',
    )


# --- ИГРЫ TELEGRAM С АНИМАЦИЕЙ ---
@bot.message_handler(commands=['dice', 'slots', 'darts'])
def play_dice(message):
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
        bot.reply_to(message, '❌ Недостаточно средств на руках!')
        return

    p['coins'] -= bet
    save_player(p)

    emoji_map = {'dice': '🎲', 'slots': '🎰', 'darts': '🎯'}
    msg = bot.send_dice(message.chat.id, emoji=emoji_map[cmd])
    time.sleep(3)

    value = msg.dice.value

    # Расчет выигрыша
    win = 0
    if cmd == 'dice' and value >= 4:
        win = bet * 2
    elif cmd == 'slots' and value in [1, 22, 43, 64]:  # Выпадение 3х комбинаций
        win = bet * 5
    elif cmd == 'darts' and value == 6:  # Яблочко
        win = bet * 3

    if win > 0:
        p['coins'] += win
        bot.reply_to(
            message,
            f'🎉 **Победа!** Вы выиграли **{win}** 🪙!',
            parse_mode='Markdown',
        )
    else:
        bot.reply_to(message, '😢 Увы, ставка не сыграла.')

    save_player(p)


# --- ОГРАБЛЕНИЕ ---
@bot.message_handler(commands=['rob'])
def rob(message):
    if not message.reply_to_message:
        bot.reply_to(
            message,
            '⚠️ Ответьте этой командой на сообщение игрока, которого хотите ограбить!',
        )
        return

    thief = get_player(message.from_user.id, message.from_user.first_name)
    target_user = message.reply_to_message.from_user
    victim = get_player(target_user.id, target_user.first_name)

    now = time.time()
    if now - thief['last_rob'] < 3600:
        wait = int((3600 - (now - thief['last_rob'])) / 60)
        bot.reply_to(
            message, f'⏳ Грабить можно раз в час! Подождите {wait} мин.'
        )
        return

    if victim['coins'] < 100:
        bot.reply_to(message, '❌ У этого игрока слишком мало денег на руках!')
        return

    thief['last_rob'] = now

    if random.random() < 0.5:
        stolen = random.randint(1, int(victim['coins'] * 0.4))
        victim['coins'] -= stolen
        thief['coins'] += stolen
        bot.reply_to(
            message,
            f"🥷 Успех! Вы украли **{stolen}** 🪙 у {victim['name']}!",
            parse_mode='Markdown',
        )
    else:
        fine = random.randint(50, 200)
        thief['coins'] = max(0, thief['coins'] - fine)
        bot.reply_to(
            message,
            f'🚔 Вас поймали! Штраф за попытку ограбления: **{fine}** 🪙',
            parse_mode='Markdown',
        )

    save_player(thief)
    save_player(victim)


# --- АИРДРОП (АДМИН) ---
@bot.message_handler(commands=['airdrop'])
def airdrop(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, '❌ Эта команда доступна только админам!')
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
            f'📦 **СБРОШЕН АИРДРОП!**\n\n Награда: **{reward}** 🪙\n Напишите `/claim <code>`, чтобы забрать!',
            parse_mode='Markdown',
        )
    except Exception:
        bot.reply_to(message, '⚠️ Использование: `/airdrop 1000 секрет`')


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
                f"🎁 Вы успели забрали Аирдроп на **{airdrop_active['reward']}** 🪙!",
                parse_mode='Markdown',
            )
            airdrop_active['active'] = False
        else:
            bot.reply_to(message, '❌ Неверный код!')
    except Exception:
        bot.reply_to(message, '⚠️ Введите код: `/claim <code>`')


# --- БЕЗОПАСНЫЙ ЗАПУСК ПОЛЛИНГА С АВТОРЕСТАРТОМ ---
if __name__ == '__main__':
    keep_alive()

    # Сброс вебхука для предотвращения ошибки 409
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass

    print('🚀 Бот успешно запущен!')

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f'⚠️ Ошибка сети или конфликта, автопереподключение: {e}')
            time.sleep(3)
