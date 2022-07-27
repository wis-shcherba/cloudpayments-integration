import asyncio

from aiohttp import TCPConnector

from base import AbstractInteractionClient, InteractionResponseError
from schemas import ChargeRequestSchema


class CloudPaymentsInteractionClient(AbstractInteractionClient):
    BASE_URL = 'https://api.cloudpayments.ru/payments/cards/'
    CHARGE_PATH = 'charge'
    CONNECTOR = TCPConnector()
    SERVICE = 'Cloud Payments'

    def __init__(self, auth_token: str) -> None:
        self.auth_token: str = auth_token
        super().__init__()

    async def charge(self, request_data: dict) -> dict:
        self.validate_data(data=request_data, schema=ChargeRequestSchema)
        url = self.get_endpoint_url(relative_url=self.CHARGE_PATH)
        headers = self._prepare_common_headers()
        response = await self.post(url=url, data=request_data, headers=headers)
        response_json = await response.json()
        if not response_json.get('Success'):
            err_message = f'{response_json.get("Message")}'
            # If ReasonCode presented in response, add it to error message.
            if reason_code := response_json.get('Model', {}).get('ReasonCode'):
                err_message += f' ReasonCode: {reason_code}'

            raise InteractionResponseError(
                status_code=response.status,
                service='cloudpayments',
                method='POST',
                message=err_message
            )

        return response_json

    def _prepare_common_headers(self) -> dict:
        """
        Add X-Request-ID and Auth headers.
        """
        return self._get_x_request_id_header() | self._get_auth_header(auth_token=self.auth_token)


async def main():  # type: ignore
    return await CloudPaymentsInteractionClient(auth_token='123').charge(
        {'Amount': 10, 'CardCryptogramPacket': 'hello'}
    )


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())  # type: ignore
