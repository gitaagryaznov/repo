# Добавьте в начало файла:
from bs4 import BeautifulSoup  # <-- Добавить эту строку
import re
import json
from cachetools import TTLCache, cached
import logging
import requests
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import pandas as pd
import pytz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session():
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session


# Конфигурация
TOKEN = "8116484548:AAFtMBtsnzAoWqxyMCZxPRUZlD39lM2xSgQ"
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Криптовалюты
CRYPTO_IDS = {
    "bitcoin": "Bitcoin 🪙",
    "ethereum": "Ethereum ⛓️",
    "tether": "Tether 💵",
    "usd-coin": "USD Coin 💲",
    "binance-coin": "BNB 💎",
    "ripple": "XRP ✨",
    "cardano": "Cardano 🔷",
    "solana": "Solana ☀️",
    "dogecoin": "Dogecoin 🐶",
    "polkadot": "Polkadot 🔴",
    "shiba-inu": "Shiba Inu 🐕",
    "avalanche": "Avalanche ❄️",
    "chainlink": "Chainlink 🔗",
    "litecoin": "Litecoin Ł",
    "uniswap": "Uniswap 🦄",
    "bitcoin-cash": "Bitcoin Cash 💰",
    "algorand": "Algorand ⚡",
    "stellar": "Stellar 🌟",
    "cosmos": "Cosmos 🌌"}

CRYPTO_RECOMMENDATIONS = {
    "bitcoin": "Bitcoin 🪙",
    "ethereum": "Ethereum ⛓️",
    "tether": "Tether 💵",
    "usd-coin": "USD Coin 💲"
}  # <-- Добавлена закрывающая скобка

# Валюты
CURRENCIES = ["USD", "EUR", "CNY"]

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Кэш для хранения данных
cache = TTLCache(maxsize=100, ttl=3600)
# Константы для валютных пар на MOEX
MOEX_CURRENCY_PAIRS = {
    "USD/RUB": "USD000UTSTOM",
    "EUR/RUB": "EUR_RUB__TOM"
}

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

MOEX_API_URL = "https://iss.moex.com/iss/engines/currency/markets/selt/boards/CETS/securities.json"

CURRENCY_PAIRS = {
    "USD/RUB": "USD000UTSTOM",
    "EUR/RUB": "EUR_RUB__TOM",
}


def get_moex_currency_rate(pair_code):
    """Получить курс валютной пары с MOEX"""
    try:
        params = {
            "securities": pair_code,
            "iss.meta": "off",
            "iss.json": "extended",
            "lang": "ru"
        }

        response = requests.get(MOEX_API_URL, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()

            # Ищем данные в marketdata
            market_data = data[1]['marketdata']
            if market_data:
                for item in market_data:
                    if item['SECID'] == pair_code:
                        # Используем последнюю цену или средневзвешенную
                        return str(item.get('MARKETPRICE')) + '-' + str(item.get('MARKETPRICE2'))

            logger.warning(f"Данные для {pair_code} не найдены")
            return None

        logger.error(f"Ошибка HTTP: {response.status_code}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка подключения: {str(e)}")
        return None
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Ошибка парсинга данных: {str(e)}")
        return None


def print_rates():
    """Вывод курсов валют"""
    h=(f"\nКурсы валют MOEX на {datetime.now().strftime('%d.%m.%Y %H:%M')}:\n")
    for pair_name, pair_code in CURRENCY_PAIRS.items():
        rate = get_moex_currency_rate(pair_code)
        if rate:
            h=h+ (f"{pair_name}: {(rate)} ₽\n")
        else:
            h='\n'
    return h


# Функция для получения курсов криптовалют через CoinGecko
@cached(cache)
def get_crypto_prices():
    try:
        url = 'https://api.coingecko.com/api/v3/simple/price'
        params = {
            'ids': ','.join(CRYPTO_IDS.keys()),
            'vs_currencies': 'usd'
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error(f"Ошибка CoinGecko: {str(e)}")
    return None


# Функция для получения курсов валют от ЦБ РФ
def get_financial_data():
    def get_key_rate():
        try:
            url = 'https://www.cbr.ru/hd_base/keyrate/'
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                table = soup.find('table', {'class': 'data'})

                # Ищем последнюю действующую ставку
                for row in reversed(table.find_all('tr')):
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        date_str = cols[0].get_text(strip=True)
                        rate_str = cols[1].get_text(strip=True).replace(',', '.')

                        # Проверяем что дата не в будущем
                        date = datetime.strptime(date_str, '%d.%m.%Y')
                        if date <= datetime.now():
                            return float(rate_str)
                return None
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении ключевой ставки: {str(e)}")
            return None

    def get_currency_rates():
        try:
            response = requests.get('https://www.cbr.ru/scripts/XML_daily.asp', timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                rates = {}

                for valute in root.findall('Valute'):
                    char_code = valute.find('CharCode').text
                    value = valute.find('Value').text.replace(',', '.')
                    nominal = valute.find('Nominal').text

                    if char_code in ['USD', 'EUR', 'CNY']:
                        rates[char_code] = round(float(value) / float(nominal), 4)
                return rates
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении курсов валют: {str(e)}")
            return None

    result = {
        'key_rate': None,
        'USD': None,
        'EUR': None,
        'CNY': None
    }

    # Получаем курсы валют
    currencies = get_currency_rates()
    if currencies:
        result.update(currencies)

    # Получаем ключевую ставку
    key_rate = get_key_rate()
    if key_rate is not None:
        result['key_rate'] = key_rate

    return result



# Функция для получения исторических данных о криптовалюте
def get_crypto_history(crypto_id, days=365):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart"
        params = {
            "vs_currency": "usd",
            "days": days
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return [price[1] for price in response.json()["prices"]]
        return None
    except Exception as e:
        logger.error(f"Ошибка получения истории {crypto_id}: {str(e)}")
        return None


# Функция для получения исторических данных о валюте
def get_currency_history(currency, days=365):
    history = []
    try:
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%d/%m/%Y")
            url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={date}"
            response = requests.get(url)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                for valute in root.findall('Valute'):
                    if valute.find('CharCode').text == currency:
                        value = valute.find('Value').text.replace(',', '.')
                        nominal = float(valute.find('Nominal').text)
                        history.append(float(value) / nominal)
                        break
        return history[::-1]  # Возвращаем в хронологическом порядке
    except Exception as e:
        logger.error(f"Ошибка истории {currency}: {str(e)}")
        return None


# Функция для расчета скользящих средних
def format_number(number):
    """Форматирование числа с пробелом между тысячами и целой частью"""
    return f"{int(round(number, 0)):,}".replace(",", " ")

def calculate_moving_averages(prices):
    return {
        'week': sum(prices[-7:])/7 if len(prices) >=7 else None,
        'month': sum(prices[-30:])/30 if len(prices)>=30 else None,
        'year': sum(prices[-365:])/365 if len(prices)>=365 else None
    }


# Функция для генерации рекомендаций
def generate_recommendation(current_price, ma_week, ma_month, ma_year):
    if None in [ma_week, ma_month, ma_year]:
        return "⚠️ Недостаточно данных"

    conditions = [
        current_price > ma_week,
        current_price > ma_month,
        current_price > ma_year
    ]

    return ["🔴 Продавать", "🟠 Держать", "🟡 Покупать", "🟢 Сильная покупка"][sum(conditions)]


# Функция для отправки сообщения с курсами и рекомендациями
def generate_forecast(prices, days_back=30):
    """Генерация прогноза на основе исторических данных"""
    if not prices or len(prices) < days_back:
        return None

    try:
        # Анализ последних изменений
        changes = []
        for i in range(1, days_back):
            changes.append((prices[-i] - prices[-i - 1]) / prices[-i - 1])

        avg_change = sum(changes) / len(changes)

        # Прогнозные значения
        last_price = prices[-1]
        tomorrow = last_price * (1 + avg_change)
        week = last_price * (1 + avg_change) ** 7
        month = last_price * (1 + avg_change) ** 30

        return {
            'tomorrow': tomorrow,
            'week': week,
            'month': month,
            'trend': "🟢 Рост" if avg_change > 0 else "🔻 Снижение"
        }
    except Exception as e:
        logger.error(f"Ошибка прогнозирования: {str(e)}")
        return None
# Обновленная функция для отправки сообщения
async def send_crypto_prices(context, chat_id):
    try:
        # Получаем все данные параллельно
        crypto_prices = get_crypto_prices()
        moex_rates = print_rates()
        cbr_rates = get_financial_data()
        print(cbr_rates)
        message = "📊 *Актуальные курсы:*\n"

        # Криптовалюты
        if crypto_prices:
            message += "\n💎 *Криптовалюты:*\n"
            for crypto_id, crypto_name in CRYPTO_IDS.items():
                if price := crypto_prices.get(crypto_id, {}).get('usd'):
                    message += f"{crypto_name}: ${price:.2f}\n"

        # Валюты MOEX
        message += moex_rates

        # Валюты ЦБ РФ
        message += "\n🏦 *Курсы ЦБ РФ:*\n"
        message +=f"Ключевая ставка: {cbr_rates['key_rate']}%\n"
        message +=f"USD: {cbr_rates['USD']} ₽\n"
        message +=f"EUR: {cbr_rates['EUR']} ₽\n"
        message +=f"CNY: {cbr_rates['CNY']} ₽\n"


        # Рекомендации для криптовалют
        if crypto_prices:
            message += "\n🔮 *Рекомендации по криптовалютам:*\n"
            for crypto_id, crypto_name in CRYPTO_RECOMMENDATIONS.items():
                if prices := get_crypto_history(crypto_id):
                    ma = calculate_moving_averages(prices)
                    if current_price := (prices[-1] if prices else None):
                        recommendation = generate_recommendation(
                            current_price,
                            ma['week'],
                            ma['month'],
                            ma['year']
                        )
                        message += (
                            f"{crypto_name}: {recommendation}\n"
                            f"  ▫️ Текущая цена: ${format_number(current_price)}\n"
                            f"  ▫️ Средняя за неделю: ${format_number(ma['week']) if ma['week'] else 'N/A'}\n"
                            f"  ▫️ Средняя за месяц: ${format_number(ma['month']) if ma['month'] else 'N/A'}\n"
                            f"  ▫️ Средняя за год: ${format_number(ma['year']) if ma['year'] else 'N/A'}\n\n"
                        )
        # Прогнозы для криптовалют
        if crypto_prices:
            message += "\n🔮 *Прогнозы по криптовалютам:*\n"
            for crypto_id, crypto_name in CRYPTO_RECOMMENDATIONS.items():
                if prices := get_crypto_history(crypto_id, days=60):
                    forecast = generate_forecast(prices)
                    if forecast:
                        message += (
                                    f"{crypto_name} ({forecast['trend']}):\n"
                                    f"  ▫️ Завтра: ~${format_number(forecast['tomorrow'])}\n"
                                    f"  ▫️ Неделя: ~${format_number(forecast['week'])}\n"
                                    f"  ▫️ Месяц: ~${format_number(forecast['month'])}\n\n"
                                )

        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка формирования отчета: {str(e)}")
        await context.bot.send_message(chat_id, "⚠️ Ошибка получения данных")


# Обработчик команды /start
async def start(update, context):
    await update.message.reply_text(
        "Привет! Я КиберЛеха. Буду присылать тебе курсы криптовалют каждое утро в 7:00. Также можешь написать 'Леха привет', чтобы получить текущие курсы.")

    # Планируем задачу на 7:00 каждый день
    chat_id = update.message.chat_id
    context.job_queue.run_daily(send_crypto_prices, time=time(hour=7, minute=0), days=(0, 1, 2, 3, 4, 5, 6),
                                chat_id=chat_id, context=context)


# Обработчик текстовых сообщений
async def handle_message(update, context):
    try:
        # Проверяем наличие сообщения и текста
        if not update.message or not update.message.text:
            logger.warning("Получено пустое сообщение или сообщение без текста")
            return

        text = update.message.text.lower().strip()
        logger.info(f"Получено сообщение: '{text}'")

        # Удаляем специальные символы для лучшего распознавания
        clean_text = re.sub(r'[^a-zа-яё]', '', text)
        triggers = ["лех", "леха", "alekseyss"]

        if any(trigger in clean_text for trigger in triggers):
            logger.info(f"Триггер сработал: '{text}'")
            await send_crypto_prices(context, chat_id=update.message.chat_id)
        else:
            logger.info(f"Триггер не найден: '{text}'")

    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {str(e)}")
        if update.message:
            await update.message.reply_text("⚠️ Ты не готов")


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
