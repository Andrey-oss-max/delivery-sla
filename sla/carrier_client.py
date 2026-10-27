"""Клиент HTTP-выгрузки службы доставки: забирает реестр доставок по адресу. Обёртка над requests."""
import time

import requests


class CarrierError(Exception):
    pass


class CarrierClient:
    def __init__(self, base_url, session=None, timeout=5, retries=3, pause=1.0, sleep=time.sleep):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout, self.retries = timeout, retries
        self.pause, self.sleep = pause, sleep

    def registry(self, name: str) -> str:
        """Текст реестра доставок (CSV). Повторы с нарастающей паузой, затем CarrierError."""
        url = f"{self.base_url}/{name.lstrip('/')}"
        last = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if 400 <= resp.status_code < 500:
                    # ошибка запроса не исправится повтором
                    raise CarrierError(f"{url}: HTTP {resp.status_code}")
                resp.raise_for_status()
                resp.encoding = "utf-8"
                return resp.text
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                last = exc
                if attempt < self.retries:
                    self.sleep(self.pause * attempt)
        raise CarrierError(f"служба доставки не ответила после {self.retries} попыток: {last}")
