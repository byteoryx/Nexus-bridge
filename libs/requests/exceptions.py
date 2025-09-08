from curl_cffi.requests import Response
from curl_cffi.requests.exceptions import ProxyError, SSLError, Timeout, ConnectionError
from aiohttp.client_exceptions import ClientHttpProxyError, ClientProxyConnectionError, ClientConnectorDNSError

class APIException(Exception):
    pass

class HTTPException(Exception):
    """
    An exception that occurs when an HTTP request is unsuccessful.

    Attributes:
        response (Optional[Dict[str, Any]]): a JSON response to a request.
        status_code (Optional[int]): a request status code.

    """
    response: dict[str, ...] | None
    status_code: int | None

    def __init__(self, response: dict[str, ...] | None = None, status_code: int | None = None) -> None:
        """
        Initialize the class.

        Args:
            response (Optional[Dict[str, Any]]): a JSON response to a request. (None)
            status_code (Optional[int]): a request status code. (None)

        """
        self.response = response
        self.status_code = status_code


class CustomRequestException(Exception):
    def __init__(self, response: Response) -> None:
        """
        Инициализация класса исключения для HTTP-запросов.

        Args:
            response (Response): объект ответа на запрос
        """
        self.response = response
        self.status_code = response.status_code
        self.text = response.text
        self.error_message: list | dict | str | None = None

        # Вызов базового конструктора Exception с информативным сообщением
        super().__init__(self._get_error_message())

    def _get_error_message(self) -> str:
        """
        Формирует детальное сообщение об ошибке.

        Returns:
            str: Информативное сообщение об ошибке
        """
        try:
            self.error_message = self.response.json()

        except Exception:
            # Если не удалось распарсить JSON или получить детальную информацию
            self.error_message = self.text[:200] + "..." if len(self.text) > 200 else self.text

        # Формирование полного сообщения с кодом статуса и URL
        full_message = (
            f"HTTP error [{self.status_code}]: {str(self.error_message).replace(", ", ",").replace(" : ", ":")}\n"
            f"URL: {self.response.url}\n"
        )

        return full_message

    def __str__(self) -> str:
        """
        Возвращает строковое представление исключения.

        Returns:
            str: Информативное сообщение об исключении
        """
        return self._get_error_message()

    def __repr__(self) -> str:
        """
        Возвращает представление исключения для отладки.

        Returns:
            str: Техническое представление исключения
        """
        return f"CustomRequestException(status_code={self.status_code}, url={self.response.url})"


EXTERNAL_REQUEST_EXCEPTIONS = (ProxyError, Timeout, SSLError, ConnectionError,  # curl_cffi
                        ClientHttpProxyError, ClientProxyConnectionError, ClientConnectorDNSError, # aiohttp
                        TimeoutError) # webshare proxy
