import telebot
import os

# Бот будет брать токен из настроек хостинга для безопасности
TOKEN = os.environ.get('BOT_TOKEN', 'ТВОЙ_ТОКЕН_ЕСЛИ_ТЕСТИРУЕШЬ_ЛОКАЛЬНО')
bot = telebot.TeleBot(TOKEN)

# База данных в памяти
players = {}

def get_player(user_id, name):
    if user_id not in players:
        players[user_id] = {'name': name, 'coins': 0, 'power': 1}
    return players[user_id]

@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.reply_to(message, 
                 "🎰 **Добро пожаловать в Чатовый Кликер!**\n\n"
                 "Команды:\n"
                 "💎 `/click` — майнить монеты\n"
                 "💰 `/balance` — твой баланс\n"
                 "🛒 `/shop` — купить видеокарту (+5 к клику)\n"
                 "🏆 `/top` — топ богачей чата", 
                 parse_mode="Markdown")

@bot.message_handler(commands=['click'])
def click(message):
    user = get_player(message.from_user.id, message.from_user.first_name)
    user['coins'] += user['power']
    bot.reply_to(message, f"⚡ +{user['power']} монет! Ваш баланс: **{user['coins']}** 🪙", parse_mode="Markdown")

@bot.message_handler(commands=['balance'])
def balance(message):
    user = get_player(message.from_user.id, message.from_user.first_name)
    bot.reply_to(message, f"📊 Игрок: **{user['name']}**\n💰 Монет: **{user['coins']}**\n⚡ Сила клика: **{user['power']}**", parse_mode="Markdown")

@bot.message_handler(commands=['shop'])
def shop(message):
    user = get_player(message.from_user.id, message.from_user.first_name)
    cost = user['power'] * 20
    
    if user['coins'] >= cost:
        user['coins'] -= cost
        user['power'] += 5
        bot.reply_to(message, f"🚀 Вы купили новую видеокарту за {cost} монет! Теперь ваш клик дает **+{user['power']}** монет!", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ Не хватает монет! Нужно: **{cost}** 🪙 (У вас: {user['coins']})", parse_mode="Markdown")

@bot.message_handler(commands=['top'])
def top(message):
    if not players:
        bot.reply_to(message, "Топ пока пуст! Начните играть с команды /click")
        return
    
    sorted_players = sorted(players.values(), key=lambda x: x['coins'], reverse=True)[:5]
    text = "🏆 **ТОП-5 МАЙНЕРОВ ЧАТА:**\n\n"
    for i, p in enumerate(sorted_players, 1):
        text += f"{i}. {p['name']} — **{p['coins']}** 🪙\n"
    
    bot.reply_to(message, text, parse_mode="Markdown")

bot.polling(none_stop=True)