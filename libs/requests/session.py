import re
from datetime import datetime
import time
from http.cookiejar import Cookie, CookieJar

from curl_cffi.requests import AsyncSession, BrowserType
import ua_generator
from ua_generator.data.version import Version
from ua_generator.options import Options, VersionRange

from core.db_utils.models import Account
from core.init_settings import settings


def get_ua_parameters():
    options = Options(version_ranges={
        "chrome": VersionRange(min_version=Version(132), max_version=Version(133)),
        "macos": VersionRange(min_version=Version(14), max_version=Version(15)),
        "windows": VersionRange(min_version=Version(10), max_version=Version(11)),
    })
    while True:
        ua = ua_generator.generate(device='desktop', platform=('windows', 'macos'), browser='chrome', options=options)
        ua = ua.text
        if 'Windows' in ua:
            if "WOW64" in ua:
                continue
            os_ua = "Windows"
        elif 'Macintosh' in ua:
            os_ua = "Macintosh"
        else:
            continue
        chrome_version = get_full_chrome_version(ua).split('.')[0]
        return ua, os_ua, chrome_version

def get_full_chrome_version(user_agent: str):
    if re.search(r'Chrome/([\d.]+)', user_agent):
        return re.search(r'Chrome/([\d.]+)', user_agent).group(1)

def get_os_version(user_agent: str):
    # like "10" from Windows 10.0 or "15" from Intel Mac OS X 15_2
    if "Windows" in user_agent:
        return re.search(r'Windows NT \d{2}', user_agent).group(0).split()[-1]
    elif "Macintosh" in user_agent:
        return re.search(r'Mac OS X \d{2}', user_agent).group(0).split()[-1]
    else:
        return str(10)


class BaseAsyncSession(AsyncSession):
    def __init__(
            self,
            account: Account,
            proxy: str | None = None,
            cookies: CookieJar | None = None,
            # *,
            # impersonate: BrowserType = BrowserType.chrome131,
            **session_kwargs,
    ):
        self._proxy = proxy
        if proxy:
            proxies = {"http": proxy, "https": proxy}
        else:
            proxies = {"http": account.proxy, "https": account.proxy}
        headers = session_kwargs.pop("headers", {})
        headers["user-agent"] = account.user_agent
        import_cookies = cookies or CookieJar()

        super().__init__(
            proxies=proxies,
            headers=headers,
            cookies=import_cookies,
            timeout=settings.general.timeout,
            # impersonate=impersonate,
            # cookiejar=True,
            **session_kwargs,
        )

    @property
    def user_agent(self) -> str:
        return self.headers["user-agent"]

    @property
    def proxy(self) -> str:
        return self._proxy

    def set_cookie(self, name: str, value: str, domain: str, secure: bool, expires: int | None = None):
        if not expires:
            # Get current datetime
            current_date = datetime.now()

            # Add 13 months
            # Since there's no direct "add months" method, we need to calculate the year and month
            future_year = current_date.year + ((current_date.month + 13 - 1) // 12)
            future_month = ((current_date.month + 13 - 1) % 12) + 1
            # future_date = datetime(future_year, future_month, current_date.day)

            # If the original day doesn't exist in the target month (e.g., Jan 31 -> Feb 28)
            # adjusting to the last day of the month
            while True:
                try:
                    future_date = datetime(future_year, future_month, current_date.day)
                    break
                except ValueError:
                    current_date = current_date.replace(day=current_date.day - 1)

            # Convert to Unix timestamp (seconds since the epoch)
            future_timestamp_seconds = int(time.mktime(future_date.timetuple()))

            # For milliseconds timestamp (common in JavaScript and some APIs)
            future_timestamp_milliseconds = future_timestamp_seconds * 1000

            expires = future_timestamp_seconds

        cookie = Cookie(
            name=name, value=value, domain=domain, domain_specified=True, domain_initial_dot=False, path='/',
            path_specified=True, secure=secure, expires=expires, version=None, port=None, comment=None, comment_url=None,
            rest={'':''}, port_specified=False, discard=False
        )

        self.cookies.jar.set_cookie(cookie)

