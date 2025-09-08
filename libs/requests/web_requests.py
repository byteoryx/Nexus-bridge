from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from core.db_utils.models import Account
from core.init_settings import settings
from core.logger import get_logger
from libs.requests.exceptions import CustomRequestException, EXTERNAL_REQUEST_EXCEPTIONS
from libs.requests.session import BaseAsyncSession
from utils.utils import CaseInsensitiveDict

if TYPE_CHECKING:
    from tasks.controller import Controller


def generate_client_hints_ua(chrome_version: int | str):
    basic_not_a_brand = '"Not A Brand"'
    possible_splitters = ("_", "(", ":", "-")
    possible_versions = (';v="24"', ';v="99"', ';v="8"')
    versions_weights = (3, 1, 1)
    not_a_brand = basic_not_a_brand.replace(" ", random.choice(possible_splitters), 1)
    not_a_brand = not_a_brand.replace(" ", random.choice(possible_splitters), 1)
    not_a_brand += random.choices(possible_versions, versions_weights)[0]

    chromium = f'"Chromium";v="{chrome_version}"'
    chrome = f'"Google Chrome";v="{chrome_version}"'
    uas = [not_a_brand, chromium, chrome]
    random.shuffle(uas)
    sec_ch_ua = ''
    for ua in uas:
        sec_ch_ua += f'{ua}, '
    # '"Chromium";v="134","Google Chrome";v="134","Not-A-Brand";v="24"'
    return sec_ch_ua.strip(", ")

class RequestsClient:
    def __init__(self, controller: Controller,
                 account: Account,
                 session: BaseAsyncSession,
                 log_context: dict,
                 ):
        self.async_session = session
        self.user_agent = account.user_agent
        self.platform = account.os_user_agent
        self.chrome_version = account.chrome_version
        self.basic_headers = {
        'accept': '*/*',
        # 'accept-encoding': 'gzip, deflate, br',
        'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'content-type': 'application/json',
        'priority': 'u=1, i',
        'sec-ch-ua': generate_client_hints_ua(self.chrome_version),
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{self.platform}"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': self.user_agent,
        }
        self.logger = get_logger(class_name=self.__class__.__name__, **log_context)
        self._controller = controller


    @staticmethod
    def aiohttp_params(params: dict[str, ...] | None) -> dict[str, str | int | float] | None:
        if not params:
            return
        new_params = params.copy()

        for key, value in params.items():
            if value is None:
                del new_params[key]

            if isinstance(value, bool):
                new_params[key] = str(value).lower()

            elif isinstance(value, bytes):
                new_params[key] = value.hex()

        return new_params

    @classmethod
    async def _handle_response(cls, response, acceptable_statuses=None, resp_handler=None, with_text=False):
        if acceptable_statuses and len(acceptable_statuses) > 0:
            if response.status_code not in acceptable_statuses:
                raise CustomRequestException(response)
        try:
            if with_text:
                return response.text if resp_handler is None else resp_handler(response)
            else:
                return response.json() if resp_handler is None else resp_handler(response)
        except Exception as e:
            raise e

    async def _make_request_with_proxy_fallback(self, method_name: str, url, **kwargs):
        retries = 0
        max_retries = settings.general.number_of_retries

        while retries < max_retries:
            try:
                self.async_session = self._controller.async_session
                request_func = getattr(self.async_session, method_name)
                return await request_func(url, **kwargs)
            except EXTERNAL_REQUEST_EXCEPTIONS as e:
                self.logger.warning(f"Proxy error: {str(e)}. Try {retries + 1}/{max_retries}")
                retries += 1
                if retries < max_retries:
                    await asyncio.sleep(5)
                    await self._controller.change_proxy()
                    continue
                else:
                    raise e

    def _get_headers(self, additional_headers: dict | None, fully_external_headers: dict | None) -> dict:
        # Функция для конвертации обычного словаря в CaseInsensitiveDict
        def to_case_insensitive(headers_dict: dict) -> CaseInsensitiveDict:
            return CaseInsensitiveDict(headers_dict)

        # Базовая инициализация
        base_headers = to_case_insensitive(self.basic_headers)
        base_headers['content-type'] = 'application/json'

        if additional_headers:
            headers = base_headers
            headers.update(additional_headers)
        elif fully_external_headers:
            headers = to_case_insensitive(fully_external_headers)
        else:
            headers = base_headers

        return dict(headers)

    async def _request_response(self, method: str, url: str, additional_headers: dict | None = None,
                  fully_external_headers: dict | None = None, **kwargs):
        headers = self._get_headers(additional_headers, fully_external_headers)
        return await self._make_request_with_proxy_fallback(method.lower(), url, headers=headers, **kwargs)


    async def do_request(self,
                         method: str,
                         url: str,
                         acceptable_statuses: list | None = None,
                         resp_handler = None,
                         with_text: bool = False,
                         additional_headers: dict | None = None,
                         fully_external_headers: dict | None = None,
                         raw: bool = False,
                         **kwargs):
        # self.logger.debug(f"Sending with proxy: {self.async_session.proxy} {self.async_session.proxies}")
        response = await self._request_response(method, url, additional_headers, fully_external_headers, **kwargs)
        if not raw:
            return await self._handle_response(response, acceptable_statuses, resp_handler, with_text)
        return response

    async def get(self, url: str, acceptable_statuses: list | None = None, resp_handler = None,
                  with_text: bool = False, additional_headers: dict | None = None,
                  fully_external_headers: dict | None = None, raw = False, **kwargs):
        return await self.do_request('GET', url, acceptable_statuses, resp_handler, with_text,
                                     additional_headers, fully_external_headers, raw, **kwargs)

    async def post(self, url: str, acceptable_statuses: list | None = None, resp_handler = None,
                   with_text: bool = False, additional_headers: dict | None = None,
                   fully_external_headers: dict | None = None, raw = False, **kwargs):
        return await self.do_request('POST', url, acceptable_statuses, resp_handler, with_text,
                                     additional_headers, fully_external_headers, raw, **kwargs)

    async def put(self, url: str, acceptable_statuses: list | None = None, resp_handler = None,
                  with_text: bool = False, additional_headers: dict | None = None,
                  fully_external_headers: dict | None = None, raw = False, **kwargs):
        return await self.do_request('PUT', url, acceptable_statuses, resp_handler, with_text,
                                     additional_headers, fully_external_headers, raw, **kwargs)

    async def delete(self, url: str, acceptable_statuses: list | None = None, resp_handler = None,
                  with_text: bool = False, additional_headers: dict | None = None,
                  fully_external_headers: dict | None = None, raw = False, **kwargs):
        return await self.do_request('DELETE', url, acceptable_statuses, resp_handler, with_text,
                                     additional_headers, fully_external_headers, raw, **kwargs)

    async def get_random_username(self):
        url = "https://randomuser.me/api/?inc=login"
        return await self.get(url, [200], lambda r: r.json()["results"][0]["login"]["username"])
