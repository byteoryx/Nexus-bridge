from __future__ import annotations

from core.settings_models import NetworkConfig
from libs.blockchains.eth_async.data.models import CommonValues


def get_next_rpc_from_network_config(network_config: NetworkConfig, logger, change: bool = False):
    if not network_config.rpcs:
        logger.error(f"Error: No RPC endpoints configured for network {network_config.name}")
        raise ValueError(f"No RPC endpoints configured for network {network_config.name}")

    if len(network_config.rpcs) == 1 and change:
        logger.warning(f"Warning: {network_config.name} has only one RPC: {network_config.rpcs[network_config.current_rpc_index]}")
    else:
        network_config.current_rpc_index = (network_config.current_rpc_index + 1) % len(network_config.rpcs)
    return network_config.rpcs[network_config.current_rpc_index]

def resolve_token_addresses(class_obj, token_from, token_to):
    if token_from == "native" or token_from == "ETH":
        token_from = CommonValues.ZeroAddress

    if token_to == "native" or token_to == "ETH":
        token_to = CommonValues.ZeroAddress

    if token_from == CommonValues.ZeroAddress:
        from_currency = class_obj.network_client.network.coin_symbol
    else:
        from_currency = token_from

    if token_to == CommonValues.ZeroAddress:
        to_currency = class_obj.network_client.network.coin_symbol
    else:
        to_currency = token_to

    return token_from, token_to, from_currency, to_currency
