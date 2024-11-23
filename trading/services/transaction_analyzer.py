from web3 import AsyncWeb3
from eth_account import Account
from bscscan import BscScan
from django.conf import settings
from ..models.provider_configs import BSCConfig
from typing import Dict, Optional, Any
import time
from web3.types import TxReceipt
from web3.middleware import ExtraDataToPOAMiddleware

class TransactionAnalyzer:
    bsc_config: BSCConfig
    rpc_nodes: Any
    router_contract: Any
    router_abi: Any
    w3: AsyncWeb3
    token_contract: Any
    account: Account

    def __init__(self):
        self.current_rpc_index = 0
        self.bsc = BscScan(settings.BSCSCAN_API_KEY)
        self.error_sigs = {
            "0x949d225d": "Insufficient input amount",
            "0x82575394": "Insufficient output amount",
            "0xe8e33700": "Insufficient liquidity",
            "0xfed1fb93": "Execution reverted: Transfer failed",
            "0x0965df6e": "Expired deadline",
            "0x0d5fa5e5": "Price impact too high",
        }

    async def get_configs(self):
        self.bsc_config = await BSCConfig.get_config()
        self.rpc_nodes = self.bsc_config.rpc_nodes.split(" ")
        self.w3 = self._initialize_web3()
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.account = Account.from_key(self.bsc_config.wallet.private_key)

    async def analyze_failed_transaction(self, tx_hash, tx_receipt: TxReceipt) -> Dict:
        await self.get_configs()
        """
        Analyze a failed transaction and return detailed information
        """
        try:
            tx = await self.w3.eth.get_transaction(tx_hash)
            # Get transaction and receipt
            # Basic transaction info
            analysis = {
                "status": tx_receipt["status"],
                "gas_used": tx_receipt["gasUsed"],
                "gas_limit": tx["gas"],
                "gas_price": tx["gasPrice"],
                "value": tx["value"],
                "from": tx["from"],
                "to": tx["to"],
                "block_number": tx_receipt["blockNumber"]
            }

            # If transaction failed
            if tx_receipt["status"] == 0:
                # Try to get revert reason
                try:
                    # Simulate the transaction to get error
                    await self.w3.eth.call(
                        {
                            "from": tx["from"],
                            "to": tx["to"],
                            "data": tx["input"],
                            "value": tx["value"],
                            "gas": tx["gas"],
                            "gasPrice": tx["gasPrice"],
                        },
                        tx_receipt["blockNumber"] - 1
                    )
                except Exception as e:
                    error_msg = str(e)
                    analysis["revert_reason"] = self._parse_error_message(error_msg)

                # Check for common errors in transaction input
                analysis["common_errors"] = self._check_common_issues(tx, tx_receipt)

                # Gas analysis
                analysis["gas_analysis"] = await self._analyze_gas(tx, tx_receipt)

                # Balance checks
                analysis["balance_issues"] = await self._check_balances(tx)

        except Exception as e:
            raise e
            return {"error": f"Analysis failed: {str(e)}"}

        return analysis

    def _initialize_web3(self) -> AsyncWeb3:
        """Initialize AsyncWeb3 with current RPC node"""
        return AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.rpc_nodes[self.current_rpc_index]))

    def _parse_error_message(self, error_msg: str) -> str:
        """Parse error message from revert"""
        # Check for known error signatures
        for sig, message in self.error_sigs.items():
            if sig in error_msg:
                return message

        # Look for revert strings
        if "revert" in error_msg.lower():
            # Extract message between single quotes if present
            import re
            revert_msg = re.search(r"'(.*?)'", error_msg)
            if revert_msg:
                return revert_msg.group(1)

        return error_msg

    def _check_common_issues(self, tx: Dict, receipt: Dict) -> Dict:
        """Check for common transaction issues"""
        issues = {}

        # Check if gas limit was too low
        if receipt["gasUsed"] >= tx["gas"]:
            issues["gas"] = "Gas limit too low"

        # Check if value is 0 for payable function
        if tx["value"] == 0 and self._is_payable_function(tx["input"]):
            issues["value"] = "No ETH/BNB sent for payable function"

        # Check deadline for swap functions
        if self._is_swap_function(tx["input"]):
            deadline = self._extract_deadline(tx["input"])
            if deadline and deadline < time.time():
                issues["deadline"] = "Transaction deadline expired"

        return issues

    async def _analyze_gas(self, tx: Dict, receipt: Dict) -> Dict:
        """Analyze gas usage and prices"""
        return {
            "gas_used_percentage": (receipt["gasUsed"] / tx["gas"]) * 100,
            "gas_price_gwei": self.w3.from_wei(tx["gasPrice"], 'gwei'),
            "total_cost_eth": self.w3.from_wei(receipt["gasUsed"] * tx["gasPrice"], 'ether'),
            "is_gas_too_low": await self._is_gas_price_too_low(tx["gasPrice"])
        }

    async def _check_balances(self, tx: Dict) -> Dict:
        """Check relevant balances at transaction block"""
        issues = {}

        # Check ETH/BNB balance
        balance = await self.w3.eth.get_balance(tx["from"])
        total_needed = tx["value"] + (tx["gas"] * tx["gasPrice"])
        issues["info"] = {"balance": balance}
        if balance < total_needed:
            issues["balance"] = "Insufficient ETH/BNB for transaction"

        return issues

    async def _is_gas_price_too_low(self, gas_price: int) -> bool:
        """Check if gas price is too low compared to network"""
        block = await self.w3.eth.get_block('latest')
        base_fee = block['baseFeePerGas']
        return gas_price < base_fee

    def _is_payable_function(self, input_data: str) -> bool:
        """Check if function is payable based on input data"""
        # Check common payable function signatures
        payable_sigs = [
            "0x7ff36ab5".encode(),  # swapExactETHForTokens
            "0xfb3bdb41".encode(),  # swapETHForExactTokens
        ]
        return any((sig in input_data for sig in payable_sigs))

    def _is_swap_function(self, input_data: str) -> bool:
        """Check if function is a swap function"""
        swap_sigs = [
            "0x7ff36ab5".encode(),  # swapExactETHForTokens
            "0x38ed1739".encode(),  # swapExactTokensForTokens
            "0x18cbafe5".encode(),  # swapExactTokensForETH
        ]
        return any((sig in input_data for sig in swap_sigs))

    def _extract_deadline(self, input_data: str) -> Optional[int]:
        """Extract deadline from swap function input"""
        try:
            # Deadline is typically the last parameter
            # This is a simplified extraction, might need adjustment
            deadline_hex = input_data[-64:]
            return int(deadline_hex, 16)
        except:
            return None
