"""Minimal illustrative Bale client. Replace logging/error conventions with project conventions."""

import requests


class BaleAPIError(RuntimeError):
    pass


class BaleClient:
    def __init__(self, token: str, base_url: str = "https://tapi.bale.ai", timeout: int = 15):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def call(self, method: str, **params):
        url = f"{self.base_url}/bot{self.token}/{method}"
        response = requests.post(url, json=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise BaleAPIError(data.get("description", "Bale API request failed"))
        return data.get("result")
