from web3 import Web3
from web3.types import TxParams

from core.evm_contracts import EVMContracts
from core.logger import get_logger
from libs.blockchains.eth_async.base_evm_task_class import BaseEVMTaskClass
from libs.blockchains.eth_async.data.models import TxArgs, Network
from libs.blockchains.omnichain_models import TokenAmount
from tasks.controller import Controller


class NexusBridge(BaseEVMTaskClass["NexusBridge"]):
    CONTRACTS = {
        'arbitrum_to_optimism': EVMContracts.ArbitrumOpenUSDT,
        'arbitrum_to_base': EVMContracts.ArbitrumOpenUSDT,
        'optimism_to_base': EVMContracts.OptimismOpenUSDT,
        'optimism_to_arbitrum': EVMContracts.OptimismOpenUSDT,
        'base_to_arbitrum': EVMContracts.BaseOpenUSDT,
        'base_to_optimism': EVMContracts.BaseOpenUSDTtoOptimism
    }

    def __init__(self, controller: Controller, log_context):
        self.controller = controller
        self.requests = self.controller.requests_client
        self.eth_client = self.controller.eth_client
        self._logger = get_logger(class_name=self.__class__.__name__, **log_context)
        self._current_network = None
        super().__init__(self)


    async def bridge_usdc(self, amount_in: TokenAmount,
                          destination_chain: Network,
                          usdc_contract,
                          approve_amount = "infinity"):
        # 13. quoteGasPayment (0xf2ed8c53) read method
        async_contract = await self._get_async_contract(destination_chain)
        gas_payment = await self.read_contract(async_contract,  "quoteGasPayment", destination_chain.chain_id)
        gas_payment = TokenAmount(gas_payment, 18, True)
        self._logger.info(f"Payment in ETH for bridge: {gas_payment.Ether} ETH")

        # 20. transferRemote (0x81b4e8b4)
        bytes32_address = Web3.to_bytes(hexstr=self.eth_client.w3_account.address).rjust(32, b'\0')
        args = TxArgs(
            _destination=destination_chain.chain_id,
            _recipient=bytes32_address,
            _amountOrId=int(amount_in.Wei),
        )

        tx_params = TxParams(
            to=async_contract.address,
            data=async_contract.encode_abi('transferRemote', args=args.tuple()),
            value=self.network_client.w3.to_wei(gas_payment.Wei, 'wei'),
        )

        if isinstance(approve_amount, str) and approve_amount == "infinity":
            approve_amount = None
            approve_inf = True
        else:
            approve_inf = False

        await self.network_client.transactions.approve_interface(token=usdc_contract.address,
                                                               spender=async_contract.address,
                                                               amount_in_tx=amount_in,
                                                               amount_to_approve=approve_amount,
                                                               approve_inf=approve_inf)

        tx_hash = await self.network_client.transactions.send_tx(tx_params)
        return True
