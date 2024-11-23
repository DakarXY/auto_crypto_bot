import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional, Union, Any

import httpx
from django.conf import settings
from web3 import AsyncWeb3
from web3.types import Address, ChecksumAddress

from trading.models.provider_configs import BSCConfig
from trading.services.pancakeswap import PancakeSwapMonitor

logger = logging.getLogger('trading')


class PriceService:
    def __init__(self):
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(settings.BSC_RPC_URL))

        # PancakeSwap pair ABI minimal for price checks
        self.pair_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "getReserves",
                "outputs": [
                    {"name": "reserve0", "type": "uint112"},
                    {"name": "reserve1", "type": "uint112"},
                    {"name": "blockTimestampLast", "type": "uint32"}
                ],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }
        ]


        self.factory_abi = [
            {
                "constant": True,
                "inputs": [
                    {"name": "tokenA", "type": "address"},
                    {"name": "tokenB", "type": "address"}
                ],
                "name": "getPair",
                "outputs": [{"name": "pair", "type": "address"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }
        ]
        self.monitor = PancakeSwapMonitor()

    async def _get_pair_address(self, token_a: str, token_b: str) -> Optional[Address]:
        await self.monitor.get_configs()
        """Get PancakeSwap pair address"""
        try:
            # Convert addresses to checksum format
            token_a_checksum = AsyncWeb3.to_checksum_address(token_a)
            token_b_checksum = AsyncWeb3.to_checksum_address(token_b)

            factory = self.w3.eth.contract(
                address=self.monitor.bsc_config.factory_address,
                abi=self.factory_abi
            )
            # Get pair address from factory
            pair_address = await factory.functions.getPair(
                token_a_checksum,
                token_b_checksum
            ).call()

            # Check if pair exists
            if pair_address == "0x0000000000000000000000000000000000000000":
                return None

            return Address(bytes.fromhex(pair_address[2:].lower()))

        except Exception as e:
            raise e
            logger.error(f"Error getting pair address: {e}")
            return None

    async def get_token_price(self, token_address: str, quote_token: Optional[str] = None) -> Optional[Decimal]:
        await self.monitor.get_configs()
        """Get current token price in USDT"""
        try:
            if not quote_token:
                quote_token = self.monitor.bsc_config.wallet.currency_to_spend_address

            # Get pair address
            pair_address = await self._get_pair_address(token_address, quote_token)
            if not pair_address:
                return None

            # Create checksum address for contract
            pair_checksum = AsyncWeb3.to_checksum_address(pair_address.hex())

            # Get reserves
            pair_contract = self.w3.eth.contract(
                address=pair_checksum,
                abi=self.pair_abi
            )

            reserves = pair_contract.functions.getReserves().call()

            # Calculate price based on token order
            token_address_checksum = AsyncWeb3.to_checksum_address(token_address)
            quote_token_checksum = AsyncWeb3.to_checksum_address(quote_token)

            if int(token_address_checksum, 16) < int(quote_token_checksum, 16):
                price = Decimal(reserves[1]) / Decimal(reserves[0])
            else:
                price = Decimal(reserves[0]) / Decimal(reserves[1])

            return price

        except Exception as e:
            raise e
            logger.error(f"Error getting token price: {e}")
            return None

    @staticmethod
    async def get_price_history(
            token_address: str,
            interval: str = '1m',
            limit: int = 100
    ) -> List[Dict]:
        """Get token price history"""
        try:
            # Convert address to checksum format
            token_address_checksum = AsyncWeb3.to_checksum_address(token_address)

            # Use PancakeSwap API for price history

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.pancakeswap.info/api/v2/tokens/{token_address_checksum}/price_history",
                    params={
                        "interval": interval,
                        "limit": limit
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('data', [])
            return []

        except Exception as e:
            logger.error(f"Error getting price history: {e}")
            return []

    @staticmethod
    def validate_address(address: str) -> bool:
        """Validate if address is valid"""
        try:
            AsyncWeb3.to_checksum_address(address)
            return True
        except ValueError:
            return False

    async def get_historical_prices(
            self,
            token_address: str,
            start_time: int,
            end_time: int | None = None,
            interval: str = '5m'
    ) -> List[Dict]:
        """
        Get historical price data for token
        interval: 1m, 5m, 15m, 30m, 1h, 4h, 1d
        """
        try:
            if not end_time:
                end_time = int(time.time())

            # Try PancakeSwap API first
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"https://api.pancakeswap.info/api/v2/tokens/{token_address}/prices",
                        params={
                            'from': start_time,
                            'to': end_time,
                            'interval': interval
                        }
                    )

                    if response.status_code == 200:
                        data = response.json().get('data', [])
                        if data:
                            return data
            except Exception as e:
                logger.debug(f"PancakeSwap API error: {e}")

            # Fallback to getting prices from pool events
            prices = []

            # Get pool
            pool_address = await self.monitor._get_pool_address(token_address)
            if not pool_address:
                return []

            # Get pool contract
            pool = self.w3.eth.contract(
                address=self.w3.to_checksum_address(pool_address),
                abi=self.monitor.pool_abi
            )

            # Get Sync events
            sync_events = await self._get_pool_events(
                pool,
                'Sync',
                from_block=await self._get_block_number(start_time),
                to_block=await self._get_block_number(end_time)
            )

            # Process events
            for event in sync_events:
                try:
                    block = await self.w3.eth.get_block(event['blockNumber'])
                    timestamp = block['timestamp']

                    if timestamp < start_time or timestamp > end_time:
                        continue

                    price = await self._calculate_price_from_reserves(
                        token_address,
                        event['args']['reserve0'],
                        event['args']['reserve1'],
                        pool
                    )

                    if price:
                        prices.append({
                            'timestamp': timestamp,
                            'price': price
                        })

                except Exception as e:
                    logger.debug(f"Error processing event: {e}")
                    continue

            return sorted(prices, key=lambda x: x['timestamp'])

        except Exception as e:
            logger.error(f"Error getting historical prices: {e}")
            return []

    @staticmethod
    async def _get_pool_events(
            pool,
            event_name: str,
            from_block: int,
            to_block: Union[int, str]
    ) -> List[Dict]:
        """Get pool events"""
        try:
            events = []
            batch_size = 2000  # BSC limit
            current_block = from_block

            while current_block < to_block:
                end_block = min(current_block + batch_size, to_block)

                batch_events = await pool.events[event_name].get_logs(
                    fromBlock=current_block,
                    toBlock=end_block
                )

                events.extend(batch_events)
                current_block = end_block + 1

            return events

        except Exception as e:
            logger.error(f"Error getting pool events: {e}")
            return []

    async def _calculate_price_from_reserves(
            self,
            token_address: str,
            reserve0: int,
            reserve1: int,
            pool
    ) -> Optional[float]:
        """Calculate token price from reserves"""
        try:
            token0 = await pool.functions.token0().call()
            token1 = await pool.functions.token1().call()

            token0_decimals = await self.monitor._get_token_decimals(token0)
            token1_decimals = await self.monitor._get_token_decimals(token1)

            reserve0_adjusted = Decimal(str(reserve0)) / Decimal(str(10 ** token0_decimals))
            reserve1_adjusted = Decimal(str(reserve1)) / Decimal(str(10 ** token1_decimals))

            if token_address.lower() == token0.lower():
                paired_token = token1
                price_ratio = reserve1_adjusted / reserve0_adjusted
            else:
                paired_token = token0
                price_ratio = reserve0_adjusted / reserve1_adjusted

            # Convert to USD
            if paired_token.lower() == self.monitor.known_tokens['WBNB'].lower():
                bnb_price = await self.monitor.get_bnb_price()
                if not bnb_price:
                    return None
                return float(price_ratio * Decimal(str(bnb_price)))
            elif paired_token.lower() in [
                self.monitor.known_tokens['USDT'].lower(),
                self.monitor.known_tokens['BUSD'].lower()
            ]:
                return float(price_ratio)

            return None

        except Exception as e:
            logger.debug(f"Error calculating price: {e}")
            return None

    async def _get_block_number(self, timestamp: int) -> int:
        """
        Estimate block number from timestamp
        BSC averages 3 second blocks
        """
        current_block = await self.w3.eth.block_number
        current_time = int(time.time())

        # Calculate blocks back
        time_diff = current_time - timestamp
        blocks_back = int(time_diff / 3)  # 3 seconds per block

        return max(0, current_block - blocks_back)