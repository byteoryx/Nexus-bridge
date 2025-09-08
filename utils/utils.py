from __future__ import annotations

import asyncio
import inspect
import json
import os
import random
import secrets
import string
from datetime import datetime, timedelta
import time
import tomllib
from decimal import Decimal
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse, parse_qs

if TYPE_CHECKING:
    from libs.requests.session import BaseAsyncSession


def check_cookies(requests_client, cookie_names: list[str]) -> bool | None:
    session: BaseAsyncSession = getattr(requests_client, "async_session", None)
    if session:
        cookies: CookieJar = session.cookies.jar
        present_cookie_names = [cookie.name for cookie in cookies]
        return any(name in present_cookie_names for name in cookie_names)

def parse_raw_tx_data_legacy(data: str, has_function: bool = True, has_0x: bool = True):
    """
    Used for inspecting raw input of transactions
    """
    if has_function:
        function_signature = data[:10]
        print('MY MethodID: ', function_signature)
        data = data[10:]
    if has_0x and not has_function:
        data = data[2:]

    i = 0
    while data:
        print(f'[{i}]: {data[:64]}')
        data = data[64:]
        i += 1

def string_contains(s: str, subs: list | tuple) -> bool:
    return s and any(sub in s for sub in subs)


class CaseInsensitiveDict(dict):
    """Словарь, в котором ключи регистронезависимы."""

    def __init__(self, data=None, **kwargs):
        super().__init__()
        self.update(data or {})
        self.update(kwargs)

    def __setitem__(self, key, value):
        super().__setitem__(key.lower() if isinstance(key, str) else key, value)

    def __getitem__(self, key):
        return super().__getitem__(key.lower() if isinstance(key, str) else key)

    def __contains__(self, key):
        return super().__contains__(key.lower() if isinstance(key, str) else key)

    def get(self, key, default=None):
        return super().get(key.lower() if isinstance(key, str) else key, default)

    def pop(self, key, default=None):
        return super().pop(key.lower() if isinstance(key, str) else key, default)

    def update(self, data=None, **kwargs):
        if data is None:
            data = {}
        if isinstance(data, dict):
            for key, value in data.items():
                self[key] = value
        else:
            for key, value in data:
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value


def get_caller_function():
    # Получаем текущий стек вызовов
    frame = inspect.currentframe()
    # Получаем информацию о вызывающем фрейме (предыдущий на два шага назад)
    caller_frame = frame.f_back.f_back
    # Получаем имя вызывающей функции
    caller_function_name = caller_frame.f_code.co_name
    # Получаем имя модуля (файла), в котором находится вызывающая функция
    caller_module = inspect.getmodule(caller_frame)
    caller_module_name = caller_module.__name__ if caller_module else "Unknown"

    # Не забудьте освободить ресурсы
    del frame
    del caller_frame
    return f"Caller function: {caller_function_name} from module: {caller_module_name}"


async def log_sleep(class_object, time_: float = 10, message: str = ""):
    log_message = f"Sleeping for {time_} seconds " + message
    for elem in ("logger", "_logger", "__logger"):
        try:
            if getattr(class_object, elem):
                logger = getattr(class_object, elem)
                logger.info(log_message)
        except AttributeError:
            pass
    await asyncio.sleep(time_)

def contains_digit(sequence):
    return any(character.isdigit() for character in sequence)


def time_until_target(target_time_str: str) -> int:
    """
    Вычисляет количество секунд, оставшихся до ближайшего наступления указанного времени.

    Args:
        target_time_str: Желаемое время в формате строки "ЧЧ:ММ", например "13:20"

    Returns:
        int: Количество секунд до ближайшего наступления указанного времени
    """
    hours, minutes = map(int, target_time_str.split(':'))
    now = datetime.now()

    target_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)

    if target_time <= now:
        target_time += timedelta(days=1)

    return int((target_time - now).total_seconds())


async def wait_nl(from_: int | float | str, to_: int | float | str): # nl = no logger
    await asyncio.sleep(randfloat(from_, to_))

def excname(exception):
    return exception.__class__.__name__

def get_query_param(url: str, name: str):
    values = parse_qs(urlparse(url).query).get(name)
    if values:
        return values[0]
    return None

def get_milliseconds_timestamp(days_before = 0, hours_before = 0, minutes_before = 0, seconds_before = 0,
                               days_after = 0, hours_after = 0, minutes_after = 0, seconds_after = 0) -> int:
    days = days_after - days_before
    hours = hours_after - hours_before
    minutes = minutes_after - minutes_before
    seconds = seconds_after - seconds_before

    date = datetime.now() + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    return int(date.timestamp() * 1000)

def get_now_seconds_timestamp() -> int:
    return int(datetime.now().timestamp())

def read_toml(path: str | Path) -> dict[str, Any]:
    with open(path, 'rb') as f:
        data = tomllib.load(f)
        return data

def iso_time():
    return datetime.now().isoformat()[:-3] + 'Z'

def generate_random_string(length=10):
    chars = string.ascii_letters + string.digits  # a-z, A-Z, 0-9
    return ''.join(random.choices(chars, k=length))

def generate_random_lowercase_string(length=10):
    chars = string.ascii_lowercase + string.digits # a-z, 0-9
    return ''.join(secrets.choice(chars) for _ in range(length))


def randfloat(from_: int | float | str, to_: int | float | str,
              step: int | float | str | None = None) -> float:
    """
    Return a random float from the range.

    :param Union[int, float, str] from_: the minimum value
    :param Union[int, float, str] to_: the maximum value
    :param Optional[Union[int, float, str]] step: the step size (calculated based on the number of decimal places)
    :return float: the random float
    """
    from_ = Decimal(str(from_))
    to_ = Decimal(str(to_))
    if not step:
        step = 1 / 10 ** (min(from_.as_tuple().exponent, to_.as_tuple().exponent) * -1)

    step = Decimal(str(step))
    rand_int = Decimal(str(random.randint(0, int((to_ - from_) / step))))
    return float(rand_int * step + from_)


def update_dict(modifiable: dict, template: dict, rearrange: bool = True, remove_extra_keys: bool = False) -> dict:
    """
    Update the specified dictionary with any number of dictionary attachments based on the template without changing the values already set.

    :param dict modifiable: a dictionary for template-based modification
    :param dict template: the dictionary-template
    :param bool rearrange: make the order of the keys as in the template, and place the extra keys at the end (True)
    :param bool remove_extra_keys: whether to remove unnecessary keys and their values (False)
    :return dict: the modified dictionary
    """
    for key, value in template.items():
        if key not in modifiable:
            modifiable.update({key: value})

        elif isinstance(value, dict):
            modifiable[key] = update_dict(
                modifiable=modifiable[key], template=value, rearrange=rearrange, remove_extra_keys=remove_extra_keys
            )

    if rearrange:
        new_dict = {}
        for key in template.keys():
            new_dict[key] = modifiable[key]

        for key in tuple(set(modifiable) - set(new_dict)):
            new_dict[key] = modifiable[key]

    else:
        new_dict = modifiable.copy()

    if remove_extra_keys:
        for key in tuple(set(modifiable) - set(template)):
            del new_dict[key]

    return new_dict


def join_path(path: str | tuple | list) -> str:
    if isinstance(path, str):
        return path
    return str(os.path.join(*path))


def read_json(path: str | tuple | list, encoding: str | None = None) -> list | dict:
    path = join_path(path)
    return json.load(open(path, encoding=encoding))


def touch(path: str | tuple | list, file: bool = False) -> bool:
    """
    Create an object (file or directory) if it doesn't exist.

    :param Union[str, tuple, list] path: path to the object
    :param bool file: is it a file?
    :return bool: True if the object was created
    """
    path = join_path(path)
    if file:
        if not os.path.exists(path):
            with open(path, 'w') as f:
                f.write('')

            return True

        return False

    if not os.path.isdir(path):
        os.mkdir(path)
        return True

    return False


def write_json(path: str | tuple | list, obj: list | dict, indent: int | None = None,
               encoding: str | None = None) -> None:
    """
    Write Python list or dictionary to a JSON file.

    :param Union[str, tuple, list] path: path to the JSON file
    :param Union[list, dict] obj: the Python list or dictionary
    :param Optional[int] indent: the indent level
    :param Optional[str] encoding: the name of the encoding used to decode or encode the file
    """
    path = join_path(path)
    with open(path, mode='w', encoding=encoding) as f:
        json.dump(obj, f, indent=indent)


def text_between(text: str, begin: str = '', end: str = '') -> str:
    """
    Extract a text between strings.

    :param str text: a source text
    :param str begin: a string from the end of which to start the extraction
    :param str end: a string at the beginning of which the extraction should end
    :return str: the extracted text or empty string if nothing is found
    """
    try:
        if begin:
            start = text.index(begin) + len(begin)
        else:
            start = 0
    except:
        start = 0

    try:
        if end:
            end = text.index(end, start)
        else:
            end = len(text)
    except:
        end = len(text)

    excerpt = text[start:end]
    if excerpt == text:
        return ''

    return excerpt


def time_elapsed(start_time):
    """
    Вычисляет, сколько времени прошло с указанного момента.
    
    Args:
        start_time: время начала в формате time.time()
        
    Returns:
        float: количество секунд, прошедших с указанного момента
    """
    return time.time() - start_time


def time_elapsed_formatted(start_time):
    """
    Вычисляет и форматирует время, прошедшее с указанного момента.
    
    Args:
        start_time: время начала в формате time.time()
        
    Returns:
        str: отформатированная строка с прошедшим временем (часы:минуты:секунды)
    """
    elapsed_seconds = time.time() - start_time
    hours, remainder = divmod(int(elapsed_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def time_elapsed_since_datetime(start_datetime):
    """
    Вычисляет, сколько времени прошло с указанного момента.
    
    Args:
        start_datetime: время начала в формате datetime объекта
        
    Returns:
        timedelta: объект с разницей во времени
    """
    current_time = datetime.now()
    time_diff = current_time - start_datetime
    
    return time_diff
