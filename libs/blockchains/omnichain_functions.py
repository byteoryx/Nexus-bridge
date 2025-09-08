from __future__ import annotations

from core.settings_models import NetworkConfig


def get_next_rpc_from_network_config(network_config: NetworkConfig, logger, change: bool = False):
    if not network_config.rpcs:
        logger.error(f"Error: No RPC endpoints configured for network {network_config.name}")
        raise ValueError(f"No RPC endpoints configured for network {network_config.name}")

    if len(network_config.rpcs) == 1 and change:
        logger.warning(f"Warning: {network_config.name} has only one RPC: {network_config.rpcs[network_config.current_rpc_index]}")
    else:
        network_config.current_rpc_index = (network_config.current_rpc_index + 1) % len(network_config.rpcs)
    return network_config.rpcs[network_config.current_rpc_index]
