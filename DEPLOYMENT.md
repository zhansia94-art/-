# 🚀 Развертывание бота на Railway

## Быстрый старт (5 минут)

### 1️⃣ Получи токен бота
1. Откой Telegram → найди **@BotFather**
2. Отправь `/newbot` и следуй инструкциям
3. Скопируй полученный токен вида: `123456789:ABCdefGHIjklmNO...`

### 2️⃣ Загрузи бота на GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/ТВОЙ_ЮЗЕР/detective-bot.git
git push -u origin main
```

### 3️⃣ Развернись на Railway
1. Перейди на [railway.app](https://railway.app)
2. Нажми **"Create New"** → **"Deploy from GitHub"**
3. Выбери свой репозиторий
4. ⚠️ **ВАЖНО!** Railway автоматически заметит `Dockerfile` и построит образ из него
   - Это безопаснее чем `runtime.txt` (нет проблем с attestations)
5. Нажми **"Deploy"**

**Если Railway всё равно ругается на runtime.txt:**
- Удали файл `runtime.txt` перед загрузкой на GitHub
- Dockerfile заменит его функциональность

### 4️⃣ Добавь переменные окружения
1. В панели Railway нажми на проект
2. Открой вкладку **"Variables"**
3. Добавь переменную:
   - **KEY:** `BOT_TOKEN`
   - **VALUE:** `твой_токен_от_BotFather`

### 5️⃣ Готово! 🎉
Бот будет работать 24/7

---

## Альтернатива: Запуск локально

```bash
# 1. Установи Python 3.8+
# 2. Установи зависимости
pip install -r requirements.txt

# 3. Запусти бота
export BOT_TOKEN="твой_токен"
python bot.py
```

---

## Ограничения Railway (Free Tier)
- ✅ 500 часов в месяц (достаточно для постоянной работы)
- ✅ 5 проектов
- ✅ Без кредитной карты
- ⚠️ После исчерпания часов понадобится оплата

---

## Вопросы?
Проверь логи в Railway → вкладка "Logs"
