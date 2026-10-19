from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

MAX_LIST_ITEMS = 10_000
MAX_STRING_LENGTH = 1_000

Text = Annotated[str, StringConstraints(max_length=MAX_STRING_LENGTH)]
TextList = Annotated[list[Text], Field(max_length=MAX_LIST_ITEMS)]


class PayloadCreateRequest(BaseModel):
    list_1: TextList
    list_2: TextList

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
