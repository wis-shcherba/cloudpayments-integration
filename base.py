import asyncio
import random
import time
from itertools import chain
from typing import Any, ClassVar, Optional, Type
from uuid import uuid4

from aiohttp import ClientResponse, ClientSession, ClientTimeout, TCPConnector
from marshmallow import Schema, ValidationError


class BaseInteractionError(Exception):
    default_message = 'Backend interaction error'

    def __init__(self, *, service: str, method: str, message: Optional[str] = None) -> None:
        self.message = message or self.default_message
        self.service = service
        self.method = method

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.service}, {self.method}): {self.message}'


class InteractionResponseError(BaseInteractionError):
    default_message = 'Backend unexpected response'

    def __init__(
            self,
            *,
            status_code: int,
            method: str,
            service: str,
            message: Optional[str] = None,
            response_status: Optional[str] = None,
            params: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        :param status_code: HTTP status code
        :param method: HTTP method
        :param response_status: статус ответа, который обычно приходит в JSON-теле ответа
            в ключе "status", например:
            >>> {"status": "failure", ... }
            >>> {"status": "success", ... }
        :param service: имя сервиса (просто строчка с человекочитаемым названием сервиса, в который делается запрос)
        :param params: какие-то структурированные параметры из тела ответа с ошибкой
        :param message: строка с сообщением об ошибке. в свободной форме
        """
        self.status_code = status_code
        self.response_status = response_status
        self.params = params
        super().__init__(service=service, method=method, message=message)

    def __str__(self) -> str:
        return (f'{self.__class__.__name__}({self.service}.{self.method}): '
                f'status={self.status_code} response_status={self.response_status} '
                f'params={self.params} {self.message}')


class AbstractInteractionClient:
    CONNECTOR: ClassVar[TCPConnector]

    REQUEST_TIMEOUT: ClassVar[Optional[float]] = None
    CONNECT_TIMEOUT: ClassVar[Optional[float]] = None

    SERVICE: ClassVar[str]
    BASE_URL: ClassVar[str]
    REQUEST_RETRY_TIMEOUTS = (0.1, 0.2, 0.4)

    _session: Optional[ClientSession] = None

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        self.default_timeout: Optional[ClientTimeout] = None
        if self.REQUEST_TIMEOUT:
            self.default_timeout = ClientTimeout(total=self.REQUEST_TIMEOUT, connect=self.CONNECT_TIMEOUT)

    def _get_session_cls(self) -> Type[ClientSession]:
        return ClientSession

    def _get_session_kwargs(self) -> dict[str, Any]:
        """Returns kwargs necessary for creating a session instance."""
        assert hasattr(self, 'CONNECTOR'), 'Set "CONNECTOR" field in inherited class.'
        kwargs = {
            'connector': self.CONNECTOR,
            'connector_owner': False,
            'trust_env': True,
        }
        if self.default_timeout:
            kwargs['timeout'] = self.default_timeout
        return kwargs

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            self._session = self.create_session()
        return self._session

    def create_session(self) -> ClientSession:
        session_cls = self._get_session_cls()
        kwargs = self._get_session_kwargs()
        return session_cls(**kwargs)

    def _handle_response_error(self, response: ClientResponse) -> None:
        assert hasattr(self, 'SERVICE'), 'Set "SERVICE" field in inherited class.'
        raise InteractionResponseError(
            status_code=response.status,
            method=response.method,
            service=self.SERVICE,
            params=None,
        )

    def validate_data(self, data: dict, schema: Type[Schema]) -> None:
        try:
            schema().load(data=data)
        except ValidationError as exc:
            self._handle_validation_error(exc)

    @staticmethod
    def _get_x_request_id_header() -> dict:
        return {'X-Request-ID': str(uuid4())}

    @staticmethod
    def _get_auth_header(auth_token: str) -> dict:
        return {'Authentication': auth_token}

    @staticmethod
    def _handle_validation_error(exc: Any) -> None:
        raise ValidationError(message=exc)

    async def _process_response(self, response: ClientResponse) -> ClientResponse:
        if response.status >= 400:
            self._handle_response_error(response)
        return response

    async def _make_request(
            self,
            method: str,
            url: str,
            **kwargs: Any
    ) -> ClientResponse:
        """Wraps ClientSession.request allowing retries, updating metrics."""

        kwargs.setdefault('headers', {})

        response_time = 0.0
        response = exc = None
        for retry_number, retry_delay in enumerate(chain((0.0,), self.REQUEST_RETRY_TIMEOUTS)):
            if retry_delay:
                delay = retry_delay - response_time
                await asyncio.sleep(delay + random.uniform(-delay / 2, delay / 2))

            exc = None
            response = None
            before = time.monotonic()
            try:
                response = await self.session.request(method, url, **kwargs)
            except asyncio.TimeoutError:
                break
            except Exception as e:
                exc = e
            else:
                break
            finally:
                response_time = time.monotonic() - before

        if exc:
            raise exc

        return response  # type: ignore

    async def _request(  # noqa: C901
            self,
            method: str,
            url: str,
            **kwargs: Any,
    ) -> ClientResponse:
        response = await self._make_request(method, url, **kwargs)
        processed = await self._process_response(response)

        return processed

    async def get(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._request('GET', url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._request('POST', url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._request('PUT', url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._request('PATCH', url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._request('DELETE', url, **kwargs)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def get_endpoint_url(self, relative_url: str, base_url_override: Optional[str] = None) -> str:
        base_url = (base_url_override or self.BASE_URL).rstrip('/')
        relative_url = relative_url.lstrip('/')
        return f'{base_url}/{relative_url}'
