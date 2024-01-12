import requests
import signal
from time import sleep
import sys

class ApiException (Exception):
    pass

def signal_handler (signum, frame):
    global shutdown
    signal. signal(signal.SIGINT, signal.SIGDFL)
    shutdown = True

API_KEY = {'X-API-Key': 'rotman'}
shutdown = False


SPEEDBUMP = 0.1
MAX_VOLUME = {'AC': 1600, 'RY': 1600, 'CNR': 1600}

MAX_ORDERS = 5

SPREAD = .05

def get_tick(session):
    resp = session.get('http://localhost:9999/v1/case')
    if resp.ok:
        case = resp.json()
        return case['tick']
    raise ApiException('Authorization error. Please check API key.')

def ticker_bid_ask(session, ticker):
    payload = {'ticker': ticker}
    resp = session.get('http://localhost:9999/v1/securities/book', params=payload)
    if resp.ok:
        book = resp. json()
        return book['bids'][0]['price'], book['asks'][0]['price']
    raise ApiException('Authorization error. Please check API key.')

def open_sells(session, sym):
    resp = session.get('http://localhost:9999/v1/orders?status=OPEN')
    if resp.ok:
        open_sells_volume = 0 # total combined volume of all open sells
        ids = []
        prices = []
        order_volumes = []
        volume_filled = []
        open_orders = resp.json()
        for order in open_orders:
            if order['action'] == 'SELL' and order['ticker'] == sym:
                volume_filled.append(order['quantity_filled'])
                order_volumes.append(order['quantity'])
                open_sells_volume = open_sells_volume + order['quantity']
                prices.append(order['price'])
                ids.append(order['order_id'])
    return volume_filled, open_sells_volume, ids, prices, order_volumes

def open_buys(session, sym):
    resp = session.get('http://localhost:9999/v1/orders?status=OPEN')
    if resp.ok:
        open_buys_volume = 0
        ids = []
        prices = []
        order_volumes = []
        volume_filled = []
        open_orders = resp.json()
        for order in open_orders:
            if order['action'] == 'BUY' and order['ticker'] == sym:
                open_buys_volume = open_buys_volume + order['quantity']
                volume_filled.append(order['quantity_filled'])
                order_volumes.append(order['quantity'])
                prices.append(order['price'])
                ids.append(order['order_id'])
    return volume_filled, open_buys_volume, ids, prices, order_volumes

def buy_sell(session, sell_price, buy_price, sym):
    for i in range (MAX_ORDERS):
        session.post('http://localhost:9999/v1/orders', params = {'ticker': sym, 'type': 'LIMIT', 'quantity': MAX_VOLUME[sym], 'price': sell_price, 'action': 'SELL'})
        session.post('http://localhost:9999/v1/orders', params = {'ticker': sym, 'type': 'LIMIT', 'quantity': MAX_VOLUME[sym], 'price': buy_price, 'action': 'BUY'})

def re_order(session, number_of_orders, ids, volumes_filled, volumes, price, action, sym):
    for i in range(number_of_orders):
        id = ids[i]
        volume = volumes[i]
        volume_filled = volumes_filled[i]
        
        if (volume_filled != 0):
            volume = MAX_VOLUME[sym] - volume_filled
        
        deleted = session.delete('http://localhost:9999/v1/orders/{}'.format(id))
        if (deleted.ok):
            session.post('http://localhost:9999/v1/orders', params = {'ticker': sym, "type": 'LIMIT', 'quantity': volume, 'price': price, 'action': action})

def main():
    single_side_transaction_time = {'AC': 0, 'RY': 0, 'CNR': 0}
    single_side_filled = {'AC': False, 'RY': False, 'CNR': False}

    with requests.Session() as s:
        s.headers.update(API_KEY)
        tick = get_tick(s)

        while tick > 0 and tick < 295 and not shutdown:
            for sym in ['AC', 'RY', 'CNR']:
                volume_filled_sells, open_sells_volume, sell_ids, sell_prices, sell_volumes = open_sells(s, sym)
                volume_filled_buys, open_buys_volume, buy_ids, buy_prices, buy_volumes = open_buys(s, sym)
                bid_price, ask_price = ticker_bid_ask(s, sym)

                if(open_sells_volume == 0 and open_buys_volume == 0):
                    single_side_filled[sym] = False
                    bid_ask_spread = ask_price - bid_price
                    sell_price = ask_price
                    buy_price = bid_price
                    if(bid_ask_spread >= SPREAD):
                        buy_sell(s, sell_price, buy_price, sym)
                        sleep(SPEEDBUMP)

                else:
                    if len(sell_prices) > 0:
                        sell_price = sell_prices[0]
                    if len(buy_prices) > 0:
                        buy_price = buy_prices[0]
                    
                    if (not single_side_filled[sym] and (open_buys_volume == 0 or open_sells_volume == 0)):
                        single_side_filled[sym] = True
                        single_side_transaction_time[sym] = tick

                    if (open_sells_volume == 0):
                        if (buy_price == bid_price):
                            continue
                    
                        elif(tick - single_side_transaction_time[sym] >= 3):
                            next_buy_price = bid_price + .01
                            potential_profit = sell_price - next_buy_price - .02
                            if(potential_profit >= .01 or tick - single_side_transaction_time[sym] >= 6):
                                action = 'BUY'
                                number_of_orders = len(buy_ids)
                                buy_price = bid_price + .01
                                price = buy_price
                                ids = buy_ids
                                volumes = buy_volumes
                                volumes_filled = volume_filled_buys
                                re_order(s, number_of_orders, ids, volumes_filled, volumes, price, action, sym)
                                sleep (SPEEDBUMP)

                    elif(open_buys_volume == 0):
                        if (sell_price == ask_price):
                            continue # next iteration of 100p

                        elif(tick - single_side_transaction_time[sym] >= 3):
                            next_sell_price = ask_price - .01
                            potential_profit = next_sell_price - buy_price - .02
                            if(potential_profit >= .01 or tick - single_side_transaction_time[sym] >= 6):
                                action = 'SELL'
                                number_of_orders = len(sell_ids)
                                sell_price = ask_price - .01
                                price = sell_price
                                ids = sell_ids
                                volumes = sell_volumes
                                volumes_filled = volume_filled_sells
                                re_order(s, number_of_orders, ids, volumes_filled, volumes, price, action, sym)
                                sleep (SPEEDBUMP)
            tick = get_tick(s)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()
