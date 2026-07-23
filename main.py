import telebot
from telebot import types
import random
import os
import time
from flask import Flask
from threading import Thread

# --- 1. ФЕЙК ВЕБ-СЕРВЕР ДЛЯ БЕСПЛАТНОГО RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Мега-Бот запущен и работает!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- 2. ИНИЦИАЛИЗАЦИЯ БОТА ---
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Базы данных в памяти
players = {}
marriages = {}
airdrop_active = {"active": False, "code": "", "reward": 0}

def get_player(user_id, name):
    if user_id not in players:
        players[user_id] = {
            'name': name, 
            'coins': 100, 
            'power': 1, 
            'last_rob': 0,
            'last_roulette': 0
        }
    else:
        players[user_id]['name'] = name
    return players[user_id]

# --- 3. КОМАНДЫ ---

@bot.message_handler(commands=['start', 'help'])
def start(message):
    text = (
        "🔥 **МЕГА-ИГРОВОЙ БОТ ДЛЯ ЧАТА!** 🔥\n\n"
        "🎮 **Экономика:**\n"
        "🔹 `/click` — майнить монеты\n"
        "🔹 `/shop` — купить видеокарту (прокачка клика)\n"
        "🔹 `/balance` — твой профиль\n"
        "🔹 `/top` — топ богачей чата\n\n"
        "🎰 **Азарт и Хаос:**\n"
        "🔹 `/casino <сумма>` — сыграть в казино (50/50)\n"
        "🔹 `/roulette` — русская рулетка (выигрыш или бан на риск!)\n"
        "🔹 `/rob` — ограбить игрока (ответом на его сообщение)\n"
        "🔹 `/duel` — дуэль на монеты (ответом на сообщение)\n\n"
        "❤️ **Отношения и События:**\n"
        "🔹 `/marry` — предложить брак (ответом на сообщение)\n"
        "🔹 `/divorce` — развестись\n"
        "🔹 `/airdrop <сумма>` — скинуть секретный код на монеты в чат!"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# --- КЛИКЕР И ПРОФИЛЬ ---
@bot.message_handler(commands=['click'])
def click(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    p['coins'] += p['power']
    bot.reply_to(message, f"⚡ +{p['power']} монет! Баланс: **{p['coins']}** 🪙", parse_mode="Markdown")

@bot.message_handler(commands=['balance'])
def balance(message):
    uid = message.from_user.id
    p = get_player(uid, message.from_user.first_name)
    spouse = marriages.get(uid, "Один(очка)")
    
    text = (
        f"📊 **Профиль {p['name']}:**\n"
        f"💰 Монет: **{p['coins']}** 🪙\n"
        f"⚡ Сила клика: **{p['power']}**\n"
        f"💍 В браке с: **{spouse}**"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['shop'])
def shop(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    cost = p['power'] * 25
    if p['coins'] >= cost:
        p['coins'] -= cost
        p['power'] += 5
        bot.reply_to(message, f"🚀 Куплена видеокарта за {cost} монет! Теперь клик дает **+{p['power']}** монет!", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ Не хватает монет! Нужно: **{cost}** 🪙", parse_mode="Markdown")

@bot.message_handler(commands=['top'])
def top(message):
    if not players:
        bot.reply_to(message, "Топ пока пуст!")
        return
    sorted_p = sorted(players.values(), key=lambda x: x['coins'], reverse=True)[:5]
    text = "🏆 **ТОП-5 БОГАЧЕЙ ЧАТА:**\n\n"
    for i, p in enumerate(sorted_p, 1):
        text += f"{i}. {p['name']} — **{p['coins']}** 🪙\n"
    bot.reply_to(message, text, parse_mode="Markdown")

# --- КАЗИНО И РУЛЕТКА ---
@bot.message_handler(commands=['casino'])
def casino(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    try:
        bet = int(message.text.split()[1])
    except:
        bot.reply_to(message, "⚠️ Укажи ставку! Пример: `/casino 50`", parse_mode="Markdown")
        return

    if bet <= 0 or bet > p['coins']:
        bot.reply_to(message, "❌ Недостаточно монет или неверная ставка!")
        return

    if random.choice([True, False]):
        p['coins'] += bet
        bot.reply_to(message, f"🎉 УДАЧА! Ты выиграл **+{bet}** монет! Баланс: {p['coins']} 🪙", parse_mode="Markdown")
    else:
        p['coins'] -= bet
        bot.reply_to(message, f"💥 СЛИВ! Ты потерял **-{bet}** монет. Баланс: {p['coins']} 🪙", parse_mode="Markdown")

@bot.message_handler(commands=['roulette'])
def roulette(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if time.time() - p['last_roulette'] < 60:
        bot.reply_to(message, "⏳ Барабан еще горячий! Подожди 1 минуту.")
        return
    
    p['last_roulette'] = time.time()
    bot.reply_to(message, "🎰 *Крутим барабан... Жмем на курок...*", parse_mode="Markdown")
    time.sleep(2)

    if random.randint(1, 6) == 1:
        loss = int(p['coins'] * 0.3)
        p['coins'] -= loss
        bot.reply_to(message, f"💀 **ВЫСТРЕЛ!** Ты потерял **{loss}** монет (30% баланса)!", parse_mode="Markdown")
    else:
        reward = 300
        p['coins'] += reward
        bot.reply_to(message, f"🍀 **ПУСТО!** Ты выжил и получил **+{reward}** монет!", parse_mode="Markdown")

# --- ОГРАБЛЕНИЕ И ДУЭЛИ ---
@bot.message_handler(commands=['rob'])
def rob(message):
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Пиши `/rob` в ответ на сообщение жертвы!")
        return
    
    thief = get_player(message.from_user.id, message.from_user.first_name)
    victim = get_player(message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name)

    if thief == victim:
        bot.reply_to(message, "❌ Нельзя ограбить самого себя!")
        return

    if time.time() - thief['last_rob'] < 120:
        bot.reply_to(message, "⏳ Полиция на хвосте! Подожди 2 минуты перед новым грабежом.")
        return

    thief['last_rob'] = time.time()

    if victim['coins'] < 50:
        bot.reply_to(message, f"❌ У {victim['name']} нечего красть, он нищий!")
        return

    if random.random() < 0.45: # 45% шанс успеха
        stolen = random.randint(20, int(victim['coins'] * 0.3))
        victim['coins'] -= stolen
        thief['coins'] += stolen
        bot.reply_to(message, f"🥷 **УСПЕХ!** {thief['name']} украл **{stolen}** 🪙 у {victim['name']}!", parse_mode="Markdown")
    else:
        fine = 100
        thief['coins'] = max(0, thief['coins'] - fine)
        bot.reply_to(message, f"🚷 **ПОЙМАН!** {thief['name']} попался полиции и заплатил штраф **{fine}** 🪙!", parse_mode="Markdown")

@bot.message_handler(commands=['duel'])
def duel(message):
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Пиши `/duel` в ответ на сообщение оппонента!")
        return

    p1 = get_player(message.from_user.id, message.from_user.first_name)
    p2 = get_player(message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name)

    if p1 == p2:
        return

    winner, loser = (p1, p2) if random.choice([True, False]) else (p2, p1)
    prize = 150
    winner['coins'] += prize
    bot.reply_to(message, f"⚔️ **ДУЭЛЬ!**\n🏆 **{winner['name']}** побеждает **{loser['name']}** и забирает **+{prize}** 🪙!", parse_mode="Markdown")

# --- БРАКИ ---
@bot.message_handler(commands=['marry'])
def marry(message):
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Пиши `/marry` в ответ человеку, с кем хочешь создать пару!")
        return
    
    u1_id = message.from_user.id
    u2_id = message.reply_to_message.from_user.id
    u1_name = message.from_user.first_name
    u2_name = message.reply_to_message.from_user.first_name

    if u1_id == u2_id:
        bot.reply_to(message, "❌ Нельзя жениться на себе!")
        return

    marriages[u1_id] = u2_name
    marriages[u2_id] = u1_name
    bot.reply_to(message, f"💖 **ПОЗДРАВЛЯЕМ!** {u1_name} и {u2_name} теперь состоят в браке! 🎉", parse_mode="Markdown")

@bot.message_handler(commands=['divorce'])
def divorce(message):
    uid = message.from_user.id
    if uid in marriages:
        ex = marriages[uid]
        del marriages[uid]
        bot.reply_to(message, f"💔 Вы развелись с {ex}!")
    else:
        bot.reply_to(message, "Вы ни с кем не состоите в браке.")

# --- АИРДРОП ---
@bot.message_handler(commands=['airdrop'])
def airdrop(message):
    global airdrop_active
    try:
        reward = int(message.text.split()[1])
    except:
        bot.reply_to(message, "⚠️ Укажи сумму аирдропа! Пример: `/airdrop 500`", parse_mode="Markdown")
        return

    code = str(random.randint(1000, 9999))
    airdrop_active = {"active": True, "code": code, "reward": reward}
    
    bot.send_message(
        message.chat.id, 
        f"📦 **СБРОС АИРДРОПА!**\nПервый, кто напишет код `claim {code}`, получит **{reward}** 🪙!", 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text and m.text.startswith('claim '))
def claim_airdrop(message):
    global airdrop_active
    if not airdrop_active["active"]:
        return

    code_entered = message.text.split()[1] if len(message.text.split()) > 1 else ""
    if code_entered == airdrop_active["code"]:
        p = get_player(message.from_user.id, message.from_user.first_name)
        p['coins'] += airdrop_active["reward"]
        bot.reply_to(message, f"🎉 **{p['name']}** успел первым и забрал **+{airdrop_active['reward']}** 🪙!", parse_mode="Markdown")
        airdrop_active["active"] = False

# ЗАПУСК
keep_alive()
bot.polling(none_stop=True)
