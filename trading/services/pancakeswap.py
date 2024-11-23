import logging
import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from pythonpancakes import PancakeSwapAPI
from web3 import AsyncWeb3
from web3.types import ChecksumAddress
import httpx

from ..models.provider_configs import BSCConfig
from ..models.config import AutoTradingConfig

logger = logging.getLogger('trading')

timeout_settings = httpx.Timeout(
    connect=60.0,  # connection timeout
    read=60.0,  # read timeout
    write=60.0,  # write timeout
    pool=60.0  # pool timeout
)


class PancakeSwapMonitor:
    config: AutoTradingConfig
    bsc_config: BSCConfig
    rpc_nodes: Any
    known_tokens: Any
    router: Any
    router_abi: Any
    w3: AsyncWeb3

    def __init__(self):
        self.current_rpc_index = 0

        self.token_abi = self._load_token_abi()
        self.ps = PancakeSwapAPI()
        self.factory_abi = [
            # Get Pair
            {
                "constant": True,
                "inputs": [
                    {"internalType": "address", "name": "tokenA", "type": "address"},
                    {"internalType": "address", "name": "tokenB", "type": "address"}
                ],
                "name": "getPair",
                "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            # All Pairs
            {
                "constant": True,
                "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "name": "allPairs",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            # All Pairs Length
            {
                "constant": True,
                "inputs": [],
                "name": "allPairsLength",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            # Create Pair Event
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "internalType": "address", "name": "token0", "type": "address"},
                    {"indexed": True, "internalType": "address", "name": "token1", "type": "address"},
                    {"indexed": False, "internalType": "address", "name": "pair", "type": "address"},
                    {"indexed": False, "internalType": "uint256", "name": "", "type": "uint256"}
                ],
                "name": "PairCreated",
                "type": "event"
            },
            # INIT_CODE_PAIR_HASH
            {
                "constant": True,
                "inputs": [],
                "name": "INIT_CODE_PAIR_HASH",
                "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            # Fee To
            {
                "constant": True,
                "inputs": [],
                "name": "feeTo",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            # Fee To Setter
            {
                "constant": True,
                "inputs": [],
                "name": "feeToSetter",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }
        ]
        self.pool_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "getReserves",
                "outputs": [
                    {"name": "_reserve0", "type": "uint112"},
                    {"name": "_reserve1", "type": "uint112"},
                    {"name": "_blockTimestampLast", "type": "uint32"}
                ],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "token0",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "token1",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            }
        ]

    def _initialize_web3(self) -> AsyncWeb3:
        """Initialize AsyncWeb3 with current RPC node"""
        return AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.rpc_nodes[self.current_rpc_index]))

    async def get_configs(self):
        self.config = await AutoTradingConfig.get_config()
        self.bsc_config = await BSCConfig.get_config()
        self.rpc_nodes = self.bsc_config.rpc_nodes.split(" ")
        self.known_tokens = self._load_known_tokens()
        self.w3 = self._initialize_web3()
        self.router_abi = await self._load_router_abi()
        self.router = self.w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(self.bsc_config.router_address),
            abi=self.router_abi
        )

    def _load_known_tokens(self):
        known_tokens_string_tuples = self.bsc_config.known_tokens.split(" ")
        known_tokens_tuples = [(token.split(",")[0], token.split(",")[1]) for token in known_tokens_string_tuples]
        return {
            name: AsyncWeb3.to_checksum_address(addr) for name, addr in known_tokens_tuples
        }

    async def _load_router_abi(self) -> List:
        """Load PancakeSwap Router ABI"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.bsc_config.main_api_url,
                    params={
                        "module": "contract",
                        "action": "getabi",
                        "address": self.bsc_config.router_address,
                        "apikey": settings.BSCSCAN_API_KEY
                    }
                )
                data = response.json()
                if data["status"] == "1":
                    return data["result"]
            return []
        except Exception as e:
            logger.error(f"Error loading router ABI: {e}")
            return []

    @staticmethod
    def _load_token_abi() -> List:
        """Load ERC20 Token ABI"""
        # Basic ERC20 ABI with required methods
        return [
            # Standard ERC20 Functions
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "totalSupply",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            },

            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }
        ]

    async def get_new_listings(self) -> List[Dict]:
        await self.get_configs()
        """Get new token listings"""
        try:
            # Get latest transactions
            transactions = await self._get_latest_transactions()

            new_listings = []
            for tx in transactions:
                try:
                    # Parse liquidity addition
                    if not self._is_liquidity_addition(tx):
                        continue

                    # Parse token addresses
                    token_pair = self._parse_liquidity_transaction(tx)
                    if not token_pair:
                        continue

                    token_a, token_b = token_pair

                    # Find new token
                    new_token = await self._find_new_token(token_a, token_b)
                    if not new_token:
                        continue

                    # Get token info
                    token_info = await self._get_token_info(new_token)
                    if not token_info:
                        continue

                    # Get pool address
                    pool_address = await self._get_pool_address(new_token, tx['hash'])
                    if not pool_address:
                        continue

                    # Get initial price
                    initial_price = await self._get_token_usd_price(new_token, pool_address)
                    if not initial_price:
                        continue

                    new_listings.append({
                        'token_address': new_token,
                        'token_symbol': token_info['symbol'],
                        'token_name': token_info.get('name', token_info['symbol']),
                        'initial_price': f"{initial_price:.8f}",
                        'pool_address': pool_address,
                        'transaction_hash': tx['hash'],
                        'decimals': token_info.get('decimals', 18),
                        'total_supply': token_info.get('total_supply', 0)
                    })

                except Exception as e:
                    raise e
                    logger.error(f"Error processing transaction {tx.get('hash')}: {e}")
                    continue

            return new_listings

        except Exception as e:
            raise e
            logger.error(f"Error getting new listings: {e}")
            return []

    async def _get_token_usd_price(self, token_address: str, pool_address: str) -> Optional[Decimal]:
        await self.get_configs()
        """Get token price in USD using pool data"""
        try:
            pool = self.w3.eth.contract(
                address=self.w3.to_checksum_address(pool_address),
                abi=self.pool_abi
            )

            # Get tokens
            token0 = await pool.functions.token0().call()
            token1 = await pool.functions.token1().call()

            # Get reserves
            reserves = await pool.functions.getReserves().call()
            reserve0 = Decimal(str(reserves[0]))
            reserve1 = Decimal(str(reserves[1]))

            # Determine which token is WBNB/USDT/BUSD
            token0_decimals = await self._get_token_decimals(token0)
            token1_decimals = await self._get_token_decimals(token1)

            # Adjust reserves by decimals
            reserve0_adjusted = reserve0 / Decimal(str(10 ** token0_decimals))
            reserve1_adjusted = reserve1 / Decimal(str(10 ** token1_decimals))

            if token0.lower() == token_address.lower():
                paired_token = token1
                price_ratio = reserve1_adjusted / reserve0_adjusted
            else:
                paired_token = token0
                price_ratio = reserve0_adjusted / reserve1_adjusted

            # If paired with WBNB, convert to USD
            if paired_token.lower() == self.known_tokens['WBNB'].lower():
                bnb_price = await self.get_bnb_price()
                if not bnb_price:
                    return None
                return price_ratio * Decimal(str(bnb_price))

            # If paired with USDT/BUSD, use direct price
            elif paired_token.lower() in [
                self.known_tokens['USDT'].lower(),
                self.known_tokens['BUSD'].lower()
            ]:
                return price_ratio

            return None

        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return None

    async def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals"""
        try:
            token = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=self.token_abi
            )
            return await token.functions.decimals().call()
        except Exception as e:
            logger.debug(f"Error getting decimals for {token_address}: {e}")
            return 18  # Default to 18 decimals

    @staticmethod
    async def get_bnb_price() -> float:
        bscscan_api = f"https://api-testnet.bscscan.com/api"
        params = {
            "module": "stats",
            "action": "bnbprice",
            "apikey": settings.BSCSCAN_API_KEY
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(bscscan_api, params=params)
            if response.status_code == 200:
                data = response.json()
                return float(data['result']['ethusd'])
            return 0.0

    async def _get_latest_transactions(self) -> List[Dict]:
        await self.get_configs()
        """Get latest router transactions"""
        try:
            async with httpx.AsyncClient(timeout=timeout_settings) as client:
                response = await client.get(
                    self.bsc_config.main_api_url,
                    params={
                        "module": "account",
                        "action": "txlist",
                        "address": self.bsc_config.router_address,
                        "apikey": settings.BSCSCAN_API_KEY,
                        "page": "1",
                        "sort": "desc"
                    }
                )

                data = response.json()
                if data["status"] == "1":
                    return data["result"]
            return []

        except Exception as e:
            raise e
            logger.error(f"Error getting transactions: {e}")
            return []

    @staticmethod
    def _is_liquidity_addition(tx: Dict) -> bool:
        """Check if transaction is liquidity addition"""
        try:
            if tx['isError'] != '0' or tx['txreceipt_status'] != '1':
                return False

            # Check method signature
            method_id = tx['input'][:10]
            return method_id in [
                '0xf305d719',  # addLiquidityETH
                '0xe8e33700'  # addLiquidity
            ]

        except Exception as e:
            logger.error(f"Error checking liquidity addition: {e}")
            return False

    def _parse_liquidity_transaction(self, tx: Dict) -> Optional[Tuple[ChecksumAddress, ChecksumAddress]]:
        """Parse liquidity addition transaction"""
        try:
            input_data = tx['input']
            method_id = input_data[:10]

            if method_id == '0xf305d719':  # addLiquidityETH
                token = AsyncWeb3.to_checksum_address('0x' + input_data[34:74])
                return self.known_tokens['WBNB'], token

            elif method_id == '0xe8e33700':  # addLiquidity
                token_a = AsyncWeb3.to_checksum_address('0x' + input_data[34:74])
                token_b = AsyncWeb3.to_checksum_address('0x' + input_data[98:138])
                return token_a, token_b

            return None

        except Exception as e:
            logger.error(f"Error parsing transaction: {e}")
            return None

    async def _find_new_token(self, token_a: ChecksumAddress, token_b: ChecksumAddress) -> Optional[ChecksumAddress]:
        await self.get_configs()
        """Find new token from pair"""
        try:
            known_addresses = set(self.known_tokens.values())

            if token_a in known_addresses and token_b not in known_addresses:
                return token_b
            elif token_b in known_addresses and token_a not in known_addresses:
                return token_a

            return None

        except Exception as e:
            logger.error(f"Error finding new token: {e}")
            return None

    async def _get_token_info(self, token_address: str) -> Optional[Dict]:
        await self.get_configs()
        """Get detailed token information combining on-chain and API data"""
        for attempt in range(len(self.rpc_nodes)):
            try:
                token = self.w3.eth.contract(
                    address=self.w3.to_checksum_address(token_address),
                    abi=self.token_abi
                )

                # Try to get basic token info
                try:
                    symbol = await token.functions.symbol().call()
                    name = await token.functions.name().call()
                    decimals = await token.functions.decimals().call()
                    total_supply = await token.functions.totalSupply().call()
                except Exception as e:
                    if 'html' in str(e).lower() or 'json' in str(e).lower():
                        # Switch to next RPC node
                        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_nodes)
                        self.w3 = self._initialize_web3()
                        continue
                    raise e

                token_data = {
                    'symbol': symbol,
                    'name': name,
                    'decimals': decimals,
                    'total_supply': total_supply
                }

                # Try to get PancakeSwap data
                try:
                    pancake_data = await self._get_pancakeswap_token_info(token_address)
                    if pancake_data:
                        token_data.update(pancake_data)
                except Exception as e:
                    logger.debug(f"Error getting PancakeSwap data: {e}")

                # Try to get additional data from BSCScan
                try:
                    bscscan_data = await self._get_bscscan_token_info(token_address)
                    if bscscan_data:
                        token_data.update(bscscan_data)
                except Exception as e:
                    logger.debug(f"Error getting BSCScan data: {e}")
                logger.info(f"Token data resolved: \n{json.dumps(token_data, indent=2, cls=DjangoJSONEncoder)}")
                return token_data

            except Exception as e:
                logger.error(f"Error getting token info (attempt {attempt + 1}): {e}")
                if attempt == len(self.rpc_nodes) - 1:
                    # If all RPC nodes failed, try BSCScan API as fallback
                    return await self._get_token_info_from_bscscan(token_address)

                # Switch to next RPC node
                self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_nodes)
                self.w3 = self._initialize_web3()

        return None

    async def _get_token_info_from_bscscan(self, token_address: str) -> Optional[Dict]:
        await self.get_configs()
        """Fallback method to get token info from BSCScan API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.bsc_config.main_api_url,
                    params={
                        "module": "token",
                        "action": "tokeninfo",
                        "contractaddress": token_address,
                        "apikey": settings.BSCSCAN_API_KEY
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "1" and data["result"]:
                        result = data["result"][0]
                        return {
                            'symbol': result.get('symbol'),
                            'name': result.get('name'),
                            'decimals': int(result.get('divisor', 18)),
                            'total_supply': int(result.get('totalSupply', '0')),
                            'holder_count': int(result.get('holdersCount', 0)),
                            'website': result.get('website', ''),
                            'email': result.get('email', ''),
                            'twitter': result.get('twitter', ''),
                            'telegram': result.get('telegram', ''),
                            'verified': bool(int(result.get('verified', 0)))
                        }
            return None

        except Exception as e:
            logger.error(f"Error getting token info from BSCScan: {e}")
            return None

    async def _check_web3_connection(self) -> bool:
        await self.get_configs()
        """Check if current AsyncWeb3 connection is working"""
        try:
            # Try to get latest block number
            self.w3.eth.block_number  # noqa
            return True
        except Exception:
            return False

    async def _ensure_web3_connection(self):
        await self.get_configs()
        """Ensure we have a working AsyncWeb3 connection"""
        if not await self._check_web3_connection():
            for i in range(len(self.rpc_nodes)):
                self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_nodes)
                self.w3 = self._initialize_web3()
                if await self._check_web3_connection():
                    break
            else:
                raise Exception("All RPC nodes are unavailable")

    async def _get_pancakeswap_token_info(self, token_address: str) -> Optional[Dict]:
        """Get token information from PancakeSwap API"""
        try:
            async with httpx.AsyncClient() as client:
                data = self.ps.tokens(token_address).get("data", {})
                if data:
                    return {
                        'price_usd': float(data.get('price', 0)),
                        'price_bnb': float(data.get('price_BNB', 0)),
                        'volume_24h': float(data.get('volume24h', 0)),
                        'liquidity_usd': float(data.get('liquidity', 0))
                    }
            return None

        except Exception as e:
            raise e
            logger.error(f"Error getting PancakeSwap info: {e}")
            return None

    async def _get_bscscan_token_info(self, token_address: str) -> Optional[Dict]:
        await self.get_configs()
        """Get token information from BSCScan API"""
        try:
            # Get token info
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.bsc_config.main_api_url,
                    params={
                        "module": "token",
                        "action": "tokeninfo",
                        "contractaddress": token_address,
                        "apikey": settings.BSCSCAN_API_KEY
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "1" and data["result"]:
                        result = data["result"][0]
                        return {
                            'holder_count': int(result.get('holdersCount', 0)),
                            'transfer_count': int(result.get('transferCount', 0)),
                            'website': result.get('website', ''),
                            'email': result.get('email', ''),
                            'twitter': result.get('twitter', ''),
                            'telegram': result.get('telegram', ''),
                            'verified': bool(int(result.get('verified', 0)))
                        }
            return None

        except Exception as e:
            logger.error(f"Error getting BSCScan info: {e}")
            return None

    async def _get_pool_address(self, token_address: str, tx_hash: str = None) -> Optional[str]:
        await self.get_configs()
        """
        Get pool address from transaction receipt or factory
        Args:
            token_address: Token contract address
            tx_hash: Optional transaction hash to check receipt logs
        Returns:
            Pool address if found, None otherwise
        """
        try:
            if tx_hash:
                # Get transaction receipt
                receipt = await self._get_transaction_receipt(tx_hash)
                if not receipt:
                    return None

                # Extract unique addresses from logs
                addresses = set()
                known_addresses = set([token_address.lower()] +
                                      [addr.lower() for addr in self.known_tokens.values()])
                if isinstance(receipt, dict):
                    for log in receipt['logs']:
                        log_address = log['address'].lower()
                        if log_address not in known_addresses:
                            addresses.add(log_address)

                    # If multiple addresses found, verify they are LP tokens
                    if len(addresses) > 1:
                        for address in addresses:
                            if await self._verify_lp_token(address):
                                return address
                    elif len(addresses) == 1:
                        return addresses.pop()
                else:
                    logger.info(f"receipt: {receipt}")

            # Fallback to factory method if no pool found in receipt
            return await self._get_pool_from_factory(token_address)

        except Exception as e:
            raise e
            logger.error(f"Error getting pool address: {e}")
            return None

    async def _verify_lp_token(self, address: str) -> bool:
        await self.get_configs()
        """
        Verify if address is a Liquidity Pool token
        by checking its symbol
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.bsc_config.main_api_url,
                    params={
                        "module": "account",
                        "action": "tokentx",
                        "contractaddress": address,
                        "apikey": settings.BSCSCAN_API_KEY,
                        "offset": "1",
                        "page": "1",
                        "sort": "asc"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "1" and data["result"]:
                        token = data["result"][0]
                        return token["tokenSymbol"] in ["Cake-LP", "UNI"] and 100 > len(data["result"]) > 0

            return False

        except Exception as e:
            logger.error(f"Error verifying LP token: {e}")
            return False

    async def _get_transaction_receipt(self, tx_hash: str) -> Optional[Dict]:
        await self.get_configs()
        """
        Get transaction receipt with logs from BSC
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.bsc_config.main_api_url,
                    params={
                        "module": "proxy",
                        "action": "eth_getTransactionReceipt",
                        "txhash": tx_hash,
                        "apikey": settings.BSCSCAN_API_KEY,
                        "page": "1",
                        "sort": "asc"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("result"):
                        return data["result"]

            return None

        except Exception as e:
            logger.error(f"Error getting transaction receipt: {e}")
            return None

    async def _get_pool_from_factory(self, token_address: str) -> Optional[str]:
        await self.get_configs()
        """
        Get pool address from PancakeSwap factory
        Fallback method when transaction receipt is not available
        """
        try:
            factory = self.w3.eth.contract(
                address=self.w3.to_checksum_address(self.bsc_config.factory_address),
                abi=self.factory_abi
            )

            # Try with common pairs
            for pair_token in self.known_tokens.values():
                try:
                    pool_address = await factory.functions.getPair(
                        self.w3.to_checksum_address(token_address),
                        self.w3.to_checksum_address(pair_token)
                    ).call()

                    if pool_address != "0x0000000000000000000000000000000000000000":
                        # Verify it's a LP token
                        if await self._verify_lp_token(pool_address):
                            return pool_address
                except Exception:
                    continue

            return None

        except Exception as e:
            logger.error(f"Error getting pool from factory: {e}")
            return None

    async def _is_pancakeswap_pool(self, address: ChecksumAddress) -> bool:
        await self.get_configs()
        """
        Check if address is a PancakeSwap pool by verifying:
        1. Contract has pool interface
        2. Factory address matches PancakeSwap
        """
        try:
            # Pool interface check
            pool_abi = [
                {
                    "constant": True,
                    "inputs": [],
                    "name": "factory",
                    "outputs": [{"name": "", "type": "address"}],
                    "type": "function"
                }
            ]

            pool = self.w3.eth.contract(address=address, abi=pool_abi)

            # Get and verify factory address
            factory = await pool.functions.factory().call()
            pancake_factory = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73".lower()

            return factory.lower() == pancake_factory

        except Exception as e:
            logger.debug(f"Address {address} is not a PancakeSwap pool: {e}")
            return False

    async def _get_pool_liquidity_amount(self, pool_address: ChecksumAddress) -> Decimal:
        await self.get_configs()
        """Get pool liquidity in USD"""
        try:
            # Pool contract ABI
            pool_abi = [
                {
                    "constant": True,
                    "inputs": [],
                    "name": "getReserves",
                    "outputs": [
                        {"name": "_reserve0", "type": "uint112"},
                        {"name": "_reserve1", "type": "uint112"},
                        {"name": "_blockTimestampLast", "type": "uint32"}
                    ],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "token0",
                    "outputs": [{"name": "", "type": "address"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "token1",
                    "outputs": [{"name": "", "type": "address"}],
                    "type": "function"
                }
            ]

            pool = self.w3.eth.contract(address=pool_address, abi=pool_abi)

            # Get tokens
            token0 = await pool.functions.token0().call()
            token1 = await pool.functions.token1().call()

            # Get reserves
            reserves = await pool.functions.getReserves().call()
            reserve0 = Decimal(reserves[0])
            reserve1 = Decimal(reserves[1])

            # Calculate liquidity based on known token
            if token0 in self.known_tokens.values():
                known_token_reserve = reserve0
                known_token = token0
            elif token1 in self.known_tokens.values():
                known_token_reserve = reserve1
                known_token = token1
            else:
                return Decimal('0')

            # Get known token price in USD
            token_price = await self._get_token_usd_price(known_token, pool_address)

            # Calculate total liquidity
            return known_token_reserve * token_price * Decimal('2')

        except Exception as e:
            logger.error(f"Error calculating pool liquidity: {e}")
            return Decimal('0')

    @staticmethod
    def _is_token_safe(security: Dict) -> bool:
        """Check if token is safe to trade"""
        return all([
            not security.get('is_honeypot', True),
            security.get('is_open_source', False),
            not security.get('can_take_back_ownership', True),
            not security.get('owner_change_balance', True),
            not security.get('selfdestruct', True),
            not security.get('trading_cooldown', True),
            not security.get('personal_slippage_modifiable', True),
            not security.get('transfer_pausable', True),
            not security.get('cannot_buy', True),
            not security.get('external_call', True),
            not security.get('slippage_modifiable', True),
            not security.get('is_anti_whale', True),
            not security.get('anti_whale_modifiable', True),
            not security.get('is_whitelisted', True),
            not security.get('is_proxy', True),
            not security.get('cannot_sell_all', True),
            Decimal(security.get('buy_tax', '100')) <= 10,
            Decimal(security.get('sell_tax', '100')) <= 10
        ])

    async def get_token_transfers_count(self, token_address: str) -> int:
        await self.get_configs()
        for attempt in range(len(self.rpc_nodes)):
            try:
                url = self.bsc_config.main_api_url

                params = {
                    "module": "account",
                    "action": "tokentx",
                    "contractaddress": token_address,
                    "startblock": 0,
                    "endblock": "latest",
                    "sort": "asc",
                    "apikey": settings.BSCSCAN_API_KEY
                }

                async with httpx.AsyncClient(timeout=timeout_settings) as client:
                    response = await client.get(url, params=params)

                    if response.status_code == 200:
                        data = response.json()
                        if data["status"] == "1":
                            transaction_count = len(data["result"])
                            return transaction_count
                        elif data["message"] == "No transactions found":
                            return 0
                        else:
                            raise Exception(f"Error: {data['message']}")
                    else:
                        raise Exception(f"HTTP Error: {response.status_code}")
            except Exception as e:
                raise e
                logger.error(f"Error getting token transfers count: {e}")
                return None

    async def analyze_token_contract(self, token_address: str) -> Dict:
        await self.get_configs()
        """Analyze token contract security"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.gopluslabs.io/api/v1/token_security/{self.bsc_config.token_analyze_url_id}",
                    params={
                        "contract_addresses": token_address
                    }
                )

                data = response.json()

            if data["code"] == 1 and token_address.lower() in data["result"]:
                token_data = data["result"][token_address.lower()]
                return {
                    'is_open_source': token_data.get("is_open_source") == "1" if token_data.get(
                        "is_open_source") is not None else None,
                    'is_honeypot': token_data.get("is_honeypot") == "1" if token_data.get(
                        "is_honeypot") is not None else None,
                    'cannot_buy': token_data.get("cannot_buy") == "1" if token_data.get(
                        "cannot_buy") is not None else None,
                    'can_take_back_ownership': token_data.get("can_take_back_ownership") == "1" if token_data.get(
                        "can_take_back_ownership") is not None else None,
                    'owner_change_balance': token_data.get("owner_change_balance") == "1" if token_data.get(
                        "owner_change_balance") is not None else None,
                    'selfdestruct': token_data.get("selfdestruct") == "1" if token_data.get(
                        "selfdestruct") is not None else None,
                    'external_call': token_data.get("external_call") == "1" if token_data.get(
                        "external_call") is not None else None,
                    'trading_cooldown': token_data.get("trading_cooldown") == "1" if token_data.get(
                        "trading_cooldown") is not None else None,
                    'personal_slippage_modifiable': token_data.get(
                        "personal_slippage_modifiable") == "1" if token_data.get(
                        "personal_slippage_modifiable") is not None else None,
                    'slippage_modifiable': token_data.get("slippage_modifiable") == "1" if token_data.get(
                        "slippage_modifiable") is not None else None,
                    'transfer_pausable': token_data.get("transfer_pausable") == "1" if token_data.get(
                        "transfer_pausable") is not None else None,
                    'is_blacklisted': token_data.get("is_blacklisted") == "1" if token_data.get(
                        "is_blacklisted") is not None else None,
                    'is_anti_whale': token_data.get("is_anti_whale") == "1" if token_data.get(
                        "is_anti_whale") is not None else None,
                    'anti_whale_modifiable': token_data.get("anti_whale_modifiable") == "1" if token_data.get(
                        "anti_whale_modifiable") is not None else None,
                    'is_whitelisted': token_data.get("is_whitelisted") == "1" if token_data.get(
                        "is_whitelisted") is not None else None,
                    'is_proxy': token_data.get("is_proxy") == "1" if token_data.get("is_proxy") is not None else None,
                    'cannot_sell_all': token_data.get("cannot_sell_all") == "1" if token_data.get(
                        "cannot_sell_all") is not None else None,
                    'buy_tax': token_data.get("buy_tax", float(0)),
                    'sell_tax': token_data.get("sell_tax", float(0)),
                    'total_supply': token_data.get("total_supply", "0"),
                    'holder_count': token_data.get("holder_count", "0"),
                    'DEX': token_data.get("dex", [{}])[0].get("name"),
                    'liquidity': self._get_pool_liquidity(token_data.get("dex", [{}]))
                }

            return {
                'is_open_source': False,
                'is_honeypot': True,
                'error': 'Unable to analyze contract'
            }

        except Exception as e:
            logger.error(f"Error analyzing contract: {e}")
            return {
                'is_open_source': False,
                'is_honeypot': True,
                'error': str(e)
            }

    @staticmethod
    def _get_pool_liquidity(dex_data: List[Dict]) -> Decimal:
        """Get total liquidity from DEX data"""
        try:
            total_liquidity = Decimal('0')

            for dex in dex_data:
                if dex.get('name') == 'PancakeV2':
                    total_liquidity += Decimal(dex.get('liquidity', '0'))

            return total_liquidity

        except Exception as e:
            logger.error(f"Error calculating liquidity: {e}")
            return Decimal('0')

    async def get_holder_count(self, token_address: str) -> int:
        await self.get_configs()
        """Get number of token holders"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.bsc_config.main_api_url,
                    params={
                        "module": "token",
                        "action": "tokenholderlist",
                        "contractaddress": token_address,
                        "apikey": settings.BSCSCAN_API_KEY,
                        "page": "1",
                        "offset": "1"
                    }
                )

                data = response.json()
            if data["status"] == "1":
                return int(data.get("result", [{"count": "0"}])[0]["count"])
            return 0

        except Exception as e:
            logger.error(f"Error getting holder count: {e}")
            return 0

    async def get_pool_liquidity(self, pool_address: str) -> Decimal:
        await self.get_configs()
        """
        Get pool liquidity in USD
        """
        try:
            # Convert address
            pool_checksum = AsyncWeb3.to_checksum_address(pool_address)

            # Get pool info
            pool_info = await self._get_pool_info(pool_checksum)
            if not pool_info:
                return Decimal('0')

            # Calculate total liquidity
            token0_liquidity = pool_info['reserve0'] * pool_info['token0_price']
            token1_liquidity = pool_info['reserve1'] * pool_info['token1_price']

            return token0_liquidity + token1_liquidity

        except Exception as e:
            logger.error(f"Error getting pool liquidity: {e}")
            return Decimal('0')

    async def _get_pool_info(self, pool_address: ChecksumAddress) -> Optional[Dict]:
        await self.get_configs()
        """
        Get detailed pool information
        """
        try:
            # Pool contract
            pool = self.w3.eth.contract(
                address=pool_address,
                abi=[
                    {
                        "constant": True,
                        "inputs": [],
                        "name": "getReserves",
                        "outputs": [
                            {"name": "_reserve0", "type": "uint112"},
                            {"name": "_reserve1", "type": "uint112"},
                            {"name": "_blockTimestampLast", "type": "uint32"}
                        ],
                        "type": "function"
                    },
                    {
                        "constant": True,
                        "inputs": [],
                        "name": "token0",
                        "outputs": [{"name": "", "type": "address"}],
                        "type": "function"
                    },
                    {
                        "constant": True,
                        "inputs": [],
                        "name": "token1",
                        "outputs": [{"name": "", "type": "address"}],
                        "type": "function"
                    }
                ]
            )

            # Get tokens
            token0 = await pool.functions.token0().call()
            token1 = await pool.functions.token1().call()

            # Get decimals
            token0_decimals = await self._get_token_decimals(token0)
            token1_decimals = await self._get_token_decimals(token1)

            # Get reserves
            reserves = await pool.functions.getReserves().call()
            reserve0 = Decimal(str(reserves[0])) / Decimal(str(10 ** token0_decimals))
            reserve1 = Decimal(str(reserves[1])) / Decimal(str(10 ** token1_decimals))

            # Get prices in USD
            token0_price = await self._get_token_usd_price(token0, pool_address)
            token1_price = await self._get_token_usd_price(token1, pool_address)

            return {
                'token0': token0,
                'token1': token1,
                'reserve0': reserve0,
                'reserve1': reserve1,
                'token0_price': token0_price,
                'token1_price': token1_price,
                'token0_decimals': token0_decimals,
                'token1_decimals': token1_decimals
            }

        except Exception as e:
            raise e
            logger.error(f"Error getting pool info: {e}")
            return None

    async def get_abi(self, contract_address):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.bsc_config.main_api_url}",
                    params={
                        "module": "contract",
                        "action": "getabi",
                        "address": contract_address,
                        "apikey": settings.BSCSCAN_API_KEY
                    }
                )
                data = response.json()
                if data["status"] == "1":
                    result = json.loads(data["result"])
                else:
                    result = []
                logger.info(f"Got ABI: {result}")
                return result

        except Exception as e:
            raise e
            logger.error(f"Error loading router ABI: {e}")
            return []

    async def get_past_liquidity_events(
            self,
            from_block: int,
            to_block: Union[int, str] = 'latest',
            limit: int = 1000
    ) -> List[Dict]:
        await self.get_configs()
        """Get past liquidity addition events"""
        try:
            # Get transaction list
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.bsc_config.main_api_url,
                    params={
                        "module": "account",
                        "action": "txlist",
                        "address": self.bsc_config.router_address,
                        "startblock": from_block,
                        "endblock": to_block,
                        "page": "1",
                        "offset": str(limit),
                        "sort": "desc",
                        "apikey": settings.BSCSCAN_API_KEY
                    }
                )

                if response.status_code != 200:
                    return []

                data = response.json()
            if data["status"] != "1":
                return []

            liquidity_events = []
            for tx in data["result"]:
                try:
                    if not self._is_liquidity_addition(tx):
                        continue

                    # Get receipt to find pool
                    receipt = await self._get_transaction_receipt(tx['hash'])
                    if not receipt:
                        continue

                    # Parse token pair
                    token_pair = self._parse_liquidity_transaction(tx)
                    if not token_pair:
                        continue

                    token_a, token_b = token_pair

                    # Find new token
                    new_token = await self._find_new_token(token_a, token_b)
                    if not new_token:
                        continue

                    # Find pool address from receipt logs
                    pool_address = self._find_pool_from_receipt(receipt, [token_a, token_b])
                    if not pool_address:
                        continue

                    # Verify it's a LP token
                    if not await self._verify_lp_token(pool_address):
                        continue

                    # Get token data with found pool
                    token_data = await self._get_token_data(new_token, pool_address, tx)
                    if not token_data:
                        continue

                    liquidity_events.append(token_data)

                except Exception as e:
                    logger.debug(f"Error processing tx {tx.get('hash')}: {e}")
                    continue

            return liquidity_events

        except Exception as e:
            logger.error(f"Error getting past liquidity events: {e}")
            return []

    @staticmethod
    def _find_pool_from_receipt(receipt: Dict, token_addresses: List[str]) -> Optional[str]:
        """
        Find pool address from transaction receipt logs
        Args:
            receipt: Transaction receipt
            token_addresses: List of token addresses involved
        Returns:
            Pool address if found, None otherwise
        """
        try:
            # Convert addresses to lowercase for comparison
            known_addresses = set(addr.lower() for addr in token_addresses)

            # Find unique addresses from logs
            for log in receipt['logs']:
                log_address = log['address'].lower()

                # Skip if it's one of the tokens
                if log_address in known_addresses:
                    continue

                # Return first address that's not a token
                # It should be the pool address
                return log_address

            return None

        except Exception as e:
            logger.error(f"Error finding pool from receipt: {e}")
            return None

    async def _get_token_data(
            self,
            token_address: str,
            pool_address: str,
            tx: Dict
    ) -> Optional[Dict]:
        await self.get_configs()
        """
        Get comprehensive token data at listing time
        Args:
            token_address: Token contract address
            pool_address: Liquidity pool address
            tx: Transaction data
        """
        paired_token = None
        try:
            # Get basic token info
            token_info = await self._get_token_info(token_address)
            if not token_info:
                return None

            # Get initial price from pool
            price = await self._get_token_usd_price(token_address, pool_address)
            if not price:
                return None

            # Get pool info
            try:
                pool = self.w3.eth.contract(
                    address=self.w3.to_checksum_address(pool_address),
                    abi=self.pool_abi
                )

                # Get tokens in pool
                token0 = await pool.functions.token0().call()
                token1 = await pool.functions.token1().call()

                # Get reserves
                reserves = await pool.functions.getReserves().call()

                # Calculate liquidity
                paired_token = token1 if token_address.lower() == token0.lower() else token0
                paired_decimals = await self._get_token_decimals(paired_token)

                if paired_token.lower() == self.known_tokens['WBNB'].lower():
                    bnb_price = await self.get_bnb_price()
                    if bnb_price:
                        liquidity = (Decimal(str(reserves[1])) / Decimal(str(10 ** paired_decimals))) * Decimal(
                            str(bnb_price)) * 2
                    else:
                        liquidity = Decimal('0')
                elif paired_token.lower() in [self.known_tokens['USDT'].lower(), self.known_tokens['BUSD'].lower()]:
                    liquidity = (Decimal(str(reserves[1])) / Decimal(str(10 ** paired_decimals))) * 2
                else:
                    liquidity = Decimal('0')

            except Exception as e:
                logger.debug(f"Error getting pool info: {e}")
                liquidity = Decimal('0')

            # Get security analysis
            security = await self.analyze_token_contract(token_address)

            return {
                'token_address': token_address,
                'pool_address': pool_address,
                'transaction_hash': tx['hash'],
                'block_number': int(tx['blockNumber']),
                'timestamp': int(tx['timeStamp']),
                'token_info': {
                    'symbol': token_info['symbol'],
                    'name': token_info.get('name', token_info['symbol']),
                    'decimals': token_info['decimals'],
                    'total_supply': token_info['total_supply']
                },
                'initial_price': float(price),
                'initial_liquidity': float(liquidity),
                'security': security,
                'paired_token': paired_token
            }

        except Exception as e:
            logger.error(f"Error getting token data: {e}")
            return None
