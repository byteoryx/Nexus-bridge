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

    def __init__(self, eth_client: EthClient, requests_client: RequestsClient, log_context):
        self._requests_client = requests_client
        self._eth_client = eth_client
        self._logger = get_logger(class_name=self.__class__.__name__, **log_context)
        self._current_network = None
        super().__init__(self)


    async def fetch_message_ids(self, search, date_filter):
        query = """query ($search: bytea, $date_filter: timestamp) {
          q0: message_view(where: {_and: [{sender: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
          q1: message_view(where: {_and: [{recipient: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
          q2: message_view(where: {_and: [{origin_tx_sender: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
          q3: message_view(where: {_and: [{destination_tx_sender: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
          q4: message_view(where: {_and: [{msg_id: {_eq: $search}}, {delivery_occurred_at: {_gt: $date_filter}}]}, order_by: {delivery_occurred_at: desc}, limit: 100) { msg_id }
        }"""
        variables = {"search": search, "date_filter": date_filter}
        payload = {"query": query, "variables": variables}
        response = await self._requests_client.post(self.GRAPHQL_URL, json=payload)
        data = response["data"]
        msg_ids = set()
        for key in data:
            for msg in data[key]:
                msg_ids.add(msg["msg_id"])
        self._logger.info(f"Найдено {len(msg_ids)} сообщений.")
        return list(msg_ids)


    async def fetch_total_payment(self, msg_id):
        query = """query ($identifier: bytea!) {
          message_view(where: {msg_id: {_eq: $identifier}}, limit: 1) {
            msg_id
            total_payment
            delivery_occurred_at
          }
        }"""
        payload = {"query": query, "variables": {"identifier": msg_id}}
        response = await self._requests_client.post(self.GRAPHQL_URL, json=payload)
        data = response["data"]["message_view"]
        if data and data[0]["total_payment"]:
            # self._logger.info(f"Сумма: {int(data[0]['total_payment'])} wei")
            return int(data[0]["total_payment"])
        else:
            self._logger.info(f"Нет данных.")
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

#
# def run_processing(date_filter, all_time, address_file, proxy_file, log_widget, progress_var, progress_label,
#                    num_threads):
#     def logger(msg):
#         log_widget.insert("end", msg + "\n")
#         log_widget.see("end")
#
#     try:
#         with open(address_file, "r") as a, open(proxy_file, "r") as p:
#             addresses = [line.strip() for line in a if line.strip()]
#             proxies = [line.strip() for line in p if line.strip()]
#         if len(proxies) < len(addresses):
#             logger("Ошибка: прокси меньше, чем адресов.")
#             return
#
#         eth_usd_price = get_eth_usd_price()
#         logger(f"Курс ETH/USD: {eth_usd_price}")
#
#         results = [None] * len(addresses)
#
#         def process_index(i):
#             address = addresses[i]
#             logger(f"\n=== Кошелек: {address} ===")
#             try:
#                 df = "2000-01-01T00:00:00" if all_time else date_filter
#                 total_igp, msg_count = process_wallet(address, proxies, df, logger)
#                 igp_eth = total_igp / 1e18
#                 igp_usd = igp_eth * eth_usd_price
#                 results[i] = [address, round(igp_eth, 8), round(igp_usd, 2), msg_count]
#             except Exception as e:
#                 logger(f"  Ошибка: {e}")
#                 results[i] = [address, "ERROR", "ERROR", "ERROR"]
#             done = sum(r is not None for r in results)
#             progress = int((done / len(addresses)) * 100)
#             progress_var.set(progress)
#             progress_label.config(text=f"{progress}%")
#
#         with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
#             executor.map(process_index, range(len(addresses)))
#
#         wb = Workbook()
#         ws = wb.active
#         ws.title = "Interchain Gas Payments"
#         ws.append(["wallet", "ETH", "USD", "Messages"])
#         for row in results:
#             ws.append(row)
#         wb.save("interchain_gas_payments.xlsx")
#         logger("\n✅ Готово! Сохранено в interchain_gas_payments.xlsx")
#
#     except Exception as e:
#         logger(f"Ошибка запуска: {e}")
#
#
# def launch_gui():
#     root = Tk()
#     root.title("Hyperlane Gas Tracker")
#     root.geometry("800x600")
#
#     image_path = os.path.join(os.getcwd(), "photo.jpg")
#     bg_image = Image.open(image_path).resize((800, 600))
#     bg_photo = ImageTk.PhotoImage(bg_image)
#
#     canvas = Canvas(root, width=800, height=600)
#     canvas.pack(fill="both", expand=True)
#     canvas.create_image(0, 0, image=bg_photo, anchor="nw")
#
#     font_title = ("Arial", 22, "bold")
#     font_label = ("Arial", 12, "bold")
#     font_button = ("Arial", 10)
#
#     canvas.create_text(400, 30, text="Hyperlane Gas Tracker", font=font_title, fill="white")
#
#     canvas.create_text(180, 80, text="Дата фильтрации:", fill="white", font=font_label)
#     date_picker = DateEntry(root, width=12, background="darkblue", foreground="white",
#                             borderwidth=2, font=("Arial", 12), date_pattern='yyyy-mm-dd')
#     date_picker.set_date("2025-07-02")
#     canvas.create_window(400, 80, window=date_picker)
#
#     all_time_var = IntVar()
#     all_time_check = Checkbutton(root, text="За всё время", variable=all_time_var,
#                                  font=("Arial", 12), bg="#000000", fg="white", selectcolor="black")
#     canvas.create_window(400, 120, window=all_time_check)
#
#     address_path = StringVar()
#     proxy_path = StringVar()
#
#     canvas.create_text(180, 145, text="Файл с адресами:", fill="white", font=font_label)
#     address_label = Label(root, text="Файл не выбран", font=("Arial", 10), bg="#000000", fg="white")
#     canvas.create_window(400, 160, window=address_label)
#     Button(root, text="Выбрать файл", command=lambda: choose_file(address_path, address_label),
#            font=font_button).place(x=550, y=150)
#
#     canvas.create_text(180, 185, text="Файл с прокси:", fill="white", font=font_label)
#     proxy_label = Label(root, text="Файл не выбран", font=("Arial", 10), bg="#000000", fg="white")
#     canvas.create_window(400, 200, window=proxy_label)
#     Button(root, text="Выбрать файл", command=lambda: choose_file(proxy_path, proxy_label),
#            font=font_button).place(x=550, y=190)
#
#     canvas.create_text(180, 280, text="Потоки:", fill="white", font=font_label)
#     threads_var = StringVar(value="8")
#     threads_entry = Entry(root, textvariable=threads_var, width=5, font=("Arial", 12))
#     canvas.create_window(400, 280, window=threads_entry)
#
#     progress_var = IntVar()
#     progress = Progressbar(root, orient="horizontal", length=300, mode="determinate", variable=progress_var)
#     canvas.create_window(400, 320, window=progress)
#
#     progress_label = Label(root, text="0%", font=("Arial", 10, "bold"), fg="black", bg=root["bg"], bd=0,
#                            highlightthickness=0)
#     canvas.create_window(400, 320, window=progress_label)
#
#     log_widget = Text(root, width=90, height=15, font=("Courier", 10))
#     canvas.create_window(400, 500, window=log_widget)
#
#     def choose_file(var, label_widget):
#         path = filedialog.askopenfilename()
#         var.set(path)
#         label_widget.config(text=os.path.basename(path) if path else "Файл не выбран")
#
#     def start():
#         try:
#             num_threads = max(1, int(threads_var.get()))
#         except:
#             num_threads = 8
#         print("Запуск с потоками:", num_threads)
#         print("Адреса:", address_path.get())
#         print("Прокси:", proxy_path.get())
#         progress_label.config(text="0%")
#         threading.Thread(target=run_processing, args=(
#             date_picker.get() + "T00:00:00",
#             all_time_var.get(),
#             address_path.get(),
#             proxy_path.get(),
#             log_widget,
#             progress_var,
#             progress_label,
#             num_threads
#         ), daemon=True).start()
#
#     Button(root, text="🚀 Запустить обработку", command=start,
#            font=("Arial", 12, "bold"), bg="#222", fg="white").place(x=320, y=340)
#
#     root.mainloop()
#
#
# if __name__ == "__main__":
#     launch_gui()