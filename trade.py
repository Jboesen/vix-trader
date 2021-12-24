import datetime as dt
from IPython.display import display
import json
import numpy as np
import pandas as pd
from collections import deque
import requests
import requests.api
from ransac import slope
from sklearn.linear_model import LinearRegression
from threading import Thread
from time import sleep
import websocket
from config import *

# initialize
is_open = True
# initialize current price queue
current_prices = deque([], maxlen=10)
# connect and authenticate to regular
account = json.loads(requests.get(ACCOUNT_URL, headers=keys).content)
# print(account)
if not account['status'] == 'ACTIVE':
    exit(1)
# 1 = longing, 2 = shorting, 3 = hard shorting
prev_order = 0
# Prevent trying to trade before the previous trade is done
trading = False


def on_open(ws):
    print("opened")
    login = {'action': 'auth', 'key': f'{KEY}', 'secret': f'{SECRET}'}
    ws.send(json.dumps(login))
    # one-minute bars
    listen_message = {'action': 'subscribe', 'bars':['VXX']}
    ws.send(json.dumps(listen_message))


def on_message(ws, message):
    print(message)
    bar = json.loads(message)[0]
    avg = (bar['o'] + bar['l']) / 2
    current_prices.append(avg)
    print(f"trading: {trading}")
    if not trading:
        Thread(target=trade, args=("VXX", )).start()


def liquidate():
    # cancel open orders
    print("liquidating")
    open_orders = requests.get(f"{BASE_URL}/orders", headers=keys).text
    if open_orders:
        requests.delete(f"{BASE_URL}/orders", headers=keys)
    # get all positions
    positions = json.loads(requests.get(f"{BASE_URL}/positions", headers=keys).text)
    df = pd.DataFrame(positions)
    # is this the right way to iterate?
    for r in df.to_dict(orient="records"):
        if r['side'] == 'long':
            print(f"selling {r['symbol']}")
            payload = {
                'symbol' : r['symbol'],
                'qty' : r['qty'],
                'side' : 'sell',
                'type' : 'market', 
                'time_in_force' : 'day',
            }
            requests.post(f"{BASE_URL}/orders", headers=keys, json=payload)
        if r['side'] == 'short':
            print(f"buying {r['symbol']}")
            payload = {
                'symbol' : r['symbol'],
                'qty' : r['qty'],
                'side' : 'buy',
                'type' : 'market', 
                'time_in_force' : 'day',
            }
            requests.post(f"{BASE_URL}/orders", headers=keys, json=payload)
            # print(receipt.text)
    for i in range(5):
        sleep(2)
        positions = json.loads(requests.get(f"{BASE_URL}/positions", headers=keys).text)
        print(positions)
        if not positions:
            print("liquidating successful")
            return
    # restart
    print("calling main")
    __main__()


def trade(symbol):
    print("top of trade")
    global trading
    trading = True
    r = requests.get(f"{BASE_URL}/account", headers=keys)
    # store cash for later
    cash = float(json.loads(r.text)['cash']) 
    print(f"cash: {cash}")
    print("done checking on account...")
    
    # get vix price
    if is_open:
        global prev_order
        # get data from past year
        start_obj = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=150)
        start = start_obj.strftime("%Y-%m-%d")
        end_obj = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        end = end_obj.strftime("%Y-%m-%d")

        # print(start)
        # print(end)
        payload = {
            'start' : start,
            'end' : end,
            'limit' : '10000',
            'timeframe' : '15Min'
        }
        r = requests.get(f"{DATA_URL}/stocks/{symbol}/bars", params=payload, headers=keys)
        # we now have a list of bars
        # predict data for right now
        predictions = slope(r)
        # print("got slope prediction")
        # print(predictions)
        p_hat = predictions[0]
        m_hat = predictions[1][0][0]
        # get current price
        p = current_prices[-1]
        # calculate local slope
        y = np.array(current_prices)
        x = np.array(range(len(y))).reshape((-1, 1))
        model = LinearRegression().fit(x, y)
        local_slope = model.coef_[0]
        # if current price is significantly above predicted and local slope is positive, short it on margin
        # this is theroretically the minimum profitable price but maybe be more conservative
        # p > 1.0089 * p_hat
        print(f"Prev order: {prev_order}")
        if p > p_hat and local_slope > m_hat and prev_order != 3:
            print("going for hard short...")
            liquidate()
            payload = {
                'symbol' : symbol,
                'notional' : cash,
                'side' : 'sell',
                'type' : 'market', 
                'time_in_force' : 'day',
                }
            order = requests.post(f"{BASE_URL}/orders", headers=keys, json=payload)
            print(order.text)
            prev_order = 3
            trading = False
            return
        # if current price is below predicted, long it
        # I have no idea here, but this would be assuming low price regresses to the mean within a day
        # (4 15-min intervals/hour * 8 hours/day)
        lower_bound = 1 / 1.0089 * p_hat - 4 * 8 * m_hat
        if p < lower_bound and prev_order != 1:
            print("going long")
            liquidate()
            payload = {
                'symbol' : symbol,
                'notional' : str(cash),
                'side' : 'buy',
                'type' : 'market', 
                'time_in_force' : 'day',
                }
            order = requests.post(f"{BASE_URL}/orders", headers=keys, json=payload)
            print(order.text)
            prev_order = 1
            trading = False
            return
        
        if prev_order != 2:
            print("chillin w voo")
            liquidate()
            payload = {
                'symbol' : 'VOO',
                'notional' : str(cash),
                'side' : 'buy',
                'type' : 'market', 
                'time_in_force' : 'day',
                }
            order = requests.post(f"{BASE_URL}/orders", headers=keys, json=payload)
            print(order.text)
            prev_order = 2
            trading = False
            return
        print("Chilling because none of the conditions were met")
        trading = False
        # TODO: change this as needed
        # sleep(30)


def __main__():
    socket = "wss://stream.data.alpaca.markets/v2/iex"
    ws = websocket.WebSocketApp(socket, on_open=on_open, on_message=on_message)
    ws.run_forever()

if __name__ == '__main__':
    __main__()
