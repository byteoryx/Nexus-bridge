import asyncio

from core.logger import get_logger
from libs.blockchains.eth_async.base_evm_task_class import BaseEVMTaskClass
from libs.blockchains.eth_async.data.models import RawContract, CommonValues
from libs.blockchains.omnichain_functions import resolve_token_addresses
from libs.blockchains.omnichain_models import TokenAmount
from libs.blockchains.eth_async.ethclient import EthClient
from libs.requests.web_requests import RequestsClient
from utils.utils import log_sleep


class HyperLaneFeeChecker(BaseEVMTaskClass["HyperLaneFeeChecker"]):
    GRAPHQL_URL = "https://explorer4.hasura.app/v1/graphql"

    CONTRACTS = None

    # ⚙️ Переключатель для запросов (True = включены, False = выключены)
    ENABLE_REQUESTS = True

    def __init__(self, eth_client: EthClient, requests_client: RequestsClient, log_context):
        self._requests_client = requests_client
        self._eth_client = eth_client
        self._logger = get_logger(class_name=self.__class__.__name__, **log_context)
        self._current_network = None
        super().__init__(self)

    async def fetch_message_ids(self, search, date_filter):
        if not self.ENABLE_REQUESTS:
            self._logger.warning("Запросы к GraphQL отключены (fetch_message_ids).")
            return []

        query = """query ($search: bytea, $date_filter: timestamp) {
          q0: message_view(where: {_and: [{sender: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
          q1: message_view(where: {_and: [{recipient: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
          q2: message_view(where: {_and: [{origin_tx_sender: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
          q3: message_view(where: {_and: [{destination_tx_sender: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
          q4: message_view(where: {_and: [{msg_id: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
        }"""
        variables = {"search": search, "date_filter": date_filter}
        payload = {"query": query, "variables": variables}

        try:
            response = await self._requests_client.post(self.GRAPHQL_URL, json=payload)

            if "errors" in response:
                self._logger.error(f"GraphQL error при поиске сообщений: {response['errors']}")
                return []

            if "data" not in response:
                self._logger.warning(f"Некорректный ответ от GraphQL: {response}")
                return []

            msg_ids = set()
            for key, values in response["data"].items():
                for msg in values:
                    if "msg_id" in msg:
                        msg_ids.add(msg["msg_id"])

            self._logger.info(f"Найдено {len(msg_ids)} сообщений.")
            return list(msg_ids)

        except Exception as e:
            self._logger.error(f"Ошибка в fetch_message_ids: {e}")
            return []

    async def fetch_total_payment(self, msg_id):
        if not self.ENABLE_REQUESTS:
            self._logger.warning(f"Запросы к GraphQL отключены (fetch_total_payment для msg_id={msg_id}).")
            return 0

        query = """query ($identifier: bytea!) {
          message_view(where: {msg_id: {_eq: $identifier}}, limit: 1) {
            msg_id
            total_payment
            delivery_occurred_at
          }
        }"""
        payload = {"query": query, "variables": {"identifier": msg_id}}

        try:
            response = await self._requests_client.post(self.GRAPHQL_URL, json=payload)

            if "errors" in response:
                self._logger.error(f"GraphQL error for msg_id={msg_id}: {response['errors']}")
                return 0

            if "data" not in response or "message_view" not in response["data"]:
                self._logger.warning(f"Некорректный ответ от GraphQL для msg_id={msg_id}: {response}")
                return 0

            data = response["data"]["message_view"]

            if data and data[0].get("total_payment"):
                return int(data[0]["total_payment"])
            else:
                self._logger.info(f"Нет данных для msg_id={msg_id}")
                return 0

        except Exception as e:
            self._logger.error(f"Ошибка при fetch_total_payment для msg_id={msg_id}: {e}")
            return 0

    async def get_total_fees(self, date_filter) -> tuple[TokenAmount, int]:
        address = self._eth_client.w3_account.address
        search = "\\x" + address.lower()[2:]

        msg_ids = await self.fetch_message_ids(search, date_filter)
        total_igp = 0

        for msg_id in msg_ids:
            total_igp += await self.fetch_total_payment(msg_id)
            await asyncio.sleep(0.2)

        total_igp = TokenAmount(total_igp, 18, True)
        self._logger.success(f"Сумма для {address}: {total_igp.Ether} ETH")
        return total_igp, len(msg_ids)