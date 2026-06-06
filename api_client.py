import logging
import httpx
from config import WMS_API_URL, MONEY_API_URL, API_USERNAME, API_PASSWORD

logger = logging.getLogger(__name__)

_tokens = {"wms": None, "money": None}


async def _login(base_url: str, system: str) -> str:
    """登入取得 token"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base_url}/api/login",
            json={"username": API_USERNAME, "password": API_PASSWORD},
        )
        resp.raise_for_status()
        token = resp.json()["token"]
        _tokens[system] = token
        logger.info(f"{system} 登入成功")
        return token


async def _request(system: str, method: str, path: str, **kwargs) -> dict | list:
    """帶 token 的 API 請求，token 過期自動重新登入"""
    base_url = WMS_API_URL if system == "wms" else MONEY_API_URL

    for attempt in range(2):
        token = _tokens[system]
        if not token:
            token = await _login(base_url, system)

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(
                method, f"{base_url}{path}", headers=headers, **kwargs
            )

        if resp.status_code == 401 and attempt == 0:
            logger.info(f"{system} token 過期，重新登入")
            _tokens[system] = None
            continue

        resp.raise_for_status()
        return resp.json()

    raise Exception(f"{system} API 請求失敗")


async def wms_get(path: str, **kwargs):
    return await _request("wms", "GET", path, **kwargs)


async def wms_post(path: str, **kwargs):
    return await _request("wms", "POST", path, **kwargs)


async def money_get(path: str, **kwargs):
    return await _request("money", "GET", path, **kwargs)
