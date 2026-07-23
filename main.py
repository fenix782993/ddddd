import os
import random
import time
from threading import Thread
from flask import Flask
import telebot

# --- 1. ВЕБ-СЕРВЕР ДЛЯ ВЕБХУКА / RENDER ---
app = Flask('')


@app.route('/')
def home():
    return 'Мега-Бот запущен и работает!'


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run)
    t.start()


# --- 2. ИНИЦИАЛИЗАЦИЯ И СТРУКТУРЫ ДАННЫХ ---
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Базы данных в памяти
players = {}
marriages = {}
bounties = {}  # {target_id: reward}
tickets = []  # список user_id, купивших билеты
airdrop_active = {'active': False, 'code': '', 'reward': 0}
active_math = {'active': False, 'answer': None, 'reward': 300}

# Константы
BUSINESSES = {
    'coffee': {'name': 'Кофейня', 'cost': 1000, 'income': 100},
    'startup': {'name': 'IT-Стартап', 'cost': 10000, 'income': 1500},
    'mining': {'name': 'Сеть майнинг-ферм', 'cost': 100000, 'income': 20000},
}

PETS = {
    'cat': {'name': '🐱 Геймерский Кот', 'cost': 2000, 'feed_cost': 100},
    'dragon': {'name': '🐉 Дракончик', 'cost': 15000, 'feed_cost': 500},
}


def get_player(user_id, name):
    if user_id not in players:
        players[user_id] = {
            'name': name,
            'coins': 100,
            'power': 1,
            'rep': 0,
            'last_rob': 0,
            'last_roulette': 0,
            'last_daily': 0,
            'daily_streak': 0,
            'last_work': 0,
            'last_rep': 0,
            'last_collect': 0,
            'businesses': {'coffee': 0, 'startup': 0, 'mining': 0},
            'inventory': [],
            'pet': None,  # {'type': 'cat', 'fed_time': time.time()}
            'status': 'Игрок',
        }
    else:
        players[user_id]['name'] = name
    return players[user_id]


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
        '🔥 **МЕГА-ИГРОВОЙ БОТ ДЛЯ ЧАТА!** 🔥\n\n'
        '🎮 **Экономика и Прогресс:**\n'
        '🔹 `/click` — майнить монеты\n'
        '🔹 `/balance` — профиль и статусы\n'
        '🔹 `/daily` — ежедневный бонус\n'
        '🔹 `/work` — пойти на работу\n'
        '🔹 `/shop` — улучшить кликер\n'
        '🔹 `/top` — топ богачей\n\n'
        '🏢 **Бизнес и Инвентарь:**\n'
        '🔹 `/business` — покупка бизнеса\n'
        '🔹 `/collect` — забрать доход от бизнеса\n'
        '🔹 `/inventory` — питомцы и инвентарь\n'
        '🔹 `/feed` — покормить питомца\n'
        '🔹 `/case` — открыть кейс (500 🪙)\n\n'
        '🎲 **Мини-игры и Активность:**\n'
        '🔹 `/ticket` — купить лотерейный билет (50 🪙)\n'
        '🔹 `/bounty <@юзер> <сумма>` — заказ на игрока\n'
        '🔹 `/duel` — дуэль (ответом на сообщение)\n'
        '🔹 `/casino <ставка>` / `/roulette` — азарт\n'
        '🔹 `/rep` — поднять карму (ответом)\n'
        '🔹 `/math` — запустить пример на скорость\n\n'
        '👑 **Для админов:**\n'
        '🔹 `/airdrop <сумма> <пароль>` — сброс аирдропа (Нужен пароль!)'
    )
    bot.reply_to(message, text, parse_mode='Markdown')


# --- КЛИКЕР И ПРОФИЛЬ ---


@bot.message_handler(commands=['click'])
def click(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += p['power']
    bot.reply_to(
        message,
        f"⚡ +{p['power']} монет! Баланс: **{p['coins']}** 🪙",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['balance'])
def balance(message):
    uid = message.from_user.id
    p = get_player(uid, message.from_user.first_name)
    spouse = marriages.get(uid, 'Один(очка)')
    pet_info = p['pet']['type'] if p['pet'] else 'Нет'

    text = (
        f"📊 **Профиль {p['name']}:**\n"
        f"🏷 Статус: **{p['status']}**\n"
        f"💰 Монет: **{p['coins']}** 🪙\n"
        f"⚡ Сила клика: **{p['power']}**\n"
        f"🔮 Карма (Репутация): **{p['rep']}**\n"
        f"🐾 Питомец: **{pet_info}**\n"
        f'💍 В браке с: **{spouse}**'
    )
    bot.reply_to(message, text, parse_mode='Markdown')


# --- 1. БИЗНЕСЫ И ПАССИВНЫЙ ДОХОД ---


@bot.message_handler(commands=['business'])
def business(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    args = message.text.split()

    if len(args) < 2:
        text = "🏢 **Бизнесы для покупки:**\n\n"
        text += (
            "1. `coffee` — Кофейня (1 000 🪙) -> 100 🪙/час\n"
            "2. `startup` — IT-Стартап (10 000 🪙) -> 1 500 🪙/час\n"
            "3. `mining` — Майнинг-ферма (100 000 🪙) -> 20 000 🪙/час\n\n"
            "Для покупки введите: `/business <название>`\n"
            "Собрать прибыль: `/collect`"
        )
        bot.reply_to(message, text, parse_mode='Markdown')
        return

    b_type = args[1].lower()
    if b_type in BUSINESSES:
        info = BUSINESSES[b_type]
        if p['coins'] >= info['cost']:
            p['coins'] -= info['cost']
            p['businesses'][b_type] += 1
            bot.reply_to(
                message,
                f"🎉 Вы успешно купили **{info['name']}**!",
                parse_mode='Markdown',
            )
        else:
            bot.reply_to(
                message,
                f"❌ Недостаточно монет! Нужно: {info['cost']} 🪙",
            )
    else:
        bot.reply_to(message, '❌ Неверный тип бизнеса!')


@bot.message_handler(commands=['collect'])
def collect(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()
    hours_passed = int((now - p['last_collect']) // 3600)

    if hours_passed < 1:
        bot.reply_to(
            message,
            '⏳ Прибыль пока не накопилась! Заходи позже (собирать можно раз в час/день).',
        )
        return

    # Ограничение сбора максимум за 24 часа
    hours_passed = min(hours_passed, 24)
    total_income = 0
    for b_type, count in p['businesses'].items():
        total_income += count * BUSINESSES[b_type]['income'] * hours_passed

    if total_income == 0:
        bot.reply_to(message, '🏢 У вас нет купленных бизнесов!')
        return

    p['coins'] += total_income
    p['last_collect'] = now
    bot.reply_to(
        message,
        f'💰 Вы собрали **+{total_income}** 🪙 за {hours_passed} ч. работы бизнеса!',
        parse_mode='Markdown',
    )


# --- 2. ЕЖЕДНЕВНЫЙ БОНУС ---


@bot.message_handler(commands=['daily'])
def daily(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()
    elapsed = now - p['last_daily']

    if elapsed < 86400:
        hours_left = int((86400 - elapsed) // 3600)
        bot.reply_to(
            message,
            f'⏳ Бонус уже получен! Приходи через {hours_left} ч.',
        )
        return

    # Проверка на сброс стрика (если прошло больше 48 часов)
    if elapsed > 172800:
        p['daily_streak'] = 0

    p['daily_streak'] += 1
    p['last_daily'] = now

    if p['daily_streak'] >= 7:
        reward = 5000
        p['daily_streak'] = 0
        bot.reply_to(
            message,
            f'🎁 **МЕГА-КЕЙС 7 ДНЯ!** Награда: **{reward}** 🪙!',
            parse_mode='Markdown',
        )
    else:
        reward = p['daily_streak'] * 100
        bot.reply_to(
            message,
            f"🎁 **Ежедневный бонус (День {p['daily_streak']}):** +{reward} 🪙!",
            parse_mode='Markdown',
        )

    p['coins'] += reward


# --- 3. РАБОТЫ И ПРОФЕССИИ ---


@bot.message_handler(commands=['work'])
def work(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    now = time.time()

    if now - p['last_work'] < 7200:  # Кулдаун 2 часа
        bot.reply_to(message, '⏳ Вы устали! Отдохните перед новой сменой.')
        return

    jobs = [
        'Таксист 🚕',
        'Программист 💻',
        'Киберспортсмен 🎮',
        'Мемодел 🖼',
    ]
    job = random.choice(jobs)
    salary = random.randint(300, 800)

    p['coins'] += salary
    p['last_work'] = now
    bot.reply_to(
        message,
        f'👨‍💻 Вы поработали как **{job}** и заработали **+{salary}** 🪙!',
        parse_mode='Markdown',
    )


# --- 4. РЕПУТАЦИЯ ---


@bot.message_handler(commands=['rep', 'like'])
def rep(message):
    if not message.reply_to_message:
        bot.reply_to(
            message,
            '⚠️ Ответьте этой командой на сообщение пользователя!',
        )
        return

    from_user = get_player(
        message.from_user.id, message.from_user.first_name
    )
    to_user = get_player(
        message.reply_to_message.from_user.id,
        message.reply_to_message.from_user.first_name,
    )

    if message.from_user.id == message.reply_to_message.from_user.id:
        bot.reply_to(message, '❌ Нельзя ставить репутацию самому себе!')
        return

    if time.time() - from_user['last_rep'] < 86400:
        bot.reply_to(
            message,
            '⏳ Вы можете выставлять репутацию только раз в день!',
        )
        return

    from_user['last_rep'] = time.time()
    to_user['rep'] += 1
    bot.reply_to(
        message,
        f"🔮 Вы подняли репутацию пользователю **{to_user['name']}**! (Всего: {to_user['rep']})",
        parse_mode='Markdown',
    )


# --- 5. ИНВЕНТАРЬ, ПИТОМЦЫ, КЕЙСЫ ---


@bot.message_handler(commands=['case'])
def open_case(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['coins'] < 500:
        bot.reply_to(message, '❌ Кейс стоит 500 🪙!')
        return

    p['coins'] -= 500
    loot_type = random.choice(['coins', 'status', 'item'])

    if loot_type == 'coins':
        win = random.randint(100, 1500)
        p['coins'] += win
        bot.reply_to(
            message,
            f'🎰 В кейсе выпало **{win}** 🪙!',
            parse_mode='Markdown',
        )
    elif loot_type == 'status':
        statuses = ['🔥 VIP', '⚡ Кибер-Гуру', '👑 Местный Босс']
        new_status = random.choice(statuses)
        p['status'] = new_status
        bot.reply_to(
            message,
            f'🎰 В кейсе выпал секретный статус: **{new_status}**!',
            parse_mode='Markdown',
        )
    else:
        items = [
            'Щит от грабежа',
            'Усилитель казино x2',
            'Золотой коллекционный билет',
        ]
        item = random.choice(items)
        p['inventory'].append(item)
        bot.reply_to(
            message,
            f'🎰 В кейсе выпал предмет: **{item}**!',
            parse_mode='Markdown',
        )


@bot.message_handler(commands=['inventory'])
def inventory(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    inv_text = '\n'.join(p['inventory']) if p['inventory'] else 'Пусто'
    pet_text = p['pet']['type'] if p['pet'] else 'Нет'

    bot.reply_to(
        message,
        f"🎒 **Инвентарь {p['name']}:**\n{inv_text}\n\n🐾 **Питомец:** {pet_text}",
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
        bot.reply_to(
            message,
            f"🍖 Вы покормили питомца за {cost} 🪙! Бонусы активны.",
        )
    else:
        bot.reply_to(message, f'❌ Не хватает {cost} 🪙 на кормежку!')


# --- ЛОТЕРЕЯ, БУНТИ (НАГРАДА ЗА ГОЛОВУ), МАТЕМАТИКА ---


@bot.message_handler(commands=['ticket'])
def buy_ticket(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['coins'] < 50:
        bot.reply_to(message, '❌ Билет стоит 50 🪙!')
        return

    p['coins'] -= 50
    tickets.append(message.from_user.id)
    bot.reply_to(
        message,
        f'🎟 Вы купили лотерейный билет! Всего билетов в банке: {len(tickets)}',
    )


@bot.message_handler(commands=['bounty'])
def set_bounty(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if not message.reply_to_message:
        bot.reply_to(
            message,
            '⚠️ Назначить награду можно ответом на сообщение цели!',
        )
        return

    target_id = message.reply_to_message.from_user.id
    try:
        amount = int(message.text.split()[1])
    except Exception:
        bot.reply_to(
            message,
            '⚠️ Укажите сумму! Пример: `/bounty 500`',
            parse_mode='Markdown',
        )
        return

    if p['coins'] < amount or amount <= 0:
        bot.reply_to(message, '❌ Недостаточно средств!')
        return

    p['coins'] -= amount
    bounties[target_id] = bounties.get(target_id, 0) + amount
    bot.reply_to(
        message,
        f"🎯 За голову **{message.reply_to_message.from_user.first_name}** назначена награда **{bounties[target_id]}** 🪙!",
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['math'])
def math_game(message):
    global active_math
    a, b, c = (
        random.randint(10, 50),
        random.randint(2, 10),
        random.randint(10, 100),
    )
    ans = a * b - c
    active_math = {'active': True, 'answer': str(ans), 'reward': 300}

    bot.send_message(
        message.chat.id,
        f'🧠 **Быстрый пример!**\nКто первый решит: `{a} * {b} - {c}`?\nНаграда: **300** 🪙',
        parse_mode='Markdown',
    )


# --- АИРДРОП С ПРОВЕРКОЙ АДМИНА И КОДА "финкс" ---


@bot.message_handler(commands=['airdrop'])
def airdrop(message):
    global airdrop_active

    # 1. Проверка: запуск разрешен ТОЛЬКО администраторам
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(
            message,
            '❌ Запускать дроп могут **только админы** чата!',
            parse_mode='Markdown',
        )
        return

    args = message.text.split()
    # Ожидается формат: /airdrop <сумма> финкс
    if len(args) < 3:
        bot.reply_to(
            message,
            '⚠️ Введите команду в формате: `/airdrop <сумма> <секретный_код>`',
            parse_mode='Markdown',
        )
        return

    try:
        reward = int(args[1])
    except ValueError:
        bot.reply_to(message, '❌ Сумма должна быть числом!')
        return

    secret_code = args[2].lower()

    # 2. Проверка секретного кода "финкс"
    if secret_code != 'финкс':
        bot.reply_to(
            message,
            '❌ **Неверный секретный код!** Дроп отменен.',
            parse_mode='Markdown',
        )
        return

    claim_code = str(random.randint(1000, 9999))
    airdrop_active = {'active': True, 'code': claim_code, 'reward': reward}

    bot.send_message(
        message.chat.id,
        f'📦 **АДМИН-СБРОС АИРДРОПА!**\nПервый, кто напишет `claim {claim_code}`, получит **{reward}** 🪙!',
        parse_mode='Markdown',
    )


# --- ОБРАБОТЧИКИ ОВЕРЛЕЙНЫХ СООБЩЕНИЙ (CLAIM И МАТЕМАТИКА) ---


@bot.message_handler(
    func=lambda m: m.text and m.text.lower().startswith('claim ')
)
def claim_airdrop(message):
    global airdrop_active
    if not airdrop_active['active']:
        return

    code_entered = (
        message.text.split()[1] if len(message.text.split()) > 1 else ''
    )
    if code_entered == airdrop_active['code']:
        p = get_player(message.from_user.id, message.from_user.first_name)
        p['coins'] += airdrop_active['reward']
        bot.reply_to(
            message,
            f"🎉 **{p['name']}** забрал аирдроп **+{airdrop_active['reward']}** 🪙!",
            parse_mode='Markdown',
        )
        airdrop_active['active'] = False


@bot.message_handler(
    func=lambda m: active_math['active']
    and m.text
    and m.text.strip() == active_math['answer']
)
def check_math(message):
    global active_math
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += active_math['reward']
    bot.reply_to(
        message,
        f"🎯 Правильно! **{p['name']}** забирает **+{active_math['reward']}** 🪙!",
        parse_mode='Markdown',
    )
    active_math['active'] = False


# --- ДУЭЛИ (С ПОДДЕРЖКОЙ BOUNTY) ---


@bot.message_handler(commands=['duel'])
def duel(message):
    if not message.reply_to_message:
        bot.reply_to(
            message,
            '⚠️ Пишите `/duel` ответом на сообщение оппонента!',
        )
        return

    p1 = get_player(message.from_user.id, message.from_user.first_name)
    p2 = get_player(
        message.reply_to_message.from_user.id,
        message.reply_to_message.from_user.first_name,
    )

    if p1 == p2:
        return

    winner, loser = (
        (p1, p2) if random.choice([True, False]) else (p2, p1)
    )
    prize = 150

    # Если за проигравшего была назначена награда
    target_id = message.reply_to_message.from_user.id
    if target_id in bounties and winner == p1:
        bounty_reward = bounties.pop(target_id)
        prize += bounty_reward
        bot.reply_to(
            message,
            f'🎯 **НАГРАДА ЗА ГОЛОВУ!** Вы забрали куш в **{bounty_reward}** 🪙!',
        )

    winner['coins'] += prize
    bot.reply_to(
        message,
        f"⚔️ **ДУЭЛЬ!**\n🏆 **{winner['name']}** одолел **{loser['name']}** и забрал **+{prize}** 🪙!",
        parse_mode='Markdown',
    )


# --- ЗАПУСК ---
keep_alive()
bot.polling(none_stop=True)
