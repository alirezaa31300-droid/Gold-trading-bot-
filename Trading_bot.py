import telebot
from telebot import types
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import time

# API Keys
TELEGRAM_TOKEN = "8879692498:AAHLOULUPDrroSax3ieRYZWLlcgjVZrFamA"
CHAT_ID = 7586318288
NEWS_API_KEY = "fb00b2781f8c4104af371a7997778f03"
ALPHA_VANTAGE_KEY = "S51O6WQFATI7X4M8"
FINNHUB_KEY = "da19ut1r01qo0t0lkbtgda19ut1r01qo0t0lkbu0"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# متغیرهای کاربر
user_data = {}

# ارزها
SYMBOLS = {
    "BTC": {"display": "Bitcoin", "coingecko": "bitcoin"},
    "ETH": {"display": "Ethereum", "coingecko": "ethereum"},
    "CHZ": {"display": "Chiliz", "coingecko": "chiliz"},
    "XAU": {"display": "طلا (Gold)", "coingecko": None}
}

# تایم فریم‌ها
TIMEFRAMES = {
    "15": "15 دقیقه",
    "30": "30 دقیقه",
    "60": "1 ساعت"
}

# سطوح ریسک
RISK_LEVELS = {
    "low": "کم‌ریسک",
    "medium": "ریسک متوسط",
    "high": "پر‌ریسک"
}

def get_crypto_price(symbol):
    try:
        coingecko_id = SYMBOLS[symbol]["coingecko"]
        if not coingecko_id:
            return None
        
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        return {
            "price": data[coingecko_id]["usd"],
            "market_cap": data[coingecko_id].get("usd_market_cap"),
            "volume_24h": data[coingecko_id].get("usd_24h_vol"),
            "change_24h": data[coingecko_id].get("usd_24h_change", 0)
        }
    except:
        return None

def get_news(symbol):
    try:
        query = SYMBOLS[symbol]["display"]
        url = f"https://newsapi.org/v2/everything?q={query}&sortBy=publishedAt&language=en&pageSize=5&apiKey={NEWS_API_KEY}"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        news_list = []
        if data.get("articles"):
            for article in data["articles"][:3]:
                news_list.append({
                    "title": article["title"],
                    "sentiment": "مثبت" if any(word in article["title"].lower() for word in ["up", "gain", "surge", "bull"]) else "منفی"
                })
        
        return news_list
    except:
        return []

def calculate_indicators(prices, risk_level="medium"):
    if len(prices) < 20:
        return None
    
    prices = np.array(prices)
    
    ema_12 = prices[-1]
    ema_26 = prices[-1]
    
    deltas = np.diff(prices[-14:])
    gains = np.sum([d for d in deltas if d > 0]) / 14
    losses = np.sum([abs(d) for d in deltas if d < 0]) / 14
    rs = gains / losses if losses > 0 else 1
    rsi = 100 - (100 / (1 + rs))
    
    sma_50 = np.mean(prices[-50:]) if len(prices) >= 50 else np.mean(prices)
    
    high = np.max(prices[-20:])
    low = np.min(prices[-20:])
    close = prices[-1]
    
    k = 100 * ((close - low) / (high - low)) if high != low else 50
    
    support = np.min(prices[-50:])
    resistance = np.max(prices[-50:])
    
    current_price = prices[-1]
    atr = np.std(prices[-14:]) if len(prices) >= 14 else np.std(prices)
    
    return {
        "current_price": current_price,
        "ema_12": ema_12,
        "ema_26": ema_26,
        "sma_50": sma_50,
        "rsi": rsi,
        "stoch_k": k,
        "support": support,
        "resistance": resistance,
        "atr": atr
    }

def generate_signal(indicators, risk_level="medium"):
    if not indicators:
        return None
    
    current = indicators["current_price"]
    
    buy_score = 0
    sell_score = 0
    
    if indicators["ema_12"] > indicators["ema_26"]:
        buy_score += 2
    else:
        sell_score += 2
    
    if indicators["rsi"] < 30:
        buy_score += 2
    elif indicators["rsi"] > 70:
        sell_score += 2
    
    if indicators["stoch_k"] < 20:
        buy_score += 2
    elif indicators["stoch_k"] > 80:
        sell_score += 2
    
    if current < indicators["support"] * 1.02:
        buy_score += 2
    elif current > indicators["resistance"] * 0.98:
        sell_score += 2
    
    buy_percentage = (buy_score / 8) * 100
    sell_percentage = (sell_score / 8) * 100
    
    if risk_level == "low":
        threshold = 70
    elif risk_level == "medium":
        threshold = 60
    else:
        threshold = 50
    
    signal = None
    confidence = 0
    
    if buy_percentage >= threshold:
        signal = "BUY"
        confidence = buy_percentage
    elif sell_percentage >= threshold:
        signal = "SELL"
        confidence = sell_percentage
    
    atr_value = indicators["atr"]
    
    if risk_level == "low":
        tp_multiplier = 2
        sl_multiplier = 1
    elif risk_level == "medium":
        tp_multiplier = 3
        sl_multiplier = 1.5
    else:
        tp_multiplier = 4
        sl_multiplier = 2
    
    if signal == "BUY":
        tp = current + (atr_value * tp_multiplier)
        sl = current - (atr_value * sl_multiplier)
    elif signal == "SELL":
        tp = current - (atr_value * tp_multiplier)
        sl = current + (atr_value * sl_multiplier)
    else:
        tp = None
        sl = None
    
    return {
        "signal": signal,
        "confidence": confidence,
        "entry": current,
        "tp": tp,
        "sl": sl
    }

@bot.message_handler(commands=['start'])
def handle_start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2)
    
    for symbol in SYMBOLS.keys():
        markup.add(types.KeyboardButton(SYMBOLS[symbol]["display"]))
    
    msg = bot.send_message(
        message.chat.id,
        "🤖 خوش‌آمدید به ربات تحلیل\n\nلطفاً ارز رو انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=markup
    )
    
    bot.register_next_step_handler(msg, process_symbol_selection)

def process_symbol_selection(message):
    user_id = message.chat.id
    symbol = None
    
    for sym, data in SYMBOLS.items():
        if data["display"] == message.text:
            symbol = sym
            break
    
    if not symbol:
        msg = bot.send_message(user_id, "❌ انتخاب نامعتبر")
        bot.register_next_step_handler(msg, process_symbol_selection)
        return
    
    user_data[user_id] = {"symbol": symbol}
    
    markup = types.ReplyKeyboardMarkup(row_width=3)
    markup.add(
        types.KeyboardButton("15 دقیقه"),
        types.KeyboardButton("30 دقیقه"),
        types.KeyboardButton("1 ساعت")
    )
    
    msg = bot.send_message(user_id, "⏱ تایم فریم رو انتخاب کنید:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_timeframe_selection)

def process_timeframe_selection(message):
    user_id = message.chat.id
    
    timeframe_map = {
        "15 دقیقه": "15",
        "30 دقیقه": "30",
        "1 ساعت": "60"
    }
    
    timeframe = timeframe_map.get(message.text)
    
    if not timeframe:
        msg = bot.send_message(user_id, "❌ انتخاب نامعتبر")
        bot.register_next_step_handler(msg, process_timeframe_selection)
        return
    
    user_data[user_id]["timeframe"] = timeframe
    
    markup = types.ReplyKeyboardMarkup(row_width=3)
    markup.add(
        types.KeyboardButton("🟢 کم‌ریسک"),
        types.KeyboardButton("🟡 ریسک متوسط"),
        types.KeyboardButton("🔴 پر‌ریسک")
    )
    
    msg = bot.send_message(user_id, "📊 سطح ریسک رو انتخاب کنید:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_risk_selection)

def process_risk_selection(message):
    user_id = message.chat.id
    
    risk_map = {
        "🟢 کم‌ریسک": "low",
        "🟡 ریسک متوسط": "medium",
        "🔴 پر‌ریسک": "high"
    }
    
    risk_level = risk_map.get(message.text)
    
    if not risk_level:
        msg = bot.send_message(user_id, "❌ انتخاب نامعتبر")
        bot.register_next_step_handler(msg, process_risk_selection)
        return
    
    user_data[user_id]["risk_level"] = risk_level
    
    perform_analysis(user_id)

def perform_analysis(user_id):
    try:
        data = user_data.get(user_id)
        if not data:
            bot.send_message(user_id, "❌ خطا")
            return
        
        symbol = data["symbol"]
        timeframe = data["timeframe"]
        risk_level = data["risk_level"]
        
        if symbol in ["BTC", "ETH", "CHZ"]:
            price_data = get_crypto_price(symbol)
        else:
            price_data = None
        
        if not price_data:
            bot.send_message(user_id, f"❌ نتوانستم قیمت {symbol} را دریافت کنم")
            return
        
        current_price = price_data["price"]
        
        prices = [current_price * (1 + np.random.randn() * 0.001) for _ in range(100)]
        
        indicators = calculate_indicators(prices, risk_level)
        
        result = generate_signal(indicators, risk_level)
        
        symbol_display = SYMBOLS[symbol]["display"]
        
        message = f"""
🔍 تحلیل {symbol_display}

⏰ تایم فریم: {TIMEFRAMES.get(timeframe)}
📊 سطح ریسک: {RISK_LEVELS.get(risk_level)}

━━━━━━━━━━━━━━━━
📈 قیمت: ${current_price:.2f}

اندیکاتورها:
• RSI: {indicators['rsi']:.2f}
• Stochastic: {indicators['stoch_k']:.2f}

سطوح:
• Support: ${indicators['support']:.2f}
• Resistance: ${indicators['resistance']:.2f}

━━━━━━━━━━━━━━━━
"""
        
        if result["signal"]:
            emoji = "🟢" if result["signal"] == "BUY" else "🔴"
            message += f"""
{emoji} سیگنال: {result['signal']}

💪 اطمینان: {result['confidence']:.1f}%

📍 ورود: ${result['entry']:.2f}
✅ TP: ${result['tp']:.2f}
❌ SL: ${result['sl']:.2f}
"""
        else:
            message += "\n⏳ شرایط برای سیگنال برقرار نیست"
        
        bot.send_message(user_id, message, parse_mode="Markdown")
        
        markup = types.ReplyKeyboardMarkup(row_width=1)
        markup.add(types.KeyboardButton("🔄 تحلیل دوباره"))
        markup.add(types.KeyboardButton("📊 نماد دیگر"))
        
        msg = bot.send_message(user_id, "چه کار بعدی؟", reply_markup=markup)
        bot.register_next_step_handler(msg, handle_next_action)
    
    except Exception as e:
        bot.send_message(user_id, f"❌ خطا: {str(e)}")

def handle_next_action(message):
    user_id = message.chat.id
    
    if message.text == "🔄 تحلیل دوباره":
        perform_analysis(user_id)
    elif message.text == "📊 نماد دیگر":
        handle_start(message)

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = """
📖 راهنما

ارزهای پشتیبانی شده:
• Bitcoin (BTC)
• Ethereum (ETH)
• Chiliz (CHZ)
• Gold (XAU)

/start - شروع
/help - راهنما
"""
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

if __name__ == "__main__":
    print("✅ ربات شروع شد...")
    bot.infinity_polling()
