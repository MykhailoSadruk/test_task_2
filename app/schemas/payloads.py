from typing import Self

from pydantic import BaseModel, model_validator


class PayloadCreateRequest(BaseModel):
    list_1: list[str]
    list_2: list[str]

    @model_validator(mode="after")
    def lists_have_equal_length(self) -> Self:
        if len(self.list_1) != len(self.list_2):
            raise ValueError("list_1 and list_2 must have the same length")
        return self


class PayloadCreateResponse(BaseModel):
    id: str
    message: str


class PayloadResponse(BaseModel):
    output: str
