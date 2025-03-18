from cachetools import TTLCache, cached
import logging
import requests
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from datetime import time, datetime, timedelta
import xml.etree.ElementTree as ET
import re
import pandas as pd
import pytz

# Конфигурация
TOKEN = "8116484548:AAFtMBtsnzAoWqxyMCZxPRUZlD39lM2xSgQ"
ALPHA_VANTAGE_API_KEY = "86MKCLMAXG8H8Q2U"
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Акции
MOEX_API_URL = "https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}.json"
MOEX_STOCKS = {
    "SBER": "Сбербанк 🇷🇺",
    "GAZP": "Газпром ⛽",
    "GMKN": "Норникель ⚙️",
    "AFLT": "Аэрофлот ✈️ (для Маркуши)",
    "MGNT": "Магнит 🛒",
    "FIVE": "X5 Group 🛍️",
    "YNDX": "Яндекс 🌐",
    "PIKK": "ПИК 🏗️"
}

STOCKS = {
    "foreign": {
        "AAPL": "Apple 🍏",
        "MSFT": "Microsoft 💻",
        "TSLA": "Tesla 🚗",
        "AMZN": "Amazon 📦",
        "GOOGL": "Google 🌐"
    }
}

# Криптовалюты
CRYPTO_IDS = {
    "bitcoin": "Bitcoin 🪙",
    "ethereum": "Ethereum ⛓️",
    "litecoin": "Litecoin 💎",
    "ripple": "Ripple 🌊",
    "cardano": "Cardano 🎴",
    "solana": "Solana ☀️",
    "polkadot": "Polkadot ⚫",
    "dogecoin": "Dogecoin 🐶",
    "tether": "Tether (USDT) 💵",
    "streamr": "Streamr DATAcoin 📊"
}

# Валюты
CURRENCIES = ["USD", "EUR", "CNY"]

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# [Остальные функции: get_crypto_prices, get_currency_rates, 
# get_key_rate, get_crypto_history, get_currency_history, 
# calculate_changes остаются без изменений]

if not TOKEN:
    raise ValueError("Токен не найден. Убедитесь, что переменная окружения TOKEN установлена.")

# Функция для получения курсов криптовалют
def get_moex_stocks():
    """Получение данных с MOEX"""
    results = {}
    for ticker, name in MOEX_STOCKS.items():
        try:
            response = requests.get(MOEX_API_URL.format(ticker=ticker), params={
                "iss.meta": "off",
                "iss.only": "marketdata"
            })
            if response.status_code == 200:
                data = response.json()
                price = data['marketdata']['data'][0][12]  # Поле 'LAST'
                results[ticker] = {
                    "name": name,
                    "price": float(price) if price else "N/A",
                    "change": "N/A"
                }
        except Exception as e:
            logger.error(f"Ошибка для {ticker}: {str(e)}")
            results[ticker] = {"name": name, "price": "N/A", "change": "N/A"}
    return results

cache = TTLCache(maxsize=32, ttl=300)
@cached(cache)
def get_stock_prices(stock_type: str):
    """Получение данных об акциях"""
    if stock_type == "russian":
        return get_moex_stocks()
    
    # Для иностранных акций
    stocks = STOCKS[stock_type]
    results = {}
    for symbol, name in stocks.items():
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json().get("Global Quote", {})
                results[symbol] = {
                    "name": name,
                    "price": data.get("05. price", "N/A"),
                    "change": data.get("10. change percent", "N/A")
                }
        except Exception as e:
            logger.error(f"Ошибка для {symbol}: {str(e)}")
            results[symbol] = {"name": name, "price": "N/A", "change": "N/A"}
    return results

def calculate_moving_average(prices, period):
    """Расчет скользящего среднего"""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def get_recommendation(price, ma_week, ma_month, ma_year):
    """Рекомендации на основе скользящих средних"""
    if price > ma_year and price > ma_month and price > ma_week:
        return "🟢 Покупать (сильный рост)"
    elif price < ma_year and price < ma_month and price < ma_week:
        return "🔴 Продавать (сильное падение)"
    else:
        return "🟡 Держать (нейтральный тренд)"

def calculate_missed_profit(prices, investment=100):
    """Расчет упущенной выгоды"""
    if len(prices) < 2:
        return None
    first_price = prices[0][1]
    last_price = prices[-1][1]
    profit = (last_price - first_price) / first_price * investment
    return profit

def get_crypto_prices():
    url = 'https://api.coingecko.com/api/v3/simple/price'
    params = {
        'ids': 'bitcoin,ethereum,litecoin,the-open-network,tramcoin,ripple,cardano,solana,polkadot,dogecoin',
        'vs_currencies': 'usd'
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error("Ошибка при получении данных о курсах криптовалют")
        return None

# Функция для получения курсов валют от ЦБ РФ
def get_currency_rates():
    url = 'https://www.cbr.ru/scripts/XML_daily.asp'
    response = requests.get(url)
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        rates = {}
        for valute in root.findall('Valute'):
            char_code = valute.find('CharCode').text
            value = valute.find('Value').text.replace(',', '.')
            nominal = valute.find('Nominal').text
            rates[char_code] = float(value) / float(nominal)
        return rates
    else:
        logger.error("Ошибка при получении данных о курсах валют")
        return None

# Функция для получения ключевой ставки ЦБ РФ
def get_key_rate():
    try:
        url = 'https://www.cbr.ru/hd_base/keyrate/'
        response = requests.get(url).text

        dates_match = re.search(r'"categories":\[(.+?)\]', response)
        values_match = re.search(r'"data":\[(.+?)\]', response)

        if not dates_match or not values_match:
            logger.error("Не удалось извлечь данные из ответа.")
            return "N/A"

        dates = dates_match.group(1).split(',')
        values = values_match.group(1).split(',')

        all_data = [[date.replace('"', ''), float(value)] for date, value in zip(dates, values)]
        df = pd.DataFrame(all_data, columns=['Date', 'Rate'])
        df['Date'] = pd.to_datetime(df['Date'])

        latest_rate = df[df['Date'] == df['Date'].max()]['Rate'].values[0]
        return latest_rate
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки: {e}")
        return "N/A"

# Функция для получения исторических данных о криптовалютах
def get_crypto_history(crypto_id, days=5):
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()["prices"]
    else:
        logger.error(f"Ошибка при получении данных о {crypto_id}")
        return None

# Функция для получения исторических данных о курсах валют за последние 5 дней
def get_currency_history(days=5):
    history = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%d/%m/%Y")
        url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={date}"
        response = requests.get(url)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            rates = {}
            for valute in root.findall('Valute'):
                char_code = valute.find('CharCode').text
                value = valute.find('Value').text.replace(',', '.')
                nominal = valute.find('Nominal').text
                rates[char_code] = float(value) / float(nominal)
            history.append((date, rates))
        else:
            logger.error(f"Ошибка при получении данных о курсах валют за {date}")
    return history

# Функция для расчета изменений курсов
def calculate_changes(prices):
    if not prices or len(prices) < 2:
        return None
    first_price = prices[0][1]
    last_price = prices[-1][1]
    change = ((last_price - first_price) / first_price) * 100
    return change

# Функция для получения данных об акциях
# Create a cache with a TTL of 5 minutes
cache = TTLCache(maxsize=32, ttl=300)
@cached(cache)
def get_moex_stocks():
    """Получение данных с MOEX"""
    results = {}
    for ticker, name in MOEX_STOCKS.items():
        try:
            response = requests.get(MOEX_API_URL.format(ticker=ticker), params={
                "iss.meta": "off",
                "iss.only": "marketdata"
            })
            if response.status_code == 200:
                data = response.json()
                price = data['marketdata']['data'][0][12]  # Поле 'LAST'
                results[ticker] = {
                    "name": name,
                    "price": float(price) if price else "N/A",
                    "change": "N/A"
                }
        except Exception as e:
            logger.error(f"Ошибка для {ticker}: {str(e)}")
            results[ticker] = {"name": name, "price": "N/A", "change": "N/A"}
    return results

cache = TTLCache(maxsize=32, ttl=300)
@cached(cache)
def get_stock_prices(stock_type: str):
    """Получение данных об акциях"""
    if stock_type == "russian":
        return get_moex_stocks()
    
    # Для иностранных акций
    stocks = STOCKS[stock_type]
    results = {}
    for symbol, name in stocks.items():
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json().get("Global Quote", {})
                results[symbol] = {
                    "name": name,
                    "price": data.get("05. price", "N/A"),
                    "change": data.get("10. change percent", "N/A")
                }
        except Exception as e:
            logger.error(f"Ошибка для {symbol}: {str(e)}")
            results[symbol] = {"name": name, "price": "N/A", "change": "N/A"}
    return results


# Функция для отправки сообщения с курсами криптовалют, валют, акций и статистикой
async def send_crypto_prices(context, chat_id):
    # Получаем курсы криптовалют
    crypto_prices = get_crypto_prices()
    # Получаем курсы валют
    currency_rates = get_currency_rates()
    # Получаем ключевую ставку
    key_rate = get_key_rate()

    if crypto_prices and currency_rates:
        message = "📊 *Курсы криптовалют на сегодня:*\n"
        for crypto, price in crypto_prices.items():
            crypto_name = CRYPTO_IDS.get(crypto, crypto.capitalize())
            message += f"{crypto_name}: ${price['usd']}\n"

        # Добавляем курсы валют
        message += "\n💱 *Курсы валют на сегодня:*\n"
        for currency in CURRENCIES:
            rate = currency_rates.get(currency, "N/A")
            message += f"{currency}/RUB: {rate} руб.\n"

        # Добавляем ключевую ставку
        message += f"\n🏦 *Ключевая ставка ЦБ РФ:* {key_rate}%\n"

        # Блок российских акций
        message += "\n📈 *Топ российских акций (MOEX):*\n"
        ru_stocks = get_stock_prices("russian")
        for data in ru_stocks.values():
            if data["price"] != "N/A":
                price = f"{float(data['price']):.2f}₽"
                message += f"{data['name']}: {price}\n"
            else:
                message += f"{data['name']}: Нет данных\n"

        # Блок иностранных акций
        message += "\n🌍 *Топ зарубежных акций:*\n"
        us_stocks = get_stock_prices("foreign")
        for data in us_stocks.values():
            if data["price"] != "N/A":
                price = f"{float(data['price']):.2f}$"
                change = data["change"].replace("%", "") if data["change"] != "N/A" else "0"
                arrow = "📈" if float(change) >= 0 else "📉"
                message += f"{data['name']}: {price} ({arrow} {change}%)\n"
            else:
                message += f"{data['name']}: Нет данных\n"

        # Отправляем сообщение
        await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text="Не удалось получить курсы.")

# Обработчик команды /start
async def start(update, context):
    await update.message.reply_text("Привет! Я КиберЛеха. Буду присылать тебе курсы криптовалют каждое утро в 7:00. Также можешь написать 'Леха привет', чтобы получить текущие курсы.")

    # Планируем задачу на 7:00 каждый день
    chat_id = update.message.chat_id
    context.job_queue.run_daily(send_crypto_prices, time=time(hour=7, minute=0), days=(0, 1, 2, 3, 4, 5, 6), chat_id=chat_id, context=context)

# Обработчик текстовых сообщений
async def handle_message(update, context):
    text = update.message.text.lower()
    if "лех" in text or "alekseyss" in text:
        # Передаем chat_id явно
        await send_crypto_prices(context, chat_id=update.message.chat_id)

# Основная функция
def main():
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчик команды /start
    application.add_handler(CommandHandler("start", start))

    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
