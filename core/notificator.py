import curl_cffi
from curl_cffi.requests import AsyncSession

from core.db_utils.models import Account
from core.logger import get_logger
from core.init_settings import settings
from utils.utils import excname


class Notificator:
    def __init__(self, log_context):
        self.logger = get_logger(class_name=self.__class__.__name__, **log_context)

    async def _send_telegram_notification(self, text):
        if settings.telegram.send_notifications:
            session = AsyncSession()
            try:
                url = f"https://api.telegram.org/bot{settings.telegram.bot_key}/sendMessage"
                payload = {
                    "chat_id": settings.telegram.chat_id,
                    "text": text
                }
                response = await session.post(url, json=payload)

                if response.status_code == 200:
                    self.logger.info("Sent telegram notification to user! ✈️")
                else:
                    self.logger.error(f"Error while sending notification to user: {response.status_code}: {response.text}")

            except (curl_cffi.requests.exceptions.ConnectionError, curl_cffi.curl.CurlError) as e:
                self.logger.error(f"Failed to send telegram notification: {e}")

            finally:
                await session.close()


    async def send_notification_for_done_account(self, account: Account, actions_dict: dict[str, list],
                                                 completed_accounts: int, log_context):
        try:
            self.logger = get_logger(class_name=self.__class__.__name__, **log_context)
            total_actions = log_context["total_actions"]
            account_max = log_context["total_account_max"]
            successful_actions = 0
            failed_actions = 0

            # Группировка действий с одинаковыми именами
            grouped_actions = {}
            for action_name, action_results in actions_dict.items():
                if action_name not in grouped_actions:
                    grouped_actions[action_name] = {"success": 0, "fail": 0, "total": 0}

                # grouped_actions[action_name]["total"] += 1
                if action_results:
                    for res in action_results:
                        if res:
                            grouped_actions[action_name]["success"] += 1
                            successful_actions += 1
                        else:
                            grouped_actions[action_name]["fail"] += 1
                            failed_actions += 1
                    grouped_actions[action_name]["total"] = (grouped_actions[action_name]["success"]
                                                    + grouped_actions[action_name]["fail"])

                if grouped_actions[action_name]["total"] == 0:
                    grouped_actions.pop(action_name)

            # self.logger.debug(f"grouped_actions: {grouped_actions}")
            # Формирование строки действий
            actions_str = 'Actions:\n'
            for action_name, counts in grouped_actions.items():
                if counts["fail"] == 0:  # Все успешные
                    actions_str += f"✅ {action_name} ({counts['total']})\n"
                elif counts["success"] == 0:  # Все неудачные
                    actions_str += f"❌ {action_name} ({counts['total']})\n"
                else:  # Смешанные результаты
                    actions_str += f"⚠️ {action_name} - ✅{counts['success']}, ❌{counts['fail']}\n"

            text = (f"🍔🍔🍔FastFoodSofts🍔🍔🍔\n\n"
                    f"Account name: {account.name} completed route\n\n"
                    f"{total_actions} action(s) in route\n"
                    f"{actions_str}\n"
                    f"Summary: ✅Success - {successful_actions}, ❌Failed - {failed_actions}\n"
                    f"Completed accounts: {completed_accounts}/{account_max}")

            await self._send_telegram_notification(text)
        except Exception as e:
            self.logger.warning(f"Log context: {log_context}")
            self.logger.exception(f"{excname(e)}. Error sending notification {e}")

    async def send_notification_for_all_done(self, account_max):
        try:
            text = (f"🍔🍔🍔FastFoodSofts🍔🍔🍔\n\n"
                    f"Work finished!\n\n"
                    f"Total account done: {account_max}✅")
            await self._send_telegram_notification(text)
        except Exception as e:
            self.logger.error(f"{excname(e)}. Error sending notification {e}")

    def info(self, text: str):
        self.logger.info(text)
        if settings.telegram_notifications_enabled:
            if settings.enable_notifications_for_every_action:
                self._send_telegram_notification(f'👁️ INFO | {text}')

    def error(self, text):
        self.logger.error(text)
        if settings.telegram_notifications_enabled:
            self._send_telegram_notification(f'🔴 ERROR | {text}')

    def exception(self, text):
        self.logger.exception(text)
        if settings.telegram_notifications_enabled:
            self._send_telegram_notification(f'🟡 EXCEPTION | {text}')

    def success(self, text):
        self.logger.success(text)
        if settings.telegram_notifications_enabled:
            if settings.enable_notifications_for_every_action:
                self._send_telegram_notification(f'🟢 SUCCESS | {text}')
