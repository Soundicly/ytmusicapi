import json
import time
import webbrowser
from typing import Dict, Optional

import aiohttp
from case_insensitive_dict import CaseInsensitiveDict

from ytmusicapi.constants import (OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_CODE_URL,
                                  OAUTH_SCOPE, OAUTH_TOKEN_URL, OAUTH_USER_AGENT)
from ytmusicapi.helpers import initialize_headers


def is_oauth(headers: CaseInsensitiveDict) -> bool:
    oauth_structure = {
        "access_token",
        "expires_at",
        "expires_in",
        "token_type",
        "refresh_token",
    }
    return all(key in headers for key in oauth_structure)


def is_custom_oauth(headers: CaseInsensitiveDict) -> bool:
    """Checks whether the headers contain a Bearer token, indicating a custom OAuth implementation."""
    return "authorization" in headers and headers["authorization"].startswith("Bearer ")


class YTMusicOAuth:
    """OAuth implementation for YouTube Music based on YouTube TV"""

    def __init__(self, session: aiohttp.ClientSession, proxy: str = None):
        self._session = session
        if proxy:
            self._session.proxy.update(proxy)

    async def _send_request(self, url, data) -> aiohttp.ClientResponse:
        data.update({"client_id": OAUTH_CLIENT_ID})
        headers = {"User-Agent": OAUTH_USER_AGENT}
        return await self._session.post(url, data=data, headers=headers)

    async def get_code(self) -> Dict:
        code_response = await self._send_request(OAUTH_CODE_URL, data={"scope": OAUTH_SCOPE})
        response_json = code_response.json()
        return response_json

    @staticmethod
    async def _parse_token(response) -> Dict:
        token = await response.json()
        token["expires_at"] = int(time.time()) + int(token["expires_in"])
        return token

    async def get_token_from_code(self, device_code: str) -> Dict:
        response = await self._send_request(
            OAUTH_TOKEN_URL,
            data={
                "client_secret": OAUTH_CLIENT_SECRET,
                "grant_type": "http://oauth.net/grant_type/device/1.0",
                "code": device_code,
            },
        )
        return await self._parse_token(response)

    async def refresh_token(self, refresh_token: str) -> Dict:
        response = await self._send_request(
            OAUTH_TOKEN_URL,
            data={
                "client_secret": OAUTH_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        return await self._parse_token(response)

    @staticmethod
    def dump_token(token: Dict, filepath: Optional[str]):
        if not filepath or len(filepath) > 255:
            return
        with open(filepath, encoding="utf8", mode="w") as file:
            json.dump(token, file, indent=True)

    async def setup(self, filepath: Optional[str] = None, open_browser: bool = False) -> Dict:
        code = await self.get_code()
        url = f"{code['verification_url']}?user_code={code['user_code']}"
        if open_browser:
            webbrowser.open(url)
        input(f"Go to {url}, finish the login flow and press Enter when done, Ctrl-C to abort")
        token = self.get_token_from_code(code["device_code"])
        self.dump_token(token, filepath)

        return token

    async def load_headers(self, token: Dict, filepath: Optional[str] = None):
        headers = initialize_headers()
        if time.time() > token["expires_at"] - 3600:
            token.update(await self.refresh_token(token["refresh_token"]))
            self.dump_token(token, filepath)
        headers["Authorization"] = f"{token['token_type']} {token['access_token']}"
        headers["Content-Type"] = "application/json"
        headers["X-Goog-Request-Time"] = str(int(time.time()))
        return headers
