import logging
from decimal import Decimal

from binance.client import Client


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str):
        self.client = Client(api_key, api_secret)

    async def get_usdt_balance(self) -> Decimal:
        """Get USDT balance"""
        try:
            account = self.client.get_account()
            for balance in account['balances']:
                if balance['asset'] == 'USDT':
                    return Decimal(balance['free'])
            return Decimal('0')
        except Exception as e:
            logging.error(f"Error getting USDT balance: {e}")
            return Decimal('0')

    async def buy_token(self, symbol: str, amount: Decimal) -> dict:
        """Buy token with USDT"""
        try:
            order = self.client.create_order(
                symbol=f"{symbol}USDT",
                side=Client.SIDE_BUY,
                type=Client.ORDER_TYPE_MARKET,
                quoteOrderQty=str(amount)
            )
            return {
                'success': True,
                'order': order
            }
        except Exception as e:
            logging.error(f"Error buying token: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def sell_token(self, symbol: str, amount: Decimal) -> dict:
        """Sell token for USDT"""
        try:
            order = self.client.create_order(
                symbol=f"{symbol}USDT",
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=str(amount)
            )
            return {
                'success': True,
                'order': order
            }
        except Exception as e:
            logging.error(f"Error selling token: {e}")
            return {
                'success': False,
                'error': str(e)
            }
