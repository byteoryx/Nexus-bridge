from __future__ import annotations
from typing import TYPE_CHECKING, Literal

from web3 import Web3
from eth_typing import ChecksumAddress
from web3.contract import AsyncContract
from web3.types import Nonce

from core.logger import get_logger
from .data.models import RawContract
from ..omnichain_models import TokenAmount
from .data import types
from libs.blockchains.eth_async.network_client_aware import NetworkClientAware

if TYPE_CHECKING:
    from .ethclient import NetworkClient


class Wallet(NetworkClientAware):
    def __init__(self, client: NetworkClient, log_context) -> None:
        super().__init__(client, log_context)
        if log_context:
            self.logger = get_logger(class_name=f"EthClient: {client.network.name}", **log_context)
        else:
            self.logger = get_logger(class_name=f"EthClient: {client.network.name}")

    @NetworkClientAware.retry
    async def balance(
            self,
            token: types.Contract | None = None,
            address: str | ChecksumAddress | None = None,
    ) -> TokenAmount:
        if not address:
            address = self.client.w3_account.address

        address = Web3.to_checksum_address(address)
        if not token:
            return TokenAmount(
            amount=await self.client.w3.eth.get_balance(account=address),
            decimals=self.client.network.decimals,
            wei=True
            )


        token_address = token
        if isinstance(token, (RawContract, AsyncContract)):
            token_address = token.address

        contract = await self.client.contracts.default_token(
            contract_address=Web3.to_checksum_address(token_address)
        )

        return TokenAmount(
            amount=await contract.functions.balanceOf(address).call(),
            decimals=await self.client.transactions.get_decimals(contract=contract.address),
            wei=True
            )

    async def get_token_symbol(self, token_address: str | ChecksumAddress) -> str:
        token_address = Web3.to_checksum_address(token_address)
        contract = await self.client.contracts.default_token(
            contract_address=Web3.to_checksum_address(token_address)
        )
        return await contract.functions.symbol().call()

    @NetworkClientAware.retry
    async def nonce(self, address: ChecksumAddress | None = None,
                block_identifier: Literal["latest", "earliest", "pending", "safe", "finalized"] = "latest") -> Nonce:
        if not address:
            address = self.client.w3_account.address
        return await self.client.w3.eth.get_transaction_count(address, block_identifier)
