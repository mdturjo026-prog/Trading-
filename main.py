import os
from flask import Flask, request
import requests
import json
from datetime import datetime

TOKEN = os.environ.get('TOKEN')
PRIVATE_CHAT_ID = os.environ.get('PRIVATE_CHAT_ID')
GROUP_CHAT_ID = os.environ.get('GROUP_CHAT_ID')

app = Flask(__name__)
BALANCE_FILE = "balance.json"

def load_balance():
    try:
        with open(BALANCE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"usdt": 10000, "position": None, "live_alerts": {}}

def save_balance(data):
    with open(BALANCE_FILE, 'w') as f:
        json.dump(data, f)

def send_telegram(msg, to_group=False):
    chat_id = GROUP_CHAT_ID if to_group else PRIVATE_CHAT_ID
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print(f"Received: {data}")
    balance = load_balance()

    # Live Signal Handle
    if data.get('type') == 'live':
        pair = data['pair']
        signal = data['signal']
        price = data['price']

        if balance['live_alerts'].get(pair) == signal:
            return "Live Duplicate Ignored"

        balance['live_alerts'][pair] = signal
        save_balance(balance)

        live_msg = f"⚡ <b>LIVE {signal} SIGNAL</b>\n\nPair: <code>{pair}</code>\nPrice: <code>{price}</code>\nTime: {datetime.now().strftime('%H:%M:%S')}\n\n<i>Waiting for candle close... 😬</i>"
        send_telegram(live_msg, to_group=True)
        return "Live Sent"

    # Confirm Signal - তোমার 4টা ফিল্টার
    if data['is_big']:
        send_telegram(f"❌ <b>Signal Rejected</b>\nPair: {data['pair']}\nReason: Big Candle 😬")
        return "Rejected: Big Candle"
    if data['is_doji']:
        send_telegram(f"❌ <b>Signal Rejected</b>\nPair: {data['pair']}\nReason: Doji 😬")
        return "Rejected: Doji"
    if data['body'] < 80:
        send_telegram(f"❌ <b>Signal Rejected</b>\nPair: {data['pair']}\nReason: Body {data['body']:.1f}% < 80% 😬")
        return "Rejected: Body"
    if data['is_gap']:
        send_telegram(f"❌ <b>Signal Rejected</b>\nPair: {data['pair']}\nReason: Gap Detected 😬")
        return "Rejected: Gap"

    # Filter Pass = Confirm Signal + Paper Trade
    price = float(data.get('price', 0))
    pair = data['pair']
    signal = data['signal']
    balance['live_alerts'].pop(pair, None)

    if signal == "BUY" and balance['position'] == None:
        amount_usdt = balance['usdt'] * 0.2
        qty = amount_usdt / price
        balance['usdt'] -= amount_usdt
        balance['position'] = {"side": "LONG", "qty": qty, "entry": price, "pair": pair}
        save_balance(balance)

        group_msg = f"🚀 <b>CONFIRMED {signal}</b>\n\nPair: <code>{pair}</code>\nEntry: <code>{price}</code>\nLeverage: 10x-20x\nSL: <code>{price * 0.98:.2f}</code>\nTP1: <code>{price * 1.02:.2f}</code>\n\n<i>All Filters Passed ✅</i>\n#FutureSignal"
        send_telegram(group_msg, to_group=True)

        private_msg = f"✅ <b>PAPER BUY</b>\nPair: {pair}\nQty: {qty:.4f}\nUsed: {amount_usdt:.2f} USDT\nBalance: {balance['usdt']:.2f} USDT"
        send_telegram(private_msg)

    elif signal == "SELL" and balance['position'] and balance['position']['side'] == "LONG":
        pos = balance['position']
        pnl = (price - pos['entry']) * pos['qty']
        pnl_percent = (price - pos['entry']) / pos['entry'] * 100
        balance['usdt'] += pos['qty'] * price
        balance['position'] = None
        save_balance(balance)

        emoji = "🟢" if pnl > 0 else "🔴"
        group_msg = f"{emoji} <b>CLOSE {pos['pair']}</b>\n\nExit: <code>{price}</code>\nPnL: {pnl_percent:.2f}%\n\n<i>Paper Trade Closed</i>\n#FutureSignal"
        send_telegram(group_msg, to_group=True)

        private_msg = f"{emoji} <b>PAPER SELL</b>\nPnL: {pnl:.2f} USDT ({pnl_percent:.2f}%)\nNew Balance: {balance['usdt']:.2f} USDT"
        send_telegram(private_msg)
    else:
        send_telegram(f"⚠️ <b>Signal Ignored</b>\nPair: {pair}\nReason: Already in position")

    return "OK"

@app.route('/balance')
def check_balance():
    b = load_balance()
    if b['position']:
        pos = b['position']
        return f"Balance: {b['usdt']:.2f} USDT<br>Position: {pos['side']} {pos['qty']:.4f} {pos['pair']} @ {pos['entry']}"
    return f"Balance: {b['usdt']:.2f} USDT<br>Position: None"

@app.route('/')
def home():
    return "Future Signal Bot Running ✅"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
