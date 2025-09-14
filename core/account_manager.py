import asyncio
import dataclasses
import random
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import joinedload

from core.config import PK_TXT_FILE, PROXIES_TXT_FILE, CEX_DEPOSIT_ADDRESSES_TXT_FILE
from core.db_utils.db import db
from core.db_utils.models import Account, RouteAction, RouteStatus, Route
from core.txt_manager import TxtManager
from core.notificator import Notificator
from utils.utils import read_toml, randfloat, excname
from core.logger import get_logger, LogContext
from core.init_settings import settings
from tasks.executioner import Executioner


class AccountManager:
    def __init__(self):
        self.accounts: dict[int, Account] = {}
        self.spare_proxies = []
        self.flows = []
        self.flows_remaining = len(self.flows)
        self.accounts_per_flow = settings.flow.wallets_per_flow

        self.completed_accounts = 0
        self.completed_accounts_lock = asyncio.Lock()  # Блокировка для счетчика
        self.processed_account_ids = set()  # Множество для отслеживания обработанных аккаунтов
        self.logger = get_logger(class_name=self.__class__.__name__)
        self.tg_notificator = Notificator(LogContext.get())

    def load_accounts_from_excel(self):
        columns = dataclasses.asdict(settings.private)
        excel_manager = ExcelManager()

        accounts, spare_proxies = excel_manager.load_accounts(**columns)
        db.add_accounts(accounts, spare_proxies)

    def load_accounts_from_txt(self):
        txt_manager = TxtManager()
        accounts, spare_proxies = txt_manager.load_accounts(PK_TXT_FILE, PROXIES_TXT_FILE, CEX_DEPOSIT_ADDRESSES_TXT_FILE)
        db.add_accounts(accounts, spare_proxies)


    async def generate_new_routes_for_preset(self, preset: dict[str, Path | str]):
        preset_data = read_toml(preset["path"])
        db.delete_all_routes()

        # self.load_accounts_from_excel()
        self.load_accounts_from_txt()

        db.generate_routes_for_accounts(preset_data)


    def create_flows(self):
        # if settings.general.SHUFFLE_ACCOUNTS:
        #     values = list(self.accounts.values())
        #     random.shuffle(values)
        #
        #     # Создаем новый словарь с теми же ключами, но перемешанными значениями
        #     shuffled_dict = {key: values[i - 1] for i, key in enumerate(sorted(self.accounts.keys()), 1)}
        #     self.accounts = shuffled_dict

        accounts_objects = list(self.accounts.values())
        self.flows = [
            accounts_objects[i:i + self.accounts_per_flow]
            for i in range(0, len(self.accounts), self.accounts_per_flow)
        ]
        self.logger.info(f"Created {len(self.flows)} flows with {self.accounts_per_flow} wallets each")
        return self.flows


    async def process_account(self, account: Account, start_sleep: float, account_num: int, rerun_failed: bool):
        total_actions = len(list(account.route.actions))
        await asyncio.sleep(start_sleep)

        # Создаем базовый контекст для логгера аккаунта
        base_log_context = {
            "total_account_num": account_num,
            "account_name": account.name,
            "account_address": account.evm_address,
            "total_actions": total_actions,
        }
        base_log_context = base_log_context | LogContext.get()

        # Создаем логгер для аккаунта
        account_logger = get_logger(class_name=self.__class__.__name__, **base_log_context)
        previous_status = account.route.status

        session = db.Session()
        try:
            # Загружаем все необходимые связи заранее
            account = session.merge(account)  # Привязываем аккаунт к текущей сессии

            # Загружаем все необходимые связи
            account = session.query(Account).options(
                joinedload(Account.route).joinedload(Route.actions).joinedload(RouteAction.params)
            ).filter(Account.id == account.id).first()
        finally:
            session.close()

        action = None
        actions_dict = {}
        try:
            await db.update_obj_column(account.route, "status", RouteStatus.IN_PROGRESS)
            await db.update_obj_column(account.route, "started_at", datetime.now())

            for action_num, action in enumerate(list(account.route.actions), start=1):
                action_log_context = {
                    **base_log_context,
                    "action_num": action_num,
                    "try_num": 0,
                }
                account_logger = get_logger(class_name=self.__class__.__name__, **action_log_context)
                if action.action_name not in actions_dict:
                    actions_dict[action.action_name] = []

                if rerun_failed:
                    if action.status == RouteStatus.COMPLETED:
                        account_logger.warning(f"Skipping {action.action_name} with status {action.status}")
                        continue
                else:
                    if action.status == RouteStatus.COMPLETED or action.status == RouteStatus.FAILED:
                        account_logger.warning(f"Skipping {action.action_name} with status {action.status}")
                        continue

                await db.update_obj_column(action, "status", RouteStatus.IN_PROGRESS)
                await db.update_obj_column(action, "started_at", datetime.now())
                try:
                    executioner = Executioner(account=account, total_account_num=account_num,
                                              action_num=action_num, total_actions=total_actions)
                    result = await executioner.execute_action(action=action)

                    if result is True or isinstance(result, dict):
                        actions_dict[action.action_name].append(True)
                        await db.update_obj_column(action, "status", RouteStatus.COMPLETED)
                    else:
                        actions_dict[action.action_name].append(False)
                        await db.update_obj_column(action, "status", RouteStatus.FAILED)

                    # actions_dict[action.action_name]["count"] += 1
                    await db.update_obj_column(action, "completed_at", datetime.now())
                    if action_num < len(list(account.route.actions)):
                        delay = random.randint(settings.delays.action_delay[0], settings.delays.action_delay[1])
                        account_logger.info(f"Sleeping for 💤{delay}💤 seconds before next action")
                        await asyncio.sleep(delay)
                    else:
                        break
                # except (curl_cffi.requests.exceptions.ConnectionError, curl_cffi.curl.CurlError):
                #     account_logger.warning(f"Account {account.name} request error while opening controller, retrying...")
                #     continue

                except Exception as e:
                    if settings.logging.debug_logging:
                        account_logger.exception(f"{excname(e)} Error executing action: {e}")
                    else:
                        account_logger.error(f"{excname(e)} Error executing action: {e}")

                    actions_dict[action.action_name].append(False)
                    # actions_dict[action.action_name]["count"] += 1
                    await db.update_obj_column(action, "status", RouteStatus.FAILED)
                    await db.update_obj_column(action, "completed_at", datetime.now())
                    if isinstance(e, RuntimeError):
                        raise e

                    return

            account_logger.info(f"Account {account.name} finished, waiting for other accounts in flow")

            previous_status = account.route.status
            if False in list(actions_dict.values()):
                await db.update_obj_column(account.route, "status", RouteStatus.FAILED)

            else:
                await db.update_obj_column(account.route, "status", RouteStatus.COMPLETED)

            await db.update_obj_column(account.route, "completed_at", datetime.now())
            await self.finalize_account_processing(account, actions_dict, previous_status, account_logger, base_log_context)

        except Exception as e:
            if settings.logging.debug_logging:
                self.logger.exception(f"{excname(e)} Error processing account: {e}")
            else:
                self.logger.error(f"{excname(e)} Error processing account: {str(e)}")
            if account.route:
                await db.update_obj_column(account.route, "status", RouteStatus.FAILED)
                await db.update_obj_column(account.route, "completed_at", datetime.now())

            if action:
                actions_dict[action.action_name].append(False)
                # actions_dict[action.action_name]["count"] += 1

            await self.finalize_account_processing(account, actions_dict, previous_status, account_logger, base_log_context)


    async def finalize_account_processing(self, account, actions_dict, previous_status, account_logger, base_log_context):
        # Используем блокировку для безопасного обновления счетчика
        async with self.completed_accounts_lock:
            # Проверяем, что аккаунт еще не был учтен и статус действительно изменился
            if account.id not in self.processed_account_ids and previous_status == RouteStatus.IN_PROGRESS:
                self.processed_account_ids.add(account.id)
                self.completed_accounts += 1
                account_logger.debug(f"Completed accounts: {self.completed_accounts}")

        await self.tg_notificator.send_notification_for_done_account(account, actions_dict,
                                                                     self.completed_accounts, base_log_context)


    async def process_flow(self, flow, rerun_failed):
        tasks = []
        start_sleep = 0

        def get_key_by_value(dictionary, value):
            try:
                return next(key for key, val in dictionary.items() if val == value)
            except StopIteration:
                return None

        try:
            for account in flow:
                min_delay, max_delay = settings.delays.accounts_delay
                account_delay_in_flow = randfloat(min_delay, max_delay)
                if start_sleep > 0:
                    self.logger.info(f"Account {account.name} sleeping for 💤{start_sleep} before start")

                account_num = get_key_by_value(self.accounts, account)
                task = asyncio.create_task(self.process_account(account, start_sleep, account_num, rerun_failed))
                tasks.append(task)
                start_sleep += account_delay_in_flow

            # Ждем завершения всех задач
            await asyncio.gather(*tasks)
            self.flows_remaining -= 1
            if self.flows_remaining >= 1:
                min_delay, max_delay = settings.delays.flow_delay
                delay = randfloat(min_delay, max_delay)
                self.logger.info(f"All accounts in flow finished, sleeping for 💤{delay} seconds until next flow")
                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            if settings.logging.debug_logging:
                self.logger.debug("Cancelling all tasks in flow...")
            # Отменяем все запущенные задачи
            for task in tasks:
                if not task.done():
                    task.cancel()
            # Ждем отмены всех задач
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        except Exception as e:
            self.logger.error(f"Error in flow: {e}")
            raise

    async def process_flows(self, rerun_failed):
        self.flows_remaining = len(self.flows)
        try:
            for flow in self.flows:
                await self.process_flow(flow, rerun_failed)
        except asyncio.CancelledError:
            if settings.logging.debug_logging:
                self.logger.debug("Flow processing cancelled")
            raise

    async def launch(self, rerun_failed = False):
        """Запускает обработку всех flows"""
        session = db.Session()
        try:
            if rerun_failed:
                accounts_from_db = session.query(Account).join(
                    Account.route
                ).join(
                    Route.actions
                ).filter(
                    RouteAction.status.in_([RouteStatus.FAILED])
                ).options(
                    joinedload(Account.route).joinedload(Route.actions)
                ).all()
            else:
                accounts_from_db = session.query(Account).join(Account.route).options(
                    joinedload(Account.route).joinedload(Route.actions)
                ).filter(
                    Route.status.in_([RouteStatus.PENDING, RouteStatus.IN_PROGRESS])
                ).all()

            if settings.general.SHUFFLE_ACCOUNTS:
                random.shuffle(accounts_from_db)

            for i, account in enumerate(accounts_from_db, start=1):
                self.accounts[i] = account

            account_max = len(self.accounts)
            LogContext.set(
                total_account_max=account_max,
                maximum_retries=settings.general.number_of_retries,
            )

            self.logger.info(f"Loaded {account_max} accounts with pending/in-progress routes")
            self.create_flows()
            await self.process_flows(rerun_failed)

            self.logger.success(f"All flows finished...")
            await self.tg_notificator.send_notification_for_all_done(account_max)

        except asyncio.CancelledError:
            if settings.logging.debug_logging:
                self.logger.debug("Gracefully shutting down...")
            # Здесь можно добавить cleanup код если нужно
            raise  # Важно пробросить CancelledError дальше

        finally:
            session.close()
