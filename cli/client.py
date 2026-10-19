import httpx
from pydantic import BaseModel, ValidationError

from cli.settings import PayloadInput


class PayloadClientError(Exception):
    pass


class CreatedPayload(BaseModel):
    id: str


class PayloadOutput(BaseModel):
    output: str


class PayloadClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def create(self, payload: PayloadInput) -> str:
        response = self._send("POST", "/payload", json=payload.model_dump())
        return self._parse(CreatedPayload, response).id

    def get_output(self, payload_id: str) -> PayloadOutput:
        response = self._send("GET", f"/payload/{payload_id}")
        return self._parse(PayloadOutput, response)

    def _send(
        self, method: str, path: str, json: dict[str, list[str]] | None = None
    ) -> httpx.Response:
        try:
            response = self._http.request(method, path, json=json)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise PayloadClientError(
                f"{method} {path} failed with status {error.response.status_code}"
                f"{self._reason(error.response)}"
            ) from error
        except httpx.HTTPError as error:
            raise PayloadClientError(f"cannot reach server: {error}") from error
        return response

    @staticmethod
    def _reason(response: httpx.Response) -> str:
        try:
            detail = response.json()["detail"]
        except (ValueError, KeyError, TypeError):
            return ""
        if isinstance(detail, list) and detail:
            detail = detail[0].get("msg") if isinstance(detail[0], dict) else None
        return f": {detail}" if isinstance(detail, str) and detail else ""

    def _parse[T: BaseModel](self, model: type[T], response: httpx.Response) -> T:
        try:
            return model.model_validate_json(response.content)
        except ValidationError as error:
            raise PayloadClientError("unexpected response from server") from error
