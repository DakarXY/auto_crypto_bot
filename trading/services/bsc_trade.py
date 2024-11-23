import json

from web3 import AsyncWeb3
from eth_account import Account
from bscscan import BscScan
from decimal import Decimal
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
import logging
from typing import List, Dict, Any
import time
from .transaction_analyzer import TransactionAnalyzer

import httpx

from ..models.config import AutoTradingConfig
from ..models.provider_configs import BSCConfig


logger = logging.getLogger('trading')


class BSCTradingService:
    config: AutoTradingConfig
    bsc_config: BSCConfig
    rpc_nodes: Any
    router_contract: Any
    router_abi: Any
    w3: AsyncWeb3
    token_contract: Any
    account: Account
    known_tokens: Any

    def __init__(self, token_address: str):
        self.analyzer = TransactionAnalyzer()
        self.token_address = token_address
        self.current_rpc_index = 0
        self.bsc = BscScan(settings.BSCSCAN_API_KEY)
        self.token_abi = self._load_token_abi()
        self.factory_abi = [
            {
                "constant": True,
                "inputs": [
                    {"name": "tokenA", "type": "address"},
                    {"name": "tokenB", "type": "address"}
                ],
                "name": "getPair",
                "outputs": [{"name": "pair", "type": "address"}],
                "type": "function"
            }
        ]

        # Pair ABI - getReserves function
        self.pair_abi = [
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

        # Router ABI
        self.router_abi = [
            {
                "inputs": [
                    {"name": "amountOutMin", "type": "uint256"},
                    {"name": "path", "type": "address[]"},
                    {"name": "to", "type": "address"},
                    {"name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactETHForTokens",
                "outputs": [{"name": "amounts", "type": "uint256[]"}],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [
                    {
                        "internalType": "uint256",
                        "name": "amountIn",
                        "type": "uint256"
                    },
                    {
                        "internalType": "uint256",
                        "name": "amountOutMin",
                        "type": "uint256"
                    },
                    {
                        "internalType": "address[]",
                        "name": "path",
                        "type": "address[]"
                    },
                    {
                        "internalType": "address",
                        "name": "to",
                        "type": "address"
                    },
                    {
                        "internalType": "uint256",
                        "name": "deadline",
                        "type": "uint256"
                    }
                ],
                "name": "swapExactTokensForETH",
                "outputs": [
                    {
                        "internalType": "uint256[]",
                        "name": "amounts",
                        "type": "uint256[]"
                    }
                ],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]

    async def get_configs(self):
        self.config = await AutoTradingConfig.get_config()
        self.bsc_config = await BSCConfig.get_config()
        self.rpc_nodes = self.bsc_config.rpc_nodes.split(" ")
        self.known_tokens = self._load_known_tokens()
        self.w3 = self._initialize_web3()
        self.router_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.bsc_config.router_address),
            abi=self.router_abi
        )
        # Contract instances
        self.token_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.token_address),
            abi=self.token_abi
        )


    def _load_known_tokens(self):
        known_tokens_string_tuples = self.bsc_config.known_tokens.split(" ")
        known_tokens_tuples = [(token.split(",")[0], token.split(",")[1]) for token in known_tokens_string_tuples]
        return {
            name: AsyncWeb3.to_checksum_address(addr) for name, addr in known_tokens_tuples
        }

    async def load_abi(self, address: str) -> List:
        """Load PancakeSwap Router ABI"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.bsc_config.main_api_url}",
                    params={
                        "module": "contract",
                        "action": "getabi",
                        "address": address,
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
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]

    def _initialize_web3(self) -> AsyncWeb3:
        """Initialize AsyncWeb3 with current RPC node"""
        return AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.rpc_nodes[self.current_rpc_index]))

    async def get_token_price(self) -> Decimal:
        path = [
            self.w3.to_checksum_address(self.token_address),
            self.w3.to_checksum_address(self.bsc_config.wallet.address)
        ]
        amount_in = self.w3.to_wei('1', 'ether')

        # Get amounts out from PancakeSwap
        amounts = await self.router_contract.functions.getAmountsOut(
            amount_in,
            path
        ).call()

        return Decimal(amounts[1]) / Decimal('1e18')

    async def get_pair_info(self, token_sell: str, token_get: str) -> tuple[str, Dict]:
        """Get pair address and reserves for any token pair"""
        token_sell = self.w3.to_checksum_address(token_sell)
        token_get = self.w3.to_checksum_address(token_get)

        factory = self.w3.eth.contract(self.bsc_config.factory_address, abi=self.factory_abi)
        # Get pair address
        pair_address = await factory.functions.getPair(token_sell, token_get).call()

        if pair_address == "0x0000000000000000000000000000000000000000":
            raise Exception(f"No liquidity pair exists for {token_sell} - {token_get}")

        # Get pair contract
        pair_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(pair_address),
            abi=self.pair_abi
        )

        # Get tokens order
        token0 = await pair_contract.functions.token0().call()

        # Get reserves
        reserves = await pair_contract.functions.getReserves().call()

        # Create reserves dict based on token order
        if self.w3.to_checksum_address(token_sell) == self.w3.to_checksum_address(token0):
            reserve_data = {
                'sell_reserve': reserves[0],
                'get_reserve': reserves[1],
                'sell_token_is_token0': True
            }
        else:
            reserve_data = {
                'sell_reserve': reserves[1],
                'get_reserve': reserves[0],
                'sell_token_is_token0': False
            }

        return pair_address, reserve_data

    async def get_token_info(self, token_address: str, wallet_address: str = None) -> Dict:
        """Get token decimals and balance"""
        token_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token_address),
            abi=self.token_abi
        )

        decimals = await token_contract.functions.decimals().call()
        balance = 0
        if wallet_address:
            balance = await token_contract.functions.balanceOf(
                self.w3.to_checksum_address(wallet_address)
            ).call()

        result = {
            "decimals": decimals,
            "balance": balance,
            "balance_formatted": balance / (10 ** decimals)
        }
        logger.info(f"Token info for trade operation got: {token_address} {wallet_address} {result}")
        return result

    async def calculate_tokens_out(self, token_sell: str, token_get: str, amount_sell: int,
                                   wallet_address: str = None) -> Dict:
        """
        Calculate expected output tokens when selling any token

        Args:
            token_sell: Address of token to sell
            token_get: Address of token to receive
            amount_sell: Amount of tokens to sell
            wallet_address: Optional wallet address to check balances
        """
        try:
            # Get token info
            sell_token_info = await self.get_token_info(token_sell, wallet_address)
            get_token_info = await self.get_token_info(token_get)

            # Check balance if wallet provided
            # if wallet_address and amount_sell > await self.get_token_balance(token_sell):
                # raise Exception(
                    # f"Insufficient balance. Have: {sell_token_info['balance_formatted']}, Need: {amount_sell}")

            # Get pair info
            pair_address, reserves = await self.get_pair_info(token_sell, token_get)

            # Calculate current price before swap
            current_price = reserves['get_reserve'] / reserves['sell_reserve']
            current_price_formatted = current_price * (10 ** sell_token_info['decimals']) / (
                        10 ** get_token_info['decimals'])

            # Calculate output using x*y=k formula
            # amount_out = (reserve_out * amount_in * 998) / (reserve_in * 1000 + amount_in * 998)
            amount_in_with_fee = amount_sell * 998  # 0.2% fee
            numerator = amount_in_with_fee * reserves['get_reserve']
            denominator = (reserves['sell_reserve'] * 1000) + amount_in_with_fee
            tokens_out = numerator // denominator

            # Calculate execution price
            execution_price = amount_sell / tokens_out
            execution_price_formatted = execution_price * (10 ** get_token_info['decimals']) / (
                        10 ** sell_token_info['decimals'])

            # Calculate price impact
            price_impact = (amount_sell / (reserves['sell_reserve'] + amount_sell)) * 100

            # Calculate slippage from current price
            slippage = ((execution_price_formatted - current_price_formatted) / current_price_formatted) * 100

            return {
                'pair_address': pair_address,
                'tokens_out': tokens_out,
                'tokens_out_formatted': tokens_out / (10 ** get_token_info['decimals']),
                'price_impact': price_impact,
                'reserves': {
                    'sell_token': reserves['sell_reserve'] / (10 ** sell_token_info['decimals']),
                    'get_token': reserves['get_reserve'] / (10 ** get_token_info['decimals'])
                },
                'sell_token_info': sell_token_info,
                'get_token_info': get_token_info,
                'prices': {
                    'current_price': current_price_formatted,  # Текущая цена до свопа
                    'execution_price': execution_price_formatted,  # Цена исполнения с учетом объема
                    'slippage_percent': slippage,  # Проскальзывание в процентах
                    'raw': {
                        'current_price_wei': current_price,
                        'execution_price_wei': execution_price
                    }
                }
            }

        except Exception as e:
            raise e
            raise Exception(f"Failed to calculate tokens out: {str(e)}")

    async def buy(self, amount: Decimal) -> Dict[str, Any]:
        await self.get_configs()
        """
        Buy tokens using PancakeSwap through BSC

        Args:
            amount: Amount of wallet currency to spend

        Returns:
            dict: Transaction details
        """

        path = [self.w3.to_checksum_address(self.bsc_config.wallet.currency_to_spend_address),
                self.w3.to_checksum_address(self.token_address)]
        deadline = int(time.time()) + 300  # 5 minutes
        wallet_address = self.w3.to_checksum_address(self.bsc_config.wallet.address)
        nonce = await self.w3.eth.get_transaction_count(wallet_address)
        amount_in_wei = self.w3.to_wei(amount, "ether")
        expected_out = await self.calculate_tokens_out(
            self.bsc_config.wallet.currency_to_spend_address,
            self.token_address,
            amount_in_wei,
            self.bsc_config.wallet.address
        )
        min_tokens = int(expected_out.get("tokens_out") * 0.95)

        tx = await self.router_contract.functions.swapExactETHForTokens(
            min_tokens,
            path,
            wallet_address,
            deadline
        ).build_transaction({
            'chainId': int(self.bsc_config.token_analyze_url_id),
            'from': wallet_address,
            'value': amount_in_wei,
            'gas': 250000,
            'gasPrice': await self.w3.eth.gas_price,
            'nonce': nonce
        })

        # Sign and send transaction
        signed_tx = self.w3.eth.account.sign_transaction(tx, self.bsc_config.wallet.private_key)
        swap_tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        receipt = await self.w3.eth.wait_for_transaction_receipt(swap_tx_hash)

        return  {
            'transaction_hash': swap_tx_hash.hex(),
            'status': receipt['status'],
            'gas_used': receipt['gasUsed'],
            'amount_in': str(amount),
            'min_tokens_out': min_tokens,
            'expected_out': self.w3.from_wei(expected_out.get("tokens_out"), "ether"),
            "init_price": expected_out.get("prices", {}).get("execution_price", "0.0")
        }

    async def sell(self, amount: Decimal | None = None) -> Dict[str, Any]:
        await self.get_configs()
        """
        Sell tokens using PancakeSwap through BSC

        Args:
            amount: Amount of tokens to sell

        Returns:
            dict: Transaction details
        """
        analyzer = TransactionAnalyzer()
        path = [self.w3.to_checksum_address(self.token_address),
                self.w3.to_checksum_address(self.bsc_config.wallet.currency_to_spend_address)]
        deadline = int(time.time()) + 300  # 5 minutes
        wallet_address = self.w3.to_checksum_address(self.bsc_config.wallet.address)
        nonce = await self.w3.eth.get_transaction_count(wallet_address)
        if not amount:
            amount_in = await self.get_token_balance(self.token_address)
        else:
            amount_in = int(self.w3.to_wei(amount, "ether"))
        expected_out = await self.calculate_tokens_out(
            self.token_address,
            self.bsc_config.wallet.currency_to_spend_address,
            amount_in,
            self.bsc_config.wallet.address
        )
        min_tokens = int(expected_out.get("tokens_out") * 0.95)  # 5% slippage

        # Approve token spending
        approve_txn = await self.token_contract.functions.approve(
            self.w3.to_checksum_address(self.bsc_config.router_address),
            self.w3.to_wei(str(amount), 'ether')
        ).build_transaction({
            'from': self.w3.to_checksum_address(self.bsc_config.wallet.address),
            'nonce': nonce,
            'gas': 250000,
            'gasPrice': await self.w3.eth.gas_price
        })

        # Sign and send approval
        signed_approve = self.w3.eth.account.sign_transaction(
            approve_txn,
            self.bsc_config.wallet.private_key
        )
        approve_tx_hash = await self.w3.eth.send_raw_transaction(
            signed_approve.raw_transaction
        )
        approve_tx_receipt = await self.w3.eth.wait_for_transaction_receipt(approve_tx_hash)
        approve_tx_analysis = await analyzer.analyze_failed_transaction(approve_tx_hash, approve_tx_receipt)
        logger.info(f"Analyze approve receipt: \n{approve_tx_analysis}")

        tx = await self.router_contract.functions.swapExactTokensForETH(
            amount_in,
            min_tokens,
            path,
            wallet_address,
            deadline
        ).build_transaction({
            'chainId': int(self.bsc_config.token_analyze_url_id),
            'from': wallet_address,
            'gas': 250000,
            'gasPrice': await self.w3.eth.gas_price,
            'nonce': nonce+1
        })

        signed_tx = self.w3.eth.account.sign_transaction(tx, self.bsc_config.wallet.private_key)
        swap_tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(swap_tx_hash)
        tx_analysis = await analyzer.analyze_failed_transaction(swap_tx_hash, receipt)
        logger.info(f"Analyze receipt: \n{tx_analysis}")
        return {
            'transaction_hash': swap_tx_hash.hex(),
            'status': receipt['status'],
            'gas_used': receipt['gasUsed'],
            'amount_in': str(amount),
            'min_tokens_out': min_tokens,
            'expected_out': self.w3.from_wei(expected_out.get("tokens_out"), "ether"),
            'sell_price': expected_out.get("prices", {}).get("execution_price", "0.0")
        }

    async def get_token_balance(self, token_address: str) -> int:
        token_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token_address),
            abi=self.token_abi
        )
        balance = await token_contract.functions.balanceOf(
            self.w3.to_checksum_address(self.bsc_config.wallet.address)
        ).call()
        logger.info(f"balance: {balance} {type(balance)}")
        return balance
