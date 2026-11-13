import os
import random
import re
import time
import requests
import telebot
from urllib.parse import quote
from telebot import types
from dotenv import load_dotenv

load_dotenv()
bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))
TMDB_KEY = os.getenv("TMDB_API_KEY")
IMG = "https://image.tmdb.org/t/p/w780"
POSTER = "https://image.tmdb.org/t/p/w500"

games = {}
cache = {}


# ---------- Викторина ----------

def get_question():
    page = random.randint(1, 20)
    r = requests.get(
        "https://api.themoviedb.org/3/movie/popular",
        params={"api_key": TMDB_KEY, "language": "ru-RU", "page": page},
        timeout=10,
    )
    r.raise_for_status()
    movies = [
        m for m in r.json()["results"]
        if m.get("overview") and m.get("title") and m.get("backdrop_path")
    ]
    correct = random.choice(movies)
    others = random.sample([m for m in movies if m["id"] != correct["id"]], 3)
    options = [correct["title"]] + [m["title"] for m in others]
    random.shuffle(options)
    overview = re.sub(re.escape(correct["title"]), "«…»", correct["overview"], flags=re.IGNORECASE)
    if len(overview) > 700:
        overview = overview[:700].rsplit(" ", 1)[0] + "…"
    return overview, options, correct["title"], IMG + correct["backdrop_path"]


def send_question(chat_id):
    try:
        overview, options, answer, photo = get_question()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for i, title in enumerate(options):
            markup.add(types.InlineKeyboardButton(title, callback_data=f"ans:{i}"))
        sent = bot.send_photo(
            chat_id,
            photo,
            caption="🎬 Угадай фильм по кадру и описанию:\n\n" + overview,
            reply_markup=markup,
        )
    except Exception as e:
        bot.send_message(chat_id, "Не получилось загрузить вопрос, попробуй ещё раз: /play")
        print("Ошибка:", e)
        return
    games[(sent.chat.id, sent.message_id)] = {"options": options, "answer": answer}


# ---------- Новинки ----------

def get_new_list(kind):
    saved = cache.get(kind)
    if saved and time.time() - saved[0] < 3600:
        return saved[1]
    path = "now_playing" if kind == "now" else "upcoming"
    movies = []
    for page in (1, 2):
        r = requests.get(
            "https://api.themoviedb.org/3/movie/" + path,
            params={"api_key": TMDB_KEY, "language": "ru-RU", "page": page},
            timeout=10,
        )
        r.raise_for_status()
        movies += [m for m in r.json()["results"] if m.get("poster_path") and m.get("title")]
    if kind == "soon":
        today = time.strftime("%Y-%m-%d")
        movies = [m for m in movies if m.get("release_date", "") >= today]
        movies.sort(key=lambda m: m.get("release_date", ""))
    cache[kind] = (time.time(), movies)
    return movies


def fmt_date(d):
    try:
        y, m, dd = d.split("-")
        return dd + "." + m + "." + y
    except Exception:
        return "—"


def build_card(kind, i):
    movies = get_new_list(kind)
    if not movies:
        return None
    i = i % len(movies)
    m = movies[i]
    rating = m.get("vote_average") or 0
    rating_text = str(round(rating, 1)) if rating else "—"
    overview = m.get("overview") or "Описание пока не добавлено."
    if len(overview) > 500:
        overview = overview[:500].rsplit(" ", 1)[0] + "…"
    header = "Сейчас в кино" if kind == "now" else "Скоро выйдут"
    caption = (
        "🍿 " + header + "\n\n"
        "🎬 " + m["title"] + "\n"
        "📅 " + fmt_date(m.get("release_date", "")) + "\n"
        "⭐ Рейтинг: " + rating_text + "\n\n" + overview
    )
    other = "soon" if kind == "now" else "now"
    other_text = "🗓 Скоро выйдут" if kind == "now" else "🎞 Сейчас в кино"
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("◀️", callback_data=f"new:{kind}:{i - 1}"),
        types.InlineKeyboardButton(f"{i + 1}/{len(movies)}", callback_data="noop"),
        types.InlineKeyboardButton("▶️", callback_data=f"new:{kind}:{i + 1}"),
    )
    markup.add(types.InlineKeyboardButton(
        "🎬 Трейлер",
        url="https://www.youtube.com/results?search_query=" + quote(m["title"] + " трейлер"),
    ))
    markup.add(types.InlineKeyboardButton(other_text, callback_data=f"new:{other}:0"))
    return POSTER + m["poster_path"], caption, markup


def send_new(chat_id, kind="now"):
    try:
        card = build_card(kind, 0)
    except Exception as e:
        bot.send_message(chat_id, "Не получилось загрузить новинки, попробуй позже: /new")
        print("Ошибка:", e)
        return
    if not card:
        bot.send_message(chat_id, "Пока список пуст, попробуй позже.")
        return
    photo, caption, markup = card
    bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup)


# ---------- Команды ----------

@bot.message_handler(commands=["start"])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 Играть", callback_data="play"))
    markup.add(types.InlineKeyboardButton("🍿 Новинки кино", callback_data="shownew"))
    bot.send_message(
        message.chat.id,
        "Привет! Я бот про кино 🎬\n\n"
        "🎮 /play: угадай фильм по кадру и описанию\n"
        "🍿 /new: новинки кино, что идёт сейчас и что скоро выйдет\n\n"
        "Нажми кнопку ниже.",
        reply_markup=markup,
    )


@bot.message_handler(commands=["play"])
def play(message):
    send_question(message.chat.id)


@bot.message_handler(commands=["new"])
def new_command(message):
    send_new(message.chat.id)


# ---------- Кнопки ----------

@bot.callback_query_handler(func=lambda call: call.data == "play")
def play_button(call):
    bot.answer_callback_query(call.id)
    send_question(call.message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data == "shownew")
def shownew_button(call):
    bot.answer_callback_query(call.id)
    send_new(call.message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data == "noop")
def noop(call):
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("new:"))
def new_page(call):
    _, kind, idx = call.data.split(":")
    try:
        card = build_card(kind, int(idx))
        if not card:
            bot.answer_callback_query(call.id, "Список пуст.")
            return
        photo, caption, markup = card
        bot.edit_message_media(
            types.InputMediaPhoto(photo, caption=caption),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        bot.answer_callback_query(call.id, "Не получилось, попробуй ещё раз.")
        print("Ошибка:", e)


@bot.callback_query_handler(func=lambda call: call.data.startswith("ans:"))
def check_answer(call):
    key = (call.message.chat.id, call.message.message_id)
    game = games.pop(key, None)
    if not game:
        bot.answer_callback_query(call.id, "Этот вопрос уже закрыт.")
        return
    chosen = game["options"][int(call.data.split(":")[1])]
    if chosen == game["answer"]:
        text = "✅ Верно! Это «" + game["answer"] + "»."
    else:
        text = "❌ Неверно. Правильный ответ: «" + game["answer"] + "»."
    bot.answer_callback_query(call.id)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("▶️ Ещё вопрос", callback_data="play"))
    bot.send_message(call.message.chat.id, text, reply_markup=markup)


bot.set_my_commands([
    types.BotCommand("play", "🎮 Угадай фильм"),
    types.BotCommand("new", "🍿 Новинки кино"),
    types.BotCommand("start", "Приветствие"),
])

print("Бот запущен")
bot.infinity_polling()
