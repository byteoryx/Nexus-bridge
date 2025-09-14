from __future__ import annotations

import functools
import inspect
import random
from typing import Any, Callable, Iterable, Optional, TYPE_CHECKING, Coroutine, Awaitable

if TYPE_CHECKING:
    from tasks.controller import Controller
    from tasks.executioner import Executioner


async def nexus_network_resolver(executioner: Executioner, action_type, action_params: dict, controller: Controller):
    action_network = action_type.split("_")[-1]
    nexus_bridge_params = action_params["nexus_bridge_params"]
    if action_network == "biggest":
        biggest_balance_network, biggest_balance = await executioner.get_biggest_usdc_balance(controller,
                                                                                       nexus_bridge_params[
                                                                                           "networks_to_check_balance_for_biggest"])
        executioner.logger.info(
            f"Biggest USDC balance: {biggest_balance} in network {biggest_balance_network.capitalize()}")

        action_network = biggest_balance_network

    return action_network


def _get_from_path(data: dict, path: Iterable[str]) -> Optional[Any]:
    """Безопасно извлечь значение из словаря по цепочке ключей."""
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur

# AwaitableType = Callable[[Executioner, str, dict[str, Any], Controller], Awaitable[str]]
# CallableType = Callable[[Executioner, str, dict[str, Any], Controller], str]

def prechecks(
    network_resolver: Callable[[Executioner, str, dict[str, Any], Controller], str] |
                      Callable[[Executioner, str, dict[str, Any], Controller], Awaitable[str]] |
                      None = None,
    random_networks_path: Iterable[str] = ("swap", "random_networks_to_swap"),
    random_log_label: str = "network",
):
    """
    Декоратор для async-методов класса с параметрами:
      (self, action_type, action_params, controller, ...)

    Поведение:
      1) Определяет сеть из action_type (по умолчанию — последний сегмент через "_"),
         либо через кастомный network_resolver(self, action_type, action_params).
      2) Если сеть == "random" — берёт случайную из action_params по random_networks_path.
      3) await self.gas_control(controller, action_network)
      4) await self.check_balance_and_withdraw(controller, action_network, action_params)
         При неуспехе — логирует и возвращает False.
      5) Если у целевой функции есть параметр `action_network`, он будет проставлен.

    Параметры:
      - network_resolver: (опционально) функция, возвращающая строку сети.
      - random_networks_path: путь ключей к списку сетей в action_params.
      - random_log_label: подпись в логах при выборе случайной сети.
    """
    def decorator(func: Callable):
        if not inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            def unsupported_sync_wrapper(*_args, **_kwargs):
                raise RuntimeError("prechecks предназначен для async-методов.")
            return unsupported_sync_wrapper

        sig = inspect.signature(func)

        @functools.wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            # Привязываем аргументы к именам
            bound = sig.bind(self, *args, **kwargs)
            bound.apply_defaults()

            action_type: Optional[str] = bound.arguments.get("action_type")
            action_params: Optional[dict] = bound.arguments.get("action_params")
            controller = bound.arguments.get("controller")

            if action_type is None or action_params is None or controller is None:
                raise TypeError(
                    f"@prechecks ожидает параметры 'action_type', 'action_params', 'controller' в функции {func.__name__}"
                )

            # 1) Определяем сеть
            if network_resolver is not None:
                if not inspect.iscoroutinefunction(func):
                    action_network = network_resolver(self, action_type, action_params, controller)
                else:
                    action_network = await network_resolver(self, action_type, action_params, controller)
            else:
                action_network = (
                    action_type.split("_")[-1]
                    if isinstance(action_type, str) and "_" in action_type
                    else None
                )

            # 2) Обработка random
            if action_network == "random":
                candidates = _get_from_path(action_params, random_networks_path)
                if not candidates:
                    if hasattr(self, "logger"):
                        self.logger.error(
                            f"Не удалось выбрать случайную сеть: по пути {list(random_networks_path)} список пуст/отсутствует"
                        )
                    return False
                action_network = random.choice(candidates)
                if hasattr(self, "logger"):
                    try:
                        self.logger.info(f"Selected random {random_log_label}: {str(action_network).capitalize()}")
                    except Exception:
                        # На случай экзотической капитализации/типов
                        self.logger.info(f"Selected random {random_log_label}: {action_network}")

            # 3) Контроль газа
            await self.gas_control(controller, action_network)

            # 4) Проверка баланса и авто-вывод при необходимости
            balance_ok = await self.check_balance_and_withdraw(controller, action_network, action_params)
            if not balance_ok:
                if hasattr(self, "logger"):
                    self.logger.error("Oops, balance is still too low, quitting action")
                return False

            # 5) Пробуем передать action_network, если целевая функция его принимает
            # if "action_network" in sig.parameters and "action_network" not in bound.arguments:
            #     print(f"Adding action_network to kwargs for {func.__name__}")
            kwargs["action_network"] = action_network

            return await func(self, *args, **kwargs)

        return async_wrapper

    return decorator
