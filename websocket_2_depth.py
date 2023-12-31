import asyncio
from binance import AsyncClient, BinanceSocketManager
import os
from dotenv import load_dotenv
import logging
import time

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def orders_router(client, bids, asks):
    await send_orders(client, depth=bids, side='BUY')
    await send_orders(client, depth=asks, side='SELL')

async def send_orders(client, depth, side):
    tasks = [create_order(client, k, v, side) for k,v in depth.items()]
    results = await asyncio.gather(*tasks)
    logging.info(results)
    
async def create_order(client, price, size, side):
    try:
        order = await client.create_test_order(
                        symbol='NEOUSDT',
                        side=side,
                        type='LIMIT',
                        timeInForce='GTC',
                        quantity=size,
                        price=price
        )
        #logging.info(f'order has been created: {order}')
        return order
    except Exception as e:
        logging.error(f'Error creating order: {e}')
        return None
    
async def order_cancelling(client):
    #get all open orders
    orders = await client.get_open_orders(symbol='NEOUSDT')
    #checking if there are open orders to cancel them
    if orders:
        for order in orders:
            id = order['orderId']
            cancelled = await client.cancel_order(symbol='NEOUSDT', orderId=id)
            logging.info(f'order {id} has been cancelled: {cancelled}')
    else:
        pass

async def hedging(client):
    #The script assumes we start with 10,000 NEO and 100,000 USDT
    initial_token_balance = 10000
    #checking spot balances (the market I am making)
    spot_token_balance = await client.get_asset_balance(asset='NEO')
    must_be_hedged = initial_token_balance - spot_token_balance
    #looking what's actually hedged on futures
    is_hedged = await client.futures_position_information('NEOUSDT')['positionAmt']
    is_hedged = float(is_hedged)
    to_hedge = must_be_hedged - is_hedged
    #send a market order to hedge the unhedged exposure immidiately
    if to_hedge > 0:
        side = 'BUY'
    else:
        side = 'SELL'
    if abs(to_hedge) > 10:
        order = await client.futures_create_order(
                            symbol = 'NEOUSDT',
                            side=side,
                            type='MARKET',
                            uantity=round(abs(to_hedge),2)
        )
        logging.info(f'futures market hedge order sent {order}')



async def main():
    binance_key = os.getenv("BINANCE_API_KEY")
    binance_secret = os.getenv("BINANCE_SECRET")
    client = AsyncClient(binance_key, binance_secret)
    bm = BinanceSocketManager(client)

    socket = bm.futures_depth_socket('neousdt', 5)


    async with socket as tscm:
        asks = {}
        bids = {}
        margin = 0.005 #50 bps
        for _ in range(5):
            start_time = time.time()
            res = await tscm.recv()
            logging.info(f'time_to_receive data: {time.time() - start_time}')

            start_time = time.time()
            for k,v in res['data'].items():
                if k == 'b':
                    for i in v:
                        bids[round(float(i[0]) * (1 - margin), 2)] = float(i[1])
                elif k == 'a':
                    for i in v:
                        asks[round(float(i[0]) * (1 + margin), 2)] = float(i[1])
            logging.info(f'time_to_loop: {time.time() - start_time}')

            start_time = time.time()
            await asyncio.gather(
                order_cancelling(client),
                hedging(client),
                orders_router(client, bids, asks)
            )
            logging.info(f'time to print: {time.time() - start_time}')

if __name__ == "__main__":
    asyncio.run(main())