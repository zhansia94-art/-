# -*- coding: utf-8 -*-
import asyncio
import logging
import os

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from cases import CASES, FINAL_REWARD, FIRST_CASE_NUMBER, LETTERS, QUESTIONS, RANKS

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "detective.db")

# Подпись на КАЖДОМ сообщении бота
SIGN = "\n\n<i>сделано кимом • @mebona</i>"

dp = Dispatcher()
db: aiosqlite.Connection
TOTAL = len(CASES)


# ───────────────────────── БАЗА ДАННЫХ ─────────────────────────
async def init_db():
    global db
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            user_id  INTEGER PRIMARY KEY,
            username TEXT,
            case_idx INTEGER NOT NULL DEFAULT 0,
            solved   INTEGER NOT NULL DEFAULT 0,
            score    INTEGER NOT NULL DEFAULT 0,
            wrong    INTEGER NOT NULL DEFAULT 0,
            hints    INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS notes(
            user_id  INTEGER NOT NULL,
            case_idx INTEGER NOT NULL,
            key      TEXT NOT NULL,
            title    TEXT NOT NULL,
            text     TEXT NOT NULL,
            PRIMARY KEY(user_id, case_idx, key)
        );
        """
    )
    await db.commit()


async def get_user(tg_user) -> dict:
    cur = await db.execute("SELECT * FROM users WHERE user_id=?", (tg_user.id,))
    row = await cur.fetchone()
    if row is None:
        await db.execute(
            "INSERT INTO users(user_id, username) VALUES(?, ?)",
            (tg_user.id, tg_user.username or tg_user.full_name),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (tg_user.id,))
        row = await cur.fetchone()
    return dict(row)


async def add_note(uid: int, case_idx: int, key: str, title: str, text: str):
    await db.execute(
        "INSERT OR IGNORE INTO notes(user_id, case_idx, key, title, text) VALUES(?,?,?,?,?)",
        (uid, case_idx, key, title, text),
    )
    await db.commit()


async def note_keys(uid: int, case_idx: int) -> set:
    cur = await db.execute("SELECT key FROM notes WHERE user_id=? AND case_idx=?", (uid, case_idx))
    return {r["key"] for r in await cur.fetchall()}


async def get_notes(uid: int, case_idx: int):
    cur = await db.execute(
        "SELECT title, text FROM notes WHERE user_id=? AND case_idx=? ORDER BY rowid", (uid, case_idx)
    )
    return await cur.fetchall()


# ───────────────────────── ВСПОМОГАТЕЛЬНОЕ ─────────────────────────
def kb(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


async def reply(event, text: str, markup=None):
    """Единая отправка: подпись добавляется здесь, поэтому она есть на каждом сообщении."""
    text += SIGN
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                await event.message.answer(text, reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup)


def rank_of(solved: int) -> str:
    name = RANKS[0][1]
    for need, title in RANKS:
        if solved >= need:
            name = title
    return name


def letters_line(solved: int) -> str:
    n = min(solved, len(LETTERS))
    return " ".join(list(LETTERS[:n]) + ["_"] * (len(LETTERS) - n))


# ───────────────────────── ЭКРАНЫ ─────────────────────────
def screen_menu(u):
    text = (
        "🕵️ <b>ДЕТЕКТИВ</b>\n\n"
        "В магазинах города исчезают вещи. Ты допрашиваешь подозреваемых, "
        "осматриваешь место и находишь виновного.\n\n"
        f"Дел раскрыто: <b>{u['solved']}/{TOTAL}</b> · Очки: <b>{u['score']}</b>\n"
        "Прогресс сохраняется автоматически."
    )
    return text, kb([[("🗂 К делу", "hub")], [("📓 Блокнот", "nb"), ("🏆 Профиль", "prof")]])


def screen_final(u):
    text = FINAL_REWARD + f"\n\n🔤 Буквы шифра: <b>{letters_line(u['solved'])}</b>\nОчки: <b>{u['score']}</b>"
    return text, kb([[("🏆 Профиль", "prof")]])


def screen_hub(u):
    if u["case_idx"] >= TOTAL:
        return screen_final(u)
    c = CASES[u["case_idx"]]
    num = FIRST_CASE_NUMBER + u["case_idx"]
    lines = "\n".join(f"• <b>{s['name']}</b> — {s['role']}" for s in c["suspects"])
    text = (
        f"🗂 <b>ДЕЛО №{num}</b> · {c['title']}\n"
        f"<i>Дело {u['case_idx'] + 1} из {TOTAL}</i>\n\n"
        f"В 21:30 из магазина «{c['place']}» исчез предмет: <b>{c['item']}</b>. "
        "Есть 4 подозреваемых.\n\n"
        f"{c['story']}\n\n"
        f"👥 <b>Подозреваемые:</b>\n{lines}\n\n"
        "Задавай вопросы, осматривай место и обвиняй виновного."
    )
    rows = [[(s["name"], f"s:{i}")] for i, s in enumerate(c["suspects"])]
    rows.append([("🔎 Осмотр места", "clues"), ("📓 Блокнот", "nb")])
    rows.append([("💡 Подсказка", "hint"), ("⚖️ Обвинить", "acc")])
    return text, kb(rows)


async def screen_suspect(u, i):
    c = CASES[u["case_idx"]]
    s = c["suspects"][i]
    keys = await note_keys(u["user_id"], u["case_idx"])
    text = f"👤 <b>{s['name']}</b> · {s['role']}\n<i>{s['desc']}</i>\n\nЗадай вопрос:"
    rows = [
        [(("✅ " if f"s{i}q{j}" in keys else "") + q, f"q:{i}:{j}")] for j, q in enumerate(QUESTIONS)
    ]
    rows.append([("⬅️ К делу", "hub")])
    return text, kb(rows)


async def screen_clues(u):
    c = CASES[u["case_idx"]]
    keys = await note_keys(u["user_id"], u["case_idx"])
    rows = [[(("✅ " if f"c{k}" in keys else "") + name, f"c:{k}")] for k, (name, _) in enumerate(c["clues"])]
    rows.append([("⬅️ К делу", "hub")])
    return "🔎 <b>Осмотр места.</b> Что проверим?", kb(rows)


def screen_accuse(u):
    c = CASES[u["case_idx"]]
    rows = [[(f"{s['name']}", f"a:{i}")] for i, s in enumerate(c["suspects"])]
    rows.append([("⬅️ К делу", "hub")])
    text = (
        "⚖️ <b>Кто виновен?</b>\n\n"
        "Подумай хорошо: за каждую ошибку теряешь 20 очков.\n"
        f"Ошибок в деле: <b>{u['wrong']}</b>"
    )
    return text, kb(rows)


def screen_profile(u):
    text = (
        "🏆 <b>Профиль детектива</b>\n\n"
        f"Звание: <b>{rank_of(u['solved'])}</b>\n"
        f"Дел раскрыто: <b>{u['solved']}/{TOTAL}</b>\n"
        f"Очки: <b>{u['score']}</b> из {TOTAL * 100}\n"
        f"🔤 Буквы шифра: <b>{letters_line(u['solved'])}</b>"
    )
    return text, kb([[("🗂 К делу", "hub")]])


# ───────────────────────── КОМАНДЫ ─────────────────────────
@dp.message(CommandStart())
@dp.message(Command("menu"))
async def cmd_start(m: Message):
    u = await get_user(m.from_user)
    text, markup = screen_menu(u)
    await reply(m, text, markup)


@dp.message(Command("case"))
async def cmd_case(m: Message):
    u = await get_user(m.from_user)
    text, markup = screen_hub(u)
    await reply(m, text, markup)


@dp.message(Command("profile"))
async def cmd_profile(m: Message):
    u = await get_user(m.from_user)
    text, markup = screen_profile(u)
    await reply(m, text, markup)


@dp.message(Command("notebook"))
async def cmd_notebook(m: Message):
    u = await get_user(m.from_user)
    text, markup = await screen_notebook(u)
    await reply(m, text, markup)


@dp.message(Command("reset"))
async def cmd_reset(m: Message):
    await reply(
        m,
        "⚠️ Начать всё заново? Весь прогресс и блокнот будут удалены.",
        kb([[("Да, сбросить", "reset_yes"), ("Отмена", "menu")]]),
    )


@dp.message()
async def any_text(m: Message):
    u = await get_user(m.from_user)
    text, markup = screen_menu(u)
    await reply(m, "Пользуйся кнопками 👇\n\n" + text, markup)


async def screen_notebook(u):
    if u["case_idx"] >= TOTAL:
        return "📓 Все дела закрыты. Блокнот пуст.", kb([[("🏆 Профиль", "prof")]])
    notes = await get_notes(u["user_id"], u["case_idx"])
    c = CASES[u["case_idx"]]
    num = FIRST_CASE_NUMBER + u["case_idx"]
    if not notes:
        body = "Пока пусто. Допроси подозреваемых и осмотри место."
    else:
        body = "\n\n".join(f"<b>{t}</b>\n{x}" for t, x in notes)
    text = f"📓 <b>Блокнот · Дело №{num}</b> · {c['title']}\n\n{body}"
    if len(text) > 3800:
        text = text[:3800] + "…"
    return text, kb([[("⬅️ К делу", "hub")]])


# ───────────────────────── КНОПКИ ─────────────────────────
@dp.callback_query()
async def on_cb(cb: CallbackQuery):
    u = await get_user(cb.from_user)
    data = cb.data or ""
    uid = u["user_id"]

    if data == "menu":
        text, markup = screen_menu(u)
        return await reply(cb, text, markup)

    if data == "reset_yes":
        await db.execute("DELETE FROM notes WHERE user_id=?", (uid,))
        await db.execute("UPDATE users SET case_idx=0, solved=0, score=0, wrong=0, hints=0 WHERE user_id=?", (uid,))
        await db.commit()
        u = await get_user(cb.from_user)
        text, markup = screen_menu(u)
        return await reply(cb, "Прогресс сброшен.\n\n" + text, markup)

    if data == "hub" or data == "next":
        text, markup = screen_hub(u)
        return await reply(cb, text, markup)

    if data == "prof":
        text, markup = screen_profile(u)
        return await reply(cb, text, markup)

    if data == "nb":
        text, markup = await screen_notebook(u)
        return await reply(cb, text, markup)

    # Дальше — только внутри активного дела
    if u["case_idx"] >= TOTAL:
        text, markup = screen_final(u)
        return await reply(cb, text, markup)

    case = CASES[u["case_idx"]]

    if data.startswith("s:"):
        text, markup = await screen_suspect(u, int(data.split(":")[1]))
        return await reply(cb, text, markup)

    if data.startswith("q:"):
        _, i, j = data.split(":")
        i, j = int(i), int(j)
        s = case["suspects"][i]
        answer = s["a"][j]
        await add_note(uid, u["case_idx"], f"s{i}q{j}", f"{s['name']} · {QUESTIONS[j]}", answer)
        text = f"<b>{s['name']}</b> отвечает:\n\n— {answer}"
        markup = kb([[("❓ Ещё вопрос", f"s:{i}")], [("⬅️ К делу", "hub")]])
        return await reply(cb, text, markup)

    if data == "clues":
        text, markup = await screen_clues(u)
        return await reply(cb, text, markup)

    if data.startswith("c:"):
        k = int(data.split(":")[1])
        name, info = case["clues"][k]
        await add_note(uid, u["case_idx"], f"c{k}", f"Улика · {name}", info)
        text = f"<b>{name}</b>\n\n{info}"
        return await reply(cb, text, kb([[("🔎 К осмотру", "clues")], [("⬅️ К делу", "hub")]]))

    if data == "hint":
        if u["hints"] == 0:
            await db.execute("UPDATE users SET hints=1 WHERE user_id=?", (uid,))
            await db.commit()
            extra = "\n\n<i>Первая подсказка стоит 10 очков.</i>"
        else:
            extra = ""
        return await reply(cb, f"💡 <b>Подсказка:</b> {case['hint']}{extra}", kb([[("⬅️ К делу", "hub")]]))

    if data == "acc":
        text, markup = screen_accuse(u)
        return await reply(cb, text, markup)

    if data.startswith("a:"):
        i = int(data.split(":")[1])
        s = case["suspects"][i]
        if i != case["culprit"]:
            await db.execute("UPDATE users SET wrong=wrong+1 WHERE user_id=?", (uid,))
            await db.commit()
            wrong = u["wrong"] + 1
            text = (
                f"❌ <b>{s['name']}</b> не виновен(а). Улики против него/неё не сходятся.\n"
                f"Ошибок: <b>{wrong}</b> (−20 очков за каждую).\n\nЗагляни в блокнот и подумай ещё."
            )
            if wrong >= 2:
                text += f"\n\n💡 <i>Подсказка: {case['hint']}</i>"
            return await reply(cb, text, kb([[("📓 Блокнот", "nb"), ("⚖️ Ещё раз", "acc")], [("⬅️ К делу", "hub")]]))

        # Верно!
        earned = max(30, 100 - u["wrong"] * 20 - u["hints"] * 10)
        new_idx = u["case_idx"] + 1
        new_solved = u["solved"] + 1
        await db.execute(
            "UPDATE users SET case_idx=?, solved=?, score=score+?, wrong=0, hints=0 WHERE user_id=?",
            (new_idx, new_solved, earned, uid),
        )
        await db.commit()
        text = (
            f"✅ <b>ВЕРНО! Виновен — {s['name']}!</b>\n\n"
            f"{case['solution']}\n\n"
            f"⭐ Очки за дело: <b>+{earned}</b>\n"
            f"🎁 Награда: <b>{case['reward_title']}</b>\n{case['reward_text']}"
        )
        if u["case_idx"] < len(LETTERS):
            text += f"\n\n🔤 Буквы шифра: <b>{letters_line(new_solved)}</b>"
        if new_idx >= TOTAL:
            text += "\n\n" + FINAL_REWARD
            return await reply(cb, text, kb([[("🏆 Профиль", "prof")]]))
        return await reply(cb, text, kb([[("➡️ Следующее дело", "next")], [("🏆 Профиль", "prof")]]))

    await cb.answer()


# ───────────────────────── ЗАПУСК ─────────────────────────
async def main():
    if not TOKEN:
        raise SystemExit("Задай токен: export BOT_TOKEN=123:ABC...")
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
