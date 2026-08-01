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
    return 'Ультимативный Бот со всеми фичами запущен!'

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- 2. ИНИЦИАЛИЗАЦИЯ И БАЗА ДАННЫХ ---
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Твой ID администратора
ADMIN_IDS = [810823857]

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
            is_banned INTEGER DEFAULT 0,
            inventory TEXT DEFAULT '[]',
            pet TEXT DEFAULT 'None',
            last_feed INTEGER DEFAULT 0,
            last_wheel INTEGER DEFAULT 0,
            last_bank_interest INTEGER DEFAULT 0,
            bp_level INTEGER DEFAULT 1,
            bp_exp INTEGER DEFAULT 0
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
    # Таблица боссов
    c.execute('''
        CREATE TABLE IF NOT EXISTS boss (
            id INTEGER PRIMARY KEY,
            hp INTEGER DEFAULT 100000,
            max_hp INTEGER DEFAULT 100000,
            damage_log TEXT DEFAULT '{}'
        )
    ''')
    
    # Инициализация первого босса если нет
    c.execute('SELECT COUNT(*) FROM boss')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO boss (id, hp, max_hp, damage_log) VALUES (1, 100000, 100000, "{}")')

    conn.commit()
    conn.close()

init_db()

def get_player(user_id, name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
    row = c.fetchone()

    if not row:
        c.execute('INSERT INTO players (user_id, name) VALUES (?, ?)', (user_id, name))
        conn.commit()
        c.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        row = c.fetchone()

    conn.close()

    return {
        'user_id': row[0], 'name': row[1], 'coins': row[2], 'bank': row[3],
        'safe': row[4], 'power': row[5], 'exp': row[6], 'level': row[7],
        'is_banned': row[8], 'inventory': json.loads(row[9]),
        'pet': json.loads(row[10]) if row[10] != 'None' else None,
        'last_feed': row[11], 'last_wheel': row[12],
        'last_bank_interest': row[13], 'bp_level': row[14], 'bp_exp': row[15]
    }

def save_player(p):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE players SET
            name = ?, coins = ?, bank = ?, safe = ?, power = ?, exp = ?, level = ?,
            is_banned = ?, inventory = ?, pet = ?, last_feed = ?, last_wheel = ?,
            last_bank_interest = ?, bp_level = ?, bp_exp = ?
        WHERE user_id = ?
    ''', (
        p['name'], p['coins'], p['bank'], p['safe'], p['power'], p['exp'], p['level'],
        p['is_banned'], json.dumps(p['inventory']), json.dumps(p['pet']) if p['pet'] else 'None',
        p['last_feed'], p['last_wheel'], p['last_bank_interest'], p['bp_level'], p['bp_exp'], p['user_id']
    ))
    conn.commit()
    conn.close()

# --- 3. ГЕНЕРАТОРЫ ИНТЕРФЕЙСА (КНОПКИ) ---
def main_menu_kb(user_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("⚡ Клик", callback_data="menu_click"),
        InlineKeyboardButton("📊 Профиль", callback_data="menu_profile"),
        InlineKeyboardButton("🏦 Банк и Сейф", callback_data="menu_bank"),
        InlineKeyboardButton("🐱 Питомец", callback_data="menu_pet"),
        InlineKeyboardButton("🎡 Колесо Удачи", callback_data="menu_wheel"),
        InlineKeyboardButton("🔮 Крафт / Алхимия", callback_data="menu_craft"),
        InlineKeyboardButton("⚔️ Клановый Босс", callback_data="menu_boss"),
        InlineKeyboardButton("🎫 Боевой Пропуск", callback_data="menu_bp"),
        InlineKeyboardButton("🎁 Промокод", callback_data="menu_promo")
    )
    if user_id in ADMIN_IDS:
        kb.add(InlineKeyboardButton("👑 АДМИН-ПАНЕЛЬ", callback_data="menu_admin"))
    return kb

def back_to_menu_kb():
    return InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ В главное меню", callback_data="menu_main"))

# --- 4. ОСНОВНАЯ ОБРАБОТКА КОМАНД И КНОПОК ---
@bot.message_handler(commands=['start', 'menu'])
def start_cmd(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p['is_banned']:
        bot.reply_to(message, "❌ Вы забанены!")
        return

    bot.send_message(
        message.chat.id,
        f"🎮 **Добро пожаловать в Мега-Бот, {p['name']}!**\nВыбирайте раздел через кнопки ниже:",
        reply_markup=main_menu_kb(p['user_id']),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    p = get_player(call.from_user.id, call.from_user.first_name)

    if p['is_banned']:
        bot.answer_callback_query(call.id, "❌ Вы забанены!", show_alert=True)
        return

    # --- Навигация в Главное меню ---
    if call.data == "menu_main":
        bot.edit_message_text(
            f"🎮 **Главное меню:**\nИгрок: **{p['name']}** | Уровень: **{p['level']}**",
            call.message.chat.id, call.message.message_id,
            reply_markup=main_menu_kb(p['user_id']),
            parse_mode='Markdown'
        )

    # --- ⚡ КЛИК ---
    elif call.data == "menu_click":
        # Проверка сытости питомца
        bonus_mult = 1.0
        now = time.time()
        if p['pet'] and (now - p['last_feed'] < 86400):
            if p['pet']['type'] == 'cat':
                bonus_mult = 1.1  # +10%
            elif p['pet']['type'] == 'dragon':
                bonus_mult = 1.25  # +25%

        earned = int(p['power'] * bonus_mult)
        p['coins'] += earned
        p['exp'] += 1
        p['bp_exp'] += 1

        # Прокачка BP (каждые 10 exp = +1 уровень BP до 100 лвл)
        if p['bp_exp'] >= 10 and p['bp_level'] < 100:
            p['bp_level'] += 1
            p['bp_exp'] = 0

        # Прокачка общего уровня
        if p['exp'] >= p['level'] * 25:
            p['level'] += 1
            p['power'] += 1

        save_player(p)
        bot.answer_callback_query(call.id, f"+{earned} монет! (Баланс: {p['coins']} 🪙)")

    # --- 📊 ПРОФИЛЬ ---
    elif call.data == "menu_profile":
        pet_name = p['pet']['name'] if p['pet'] else "Нет"
        inv_text = ", ".join(p['inventory']) if p['inventory'] else "Пусто"
        text = (
            f"📊 **Профиль игрока {p['name']}:**\n\n"
            f"💰 Монет на руках: **{p['coins']}** 🪙\n"
            f"🏦 В банке: **{p['bank']}** 🪙 | Сейф: **{p['safe']}** 🪙\n"
            f"⚡ Сила клика: **{p['power']}**\n"
            f"⭐ Уровень: **{p['level']}** (EXP: {p['exp']}/{p['level']*25})\n"
            f"🎫 Боевой Пропуск: **{p['bp_level']} / 100 LVL**\n"
            f"🐾 Питомец: **{pet_name}**\n"
            f"🎒 Предметы: {inv_text}"
        )
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            reply_markup=back_to_menu_kb(), parse_mode='Markdown'
        )

    # --- 🏦 БАНК И СЕЙФ (+5% В СУТКИ) ---
    elif call.data == "menu_bank":
        now = time.time()
        # Процент на вклад раз в 24 часа
        if p['bank'] > 0 and (now - p['last_bank_interest'] >= 86400):
            interest = int(p['bank'] * 0.05)
            p['bank'] += interest
            p['last_bank_interest'] = now
            save_player(p)

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("📥 В Банк (+5%)", callback_data="bank_dep"),
            InlineKeyboardButton("📤 Из Банка", callback_data="bank_with"),
            InlineKeyboardButton("🔒 В Сейф", callback_data="safe_dep"),
            InlineKeyboardButton("🔓 Из Сейфа", callback_data="safe_with"),
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")
        )
        text = (
            f"🏦 **Центральный Банк и Сейф**\n\n"
            f"💰 Депозит в банке: **{p['bank']}** 🪙 (+5% доход в сутки)\n"
            f"🔒 В сейфе: **{p['safe']}** 🪙 (Полная защита от потерь)\n"
            f"💵 На руках: **{p['coins']}** 🪙"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')

    elif call.data in ["bank_dep", "bank_with", "safe_dep", "safe_with"]:
        act = call.data
        if act == "bank_dep" and p['coins'] > 0:
            p['bank'] += p['coins']; p['coins'] = 0
        elif act == "bank_with" and p['bank'] > 0:
            p['coins'] += p['bank']; p['bank'] = 0
        elif act == "safe_dep" and p['coins'] > 0:
            p['safe'] += p['coins']; p['coins'] = 0
        elif act == "safe_with" and p['safe'] > 0:
            p['coins'] += p['safe']; p['safe'] = 0
        save_player(p)
        bot.answer_callback_query(call.id, "✅ Операция успешно выполнена!")
        # Обновляем окно банка
        callback_handler(type('obj', (object,), {'id': call.id, 'from_user': call.from_user, 'data': 'menu_bank', 'message': call.message}))

    # --- 🐱 ПИТОМЦЫ ---
    elif call.data == "menu_pet":
        kb = InlineKeyboardMarkup(row_width=1)
        now = time.time()
        is_fed = "Кормлен ✅" if (now - p['last_feed'] < 86400) else "Голоден ❌"
        
        if not p['pet']:
            kb.add(
                InlineKeyboardButton("🐱 Купить Кота-майнера (2000 🪙)", callback_data="buy_pet_cat"),
                InlineKeyboardButton("🐉 Купить Дракончика (10000 🪙)", callback_data="buy_pet_dragon")
            )
            text = "🐾 **У вас нет питомца!** Купите его, чтобы получать пассивные бонусы:"
        else:
            kb.add(InlineKeyboardButton(f"🥩 Покормить питомца (150 🪙)", callback_data="feed_pet"))
            text = f"🐾 **Ваш питомец:** {p['pet']['name']}\nСтатус: **{is_fed}**\nБонус: +10-25% к монетам за клик!"

        kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="menu_main"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')

    elif call.data in ["buy_pet_cat", "buy_pet_dragon"]:
        cost = 2000 if call.data == "buy_pet_cat" else 10000
        p_type = 'cat' if call.data == "buy_pet_cat" else 'dragon'
        p_name = '🐱 Кот-майнер' if p_type == 'cat' else '🐉 Дракончик'

        if p['coins'] >= cost:
            p['coins'] -= cost
            p['pet'] = {'type': p_type, 'name': p_name}
            p['last_feed'] = time.time()
            save_player(p)
            bot.answer_callback_query(call.id, f"🎉 Вы приобрели питомца {p_name}!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Недостаточно средств!", show_alert=True)

    elif call.data == "feed_pet":
        if p['coins'] >= 150:
            p['coins'] -= 150
            p['last_feed'] = time.time()
            save_player(p)
            bot.answer_callback_query(call.id, "🥩 Питомец сыт и даёт вам бонусы!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Нужны 150 монет!", show_alert=True)

    # --- 🎡 КОЛЕСО УДАЧИ С АНИМАЦИЕЙ ---
    elif call.data == "menu_wheel":
        now = time.time()
        if now - p['last_wheel'] < 86400:
            bot.answer_callback_query(call.id, "⏳ Колесо удачи доступно раз в 24 часа!", show_alert=True)
            return

        p['last_wheel'] = now
        save_player(p)

        # Анимация прокрутки
        frames = ["[ 🪙 100 ]", "[ 💎 Меч ]", "[ 👑 Премиум ]", "[ 🪙 1000 ]", "[ 🎁 Сюрприз ]"]
        for f in frames:
            bot.edit_message_text(f"🎡 **Крутим колесо...**\n\n🎰 {f}", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
            time.sleep(0.4)

        win = random.choice([300, 500, 1000, 2500])
        p['coins'] += win
        save_player(p)

        bot.edit_message_text(
            f"🎉 **Колесо остановилось!**\n\nВы выиграли **{win}** 🪙!",
            call.message.chat.id, call.message.message_id,
            reply_markup=back_to_menu_kb(), parse_mode='Markdown'
        )

    # --- 🔮 АЛХИМИЯ И КРАФТ (СЛИЯНИЕ) ---
    elif call.data == "menu_craft":
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("⚔️ Купить Простой Меч (500 🪙)", callback_data="buy_sword"),
            InlineKeyboardButton("🔥 Слить 2 Меча (Шанс 70%)", callback_data="craft_merge"),
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")
        )
        swords = p['inventory'].count('Простой меч')
        super_swords = p['inventory'].count('🔥 Огненный клинок')
        text = (
            f"🔮 **Алхимия и Слияние Предметов**\n\n"
            f"⚔️ Простых мечей: **{swords}** шт.\n"
            f"🔥 Огненных клинков: **{super_swords}** шт. (+10 к клику)\n\n"
            f"Объедините 2 Простых меча, чтобы с шансом 70% получить Огненный клинок!"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')

    elif call.data == "buy_sword":
        if p['coins'] >= 500:
            p['coins'] -= 500
            p['inventory'].append('Простой меч')
            save_player(p)
            bot.answer_callback_query(call.id, "⚔️ Куплен Простой меч!")
        else:
            bot.answer_callback_query(call.id, "❌ Недостаточно монет!", show_alert=True)

    elif call.data == "craft_merge":
        if p['inventory'].count('Простой меч') < 2:
            bot.answer_callback_query(call.id, "❌ Нужно минимум 2 Простых меча!", show_alert=True)
            return

        p['inventory'].remove('Простой меч')
        p['inventory'].remove('Простой меч')

        if random.random() <= 0.70:
            p['inventory'].append('🔥 Огненный клинок')
            p['power'] += 10
            res_msg = "🎉 УСПЕХ! Скрафчен 🔥 Огненный клинок (+10 к клику)!"
        else:
            res_msg = "💥 НЕУДАЧА! Предметы сгорели при крафте."

        save_player(p)
        bot.answer_callback_query(call.id, res_msg, show_alert=True)

    # --- ⚔️ КЛАНОВЫЙ БОСС (100 000 HP) ---
    elif call.data == "menu_boss":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT hp, max_hp FROM boss WHERE id = 1')
        b_row = c.fetchone()
        conn.close()

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("⚔️ Нанести урон Боссу!", callback_data="attack_boss"),
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")
        )
        text = (
            f"👹 **Мировой Клановый Босс**\n\n"
            f"❤️ Здоровье: **{b_row[0]} / {b_row[1]} HP**\n\n"
            f"Каждый ваш клик наносит урон, равный вашей силе клика! При победе казна делится между всеми!"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')

    elif call.data == "attack_boss":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT hp, damage_log FROM boss WHERE id = 1')
        hp, log_raw = c.fetchone()
        damage_log = json.loads(log_raw)

        if hp <= 0:
            bot.answer_callback_query(call.id, "🎉 Босс уже повержен! Ожидайте спавна нового.", show_alert=True)
            conn.close()
            return

        dmg = p['power']
        new_hp = max(0, hp - dmg)
        damage_log[str(p['user_id'])] = damage_log.get(str(p['user_id']), 0) + dmg

        # Если босс убит — раздача 50 000 монет награды пропорционально
        if new_hp == 0:
            total_dmg = sum(damage_log.values())
            for uid, user_dmg in damage_log.items():
                reward = int((user_dmg / total_dmg) * 50000)
                c.execute('UPDATE players SET coins = coins + ? WHERE user_id = ?', (reward, int(uid)))
            # Респавн нового босса
            c.execute('UPDATE boss SET hp = 100000, damage_log = "{}" WHERE id = 1')
            bot.send_message(call.message.chat.id, "🎉 **БОСС ПОВЕРЖЕН!** Все участники получили награды!")
        else:
            c.execute('UPDATE boss SET hp = ?, damage_log = ? WHERE id = 1', (new_hp, json.dumps(damage_log)))

        conn.commit()
        conn.close()

        bot.answer_callback_query(call.id, f"⚔️ Вы нанесли {dmg} урона боссу!")

    # --- 🎫 БОЕВОЙ ПРОПУСК (100 ЛВЛ) ---
    elif call.data == "menu_bp":
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🎁 Забрать награду за уровень", callback_data="claim_bp_reward"),
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")
        )
        text = (
            f"🎫 **Боевой Пропуск (Battle Pass)**\n\n"
            f"🏆 Ваш уровень BP: **{p['bp_level']} / 100**\n"
            f"⚡ Прогресс уровня: **{p['bp_exp']} / 10 EXP**\n\n"
            f"Майните монеты, чтобы повышать уровень BP и получать монеты за каждый уровень!"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')

    elif call.data == "claim_bp_reward":
        reward = p['bp_level'] * 200
        p['coins'] += reward
        save_player(p)
        bot.answer_callback_query(call.id, f"🎁 Получено {reward} монет за ваш уровень BP!", show_alert=True)

    # --- 🎁 ВВОД ПРОМОКОДА ---
    elif call.data == "menu_promo":
        msg = bot.send_message(call.message.chat.id, "Введите промокод сообщением в чат:")
        bot.register_next_step_handler(msg, process_promo_code)

    # --- 👑 АДМИН-ПАНЕЛЬ ---
    elif call.data == "menu_admin":
        if p['user_id'] not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен!", show_alert=True)
            return

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("📢 Создать Промокод / Аирдроп", callback_data="adm_create_promo"),
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")
        )
        bot.edit_message_text("👑 **Админ-панель:**", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')

    elif call.data == "adm_create_promo":
        msg = bot.send_message(call.message.chat.id, "Введите данные промокода через пробел:\n`КОД НАГРАДА ЛИМИТ_АКТИВАЦИЙ`\n\nПример: `SUPER2026 5000 10`", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_create_promo)

def process_promo_code(message):
    code_text = message.text.strip()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT reward, max_uses, used_count, used_users FROM promo_codes WHERE code = ?', (code_text,))
    row = c.fetchone()

    if not row:
        bot.reply_to(message, "❌ Такого промокода не существует!")
        conn.close()
        return

    reward, max_uses, used_count, used_users_raw = row
    used_users = json.loads(used_users_raw)

    if message.from_user.id in used_users:
        bot.reply_to(message, "❌ Вы уже активировали этот промокод!")
    elif used_count >= max_uses:
        bot.reply_to(message, "❌ Закончился лимит активаций этого промокода!")
    else:
        used_users.append(message.from_user.id)
        c.execute('UPDATE promo_codes SET used_count = used_count + 1, used_users = ? WHERE code = ?', (json.dumps(used_users), code_text))
        conn.commit()

        p = get_player(message.from_user.id, message.from_user.first_name)
        p['coins'] += reward
        save_player(p)
        bot.reply_to(message, f"🎉 Промокод активирован! Взнос: +**{reward}** 🪙!", parse_mode='Markdown')

    conn.close()

def process_create_promo(message):
    try:
        code, reward, max_uses = message.text.split()
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('INSERT INTO promo_codes (code, reward, max_uses) VALUES (?, ?, ?)', (code, int(reward), int(max_uses)))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Промокод `{code}` на {reward} монет (Лимит: {max_uses} чел.) успешно создан!", parse_mode='Markdown')
    except Exception:
        bot.reply_to(message, "⚠️ Ошибка ввода! Формат: `КОД СУММА ЛИМИТ`")

# --- 5. БЕЗОПАСНЫЙ ЗАПУСК С БЕСКОНЕЧНЫМ ПОЛЛИНГОМ ---
if __name__ == '__main__':
    keep_alive()

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass

    print("🚀 Ультимативный Бот со всеми фичами запущен!")

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            time.sleep(3)