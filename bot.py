import json
import os
import yfinance as yf
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ========= CONFIG =========
BOT_TOKEN = "8400583280:AAH7_6_PiVxodWezPjKM2MPlvwpeeB6YbHY"
WATCHLIST_FILE = "watchlist.json"

# ========= LOGGING =========
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ========= WATCHLIST STORAGE =========
def load_watchlists():
    try:
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_watchlists():
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlists, f, indent=2)

watchlists = load_watchlists()

# ========= TECHNICAL INDICATORS =========
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ========= STOCK ANALYSIS =========
def analyze_stock(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    hist = ticker.history(period="6mo")

    if hist.empty:
        return f"❌ No data found for {symbol}"

    price = info.get("currentPrice")
    target = info.get("targetMeanPrice")
    pe = info.get("forwardPE")
    eps = info.get("trailingEps")
    roe = info.get("returnOnEquity")
    debt = info.get("debtToEquity")
    div = info.get("dividendYield")
    marketcap = info.get("marketCap")
    beta = info.get("beta")
    low52 = info.get("fiftyTwoWeekLow")
    high52 = info.get("fiftyTwoWeekHigh")

    # Technicals
    hist["SMA20"] = hist["Close"].rolling(20).mean()
    hist["EMA20"] = hist["Close"].ewm(span=20).mean()
    hist["RSI"] = calculate_rsi(hist["Close"])

    last = hist.iloc[-1]
    sma_signal = "📈 Bullish" if last["Close"] > last["SMA20"] else "🔻 Bearish"
    ema_signal = "📈 Bullish" if last["Close"] > last["EMA20"] else "🔻 Bearish"
    rsi_signal = (
        "🟢 Oversold (Buy)" if last["RSI"] < 30 else
        "🔴 Overbought (Sell)" if last["RSI"] > 70 else
        "⚪ Neutral"
    )

    # Recommendation
    if price and target:
        if price < target * 0.85:
            rating = "🟢 BUY — undervalued"
        elif price > target * 1.10:
            rating = "🔴 SELL — overvalued"
        else:
            rating = "🟡 HOLD"
    else:
        rating = "⚪ No rating available"

    # Dividend formatting
    div_yield = f"{round(div*100,2)}%" if div else "N/A"

    return f"""
📊 *{symbol} Stock Summary*  

💵 Price: *${price}*
🎯 Target: *${target}*
📈 Forward P/E: *{pe}*
💰 EPS: *{eps}*
📊 ROE: *{roe}*
🏦 Debt/Equity: *{debt}*
💲 Dividend Yield: *{div_yield}*
🏢 Market Cap: *${marketcap}*
📎 Beta: *{beta}*

📉 52W Range: *${low52} → ${high52}*

📍 *Technical Signals*
SMA20: {sma_signal}
EMA20: {ema_signal}
RSI: {rsi_signal}

🧠 Recommendation: *{rating}*
"""

# ========= COMMANDS =========
async def start(update: Update, context):
    await update.message.reply_text(
        "📈 Welcome to Stock Bot!\n"
        "Send a ticker like AAPL or TSLA\n\n"
        "Commands:\n"
        "/watchlist — View watchlist\n"
        "/add AAPL — Add to watchlist\n"
        "/remove TSLA — Remove from watchlist"
    )

async def stock_handler(update: Update, context):
    symbol = update.message.text.upper().strip()

    # Only letters allowed (tickers)
    if not symbol.isalpha():
        return

    text = analyze_stock(symbol)

    buttons = [
        [InlineKeyboardButton("📈 Chart", callback_data=f"chart_{symbol}"),
         InlineKeyboardButton("🧠 Analyze Again", callback_data=f"analyze_{symbol}")],
        [InlineKeyboardButton("➕ Add to Watchlist", callback_data=f"add_{symbol}")]
    ]

    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def chart_callback(update: Update, context):
    query = update.callback_query
    symbol = query.data.split("_")[1]

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="6mo")

    plt.figure()
    plt.plot(hist["Close"])
    plt.title(f"{symbol} — 6M Chart")
    filename = f"{symbol}.png"
    plt.savefig(filename)
    plt.close()

    await query.message.reply_photo(photo=open(filename, "rb"))
    os.remove(filename)

async def watchlist(update: Update, context):
    chat_id = str(update.message.chat_id)

    if chat_id not in watchlists or len(watchlists[chat_id]) == 0:
        await update.message.reply_text("📭 Your watchlist is empty.")
        return

    symbols = "\n".join(f"• {s}" for s in watchlists[chat_id])
    await update.message.reply_text(f"📋 *Your Watchlist:*\n\n{symbols}", parse_mode="Markdown")

async def add(update: Update, context):
    chat_id = str(update.message.chat_id)
    symbol = context.args[0].upper()

    watchlists.setdefault(chat_id, [])
    if symbol not in watchlists[chat_id]:
        watchlists[chat_id].append(symbol)
        save_watchlists()

    await update.message.reply_text(f"✅ {symbol} added to your watchlist")

async def remove(update: Update, context):
    chat_id = str(update.message.chat_id)
    symbol = context.args[0].upper()

    if chat_id in watchlists and symbol in watchlists[chat_id]:
        watchlists[chat_id].remove(symbol)
        save_watchlists()
        await update.message.reply_text(f"❌ {symbol} removed from watchlist")
    else:
        await update.message.reply_text(f"{symbol} not found in watchlist")

# ========= INLINE BUTTON HANDLER =========
async def callback_handler(update: Update, context):
    query = update.callback_query
    data = query.data

    if "chart" in data:
        await chart_callback(update, context)

    if "analyze" in data:
        symbol = data.split("_")[1]
        text = analyze_stock(symbol)
        await query.message.edit_text(text, parse_mode="Markdown")

    if "add" in data:
        symbol = data.split("_")[1]
        chat_id = str(query.message.chat_id)

        watchlists.setdefault(chat_id, [])
        if symbol not in watchlists[chat_id]:
            watchlists[chat_id].append(symbol)
            save_watchlists()

        await query.answer("✅ Added to watchlist")

# ========= MAIN =========
app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("watchlist", watchlist))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("remove", remove))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, stock_handler))
app.add_handler(CallbackQueryHandler(callback_handler))

print("✅ Bot running...")
app.run_polling()
