import functools
import sys
from contextlib import contextmanager
from typing import ParamSpec, TypeVar, Callable

from loguru import logger

from core.config import LOG_FILE
from core.init_settings import settings

P = ParamSpec('P')
R = TypeVar('R')


class LogContext:
    """Класс для хранения контекста логирования"""
    _context = {}

    @classmethod
    def set(cls, **kwargs):
        """Установить значения контекста"""
        cls._context.update(kwargs)

    @classmethod
    def get(cls):
        """Получить текущий контекст"""
        return cls._context

    @classmethod
    def clear(cls):
        """Очистить контекст"""
        cls._context.clear()


@contextmanager
def logging_context(**kwargs):
    try:
        LogContext.set(**kwargs)
        yield
    finally:
        LogContext.clear()


def get_logger(**context):
    current_context = LogContext.get().copy()

    default_context = {
        "total_account_num": 0,
        "total_account_max": 0,
        "action_num": 0,
        "total_actions": 0,
        "account_name": "-",
        "account_address": "FastFoodSofts",
        "class_name": "FastFoodSofts",
        "try_num": 0,
        "maximum_retries": 1,
    }
    # Обновляем контекст в порядке: дефолтный -> текущий -> новый
    default_context.update(current_context)
    default_context.update(context)

    return logger.bind(**default_context)


def format_address(addr: str) -> str:
    """Format Ethereum evm_address to show only first and last 7 characters"""
    try:
        if not addr or addr == '-' or len(addr) <= 14:
            return addr
        return f"{addr[:7]}...{addr[-7:]}"
    except Exception:
        return addr


def patch_address(record):
    try:
        addr = record["extra"].get("account_address")
        if addr:
            record["extra"]["account_address"] = format_address(addr)
    except Exception:
        pass  # В случае ошибки оставляем адрес как есть
    return record

def configure_logger(log_file: str, debug_mode: bool, log_to_file: bool, show_full_address: bool):
    beautiful_format = {
        "time": "<green>{time:HH:mm:ss}</green> | ",
        "level": "<level>{level: <8}</level> | ",
        "total_account_counting": "<white>[{extra[total_account_num]}/{extra[total_account_max]}]</white> | ",
        "account_name": "<white>[{extra[account_name]}]</white> | ",
        "action_counting": "<blue>[A{extra[action_num]}/{extra[total_actions]}]</blue> | ",
        "account_address": "<white>{extra[account_address]}</white> | ",
        "class_name": "<cyan>[{extra[class_name]}]</cyan> | ",
        # "try_count": "<magenta>[T{extra[try_num]}/{extra[maximum_retries]}]</magenta> | ",
        "message": "<level>{message}</level>",
    }

    format_str = ''.join(list(beautiful_format.values()))

    logger.remove()

    if log_to_file:
        logger.add(
            log_file,
            rotation="10 MB",
            retention="1 week",
            format=format_str,
        )
    
    # if debug_mode:
    #     logger.add(
    #         sys.stdout,
    #         format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
    #     )
    # else:
    logger.add(
        sink=sys.stderr,
        format=format_str,
    )
    if not show_full_address:
        logger.configure(patcher=patch_address)

def with_class_logging(func: Callable[P, R]) -> Callable[P, R]:
    """Декоратор для автоматического добавления имени класса и метода в логи"""
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        if args and hasattr(args[0], '__class__'):
            class_name = args[0].__class__.__name__
        else:
            class_name = 'Module'

        func_name = func.__name__
        logger_context = {"name": f"{class_name}.{func_name}"}
        logger_context.update(LogContext.get())  # Добавляем текущий контекст

        with logger.contextualize(**logger_context):
            return func(*args, **kwargs)

    return wrapper


def with_class_logging_async(func: Callable[P, R]) -> Callable[P, R]:
    """Декоратор для автоматического добавления имени класса и метода в логи (для асинхронных функций)"""
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        if args and hasattr(args[0], '__class__'):
            class_name = args[0].__class__.__name__
        else:
            class_name = 'Module'

        func_name = func.__name__
        logger_context = {"name": f"{class_name}.{func_name}"}
        logger_context.update(LogContext.get())  # Добавляем текущий контекст

        with logger.contextualize(**logger_context):
            return await func(*args, **kwargs)

    return wrapper


configure_logger(LOG_FILE, debug_mode=settings.logging.debug_logging,
                 log_to_file=settings.logging.log_to_file, show_full_address=settings.logging.show_full_address)
