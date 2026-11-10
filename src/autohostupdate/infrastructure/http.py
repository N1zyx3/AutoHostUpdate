"""HTTP-клиент источника: httpx с retry/backoff, ETag и ограничением размера."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from autohostupdate.errors import SourceUnavailableError

DEFAULT_URL = "https://geohide.ru/eu/hosts"
DEFAULT_MAX_BYTES = 2048 * 1024


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Результат загрузки источника."""

    text: str
    etag: str | None = None
    not_modified: bool = False
    status_code: int = 200


class HttpSourceClient:
    """Загружает текст источника. Экземпляр переиспользует соединения."""

    def __init__(
        self,
        *,
        url: str = DEFAULT_URL,
        timeout: float = 60.0,
        retries: int = 2,
        max_bytes: int = DEFAULT_MAX_BYTES,
        verify_tls: bool = True,
        proxy: str | None = None,
        user_agent: str = "AutoHostUpdate",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.retries = max(0, retries)
        self.max_bytes = max_bytes
        self.verify_tls = verify_tls
        self.proxy = proxy
        self.user_agent = user_agent
        self._transport = transport

    async def fetch(self, *, etag: str | None = None) -> FetchResult:
        headers = {"User-Agent": self.user_agent}
        if etag:
            headers["If-None-Match"] = etag

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    verify=self.verify_tls,
                    proxy=self.proxy,
                    transport=self._transport,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(self.url, headers=headers)
                    if response.status_code == 304:
                        return FetchResult(text="", etag=etag, not_modified=True, status_code=304)
                    response.raise_for_status()
                    data = response.content
                    if len(data) > self.max_bytes:
                        raise SourceUnavailableError(
                            f"Ответ источника больше {self.max_bytes} байт."
                        )
                    from autohostupdate.core.source import decode_source

                    return FetchResult(
                        text=decode_source(data),
                        etag=response.headers.get("ETag"),
                        status_code=response.status_code,
                    )
            except (httpx.HTTPError, SourceUnavailableError) as exc:
                last_error = exc
                if attempt < self.retries:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise SourceUnavailableError(f"Источник недоступен ({self.url}): {last_error}")


def default_client(**kwargs: object) -> HttpSourceClient:
    return HttpSourceClient(**kwargs)  # type: ignore[arg-type]
