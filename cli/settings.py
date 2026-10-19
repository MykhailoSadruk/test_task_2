import sys
from typing import Self

from pydantic import AliasChoices, AnyHttpUrl, BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class PayloadInput(BaseModel):
    list_1: list[str]
    list_2: list[str]


class CliSettings(BaseSettings):
    model_config = SettingsConfigDict(
        cli_parse_args=True, cli_prog_name="cache-cli", case_sensitive=True
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)

    host: AnyHttpUrl = Field(
        AnyHttpUrl("http://localhost:8000"),
        validation_alias=AliasChoices("H", "host"),
        description="server URL",
    )
    repeat: int = Field(
        1,
        ge=1,
        validation_alias=AliasChoices("r", "repeat"),
        description="number of iterations",
    )
    timeout: float = Field(
        600.0,
        gt=0,
        validation_alias=AliasChoices("t", "timeout"),
        description="request timeout in seconds",
    )
    input: str | None = Field(
        None,
        validation_alias=AliasChoices("i", "input"),
        description="JSON input file, '-' for stdin",
    )
    json_: str | None = Field(
        None,
        validation_alias=AliasChoices("j", "json"),
        description="inline JSON input",
    )
    output: str = Field(
        "-",
        validation_alias=AliasChoices("o", "output"),
        description="output file, '-' for stdout",
    )

    @model_validator(mode="after")
    def exactly_one_input_source(self) -> Self:
        if (self.input is None) == (self.json_ is None):
            raise ValueError("exactly one of --input and --json is required")
        return self

    def load_payload(self) -> PayloadInput:
        return PayloadInput.model_validate_json(self.read_raw_json())

    def read_raw_json(self) -> str:
        if self.json_ is not None:
            return self.json_
        if self.input == "-":
            return sys.stdin.read()
        assert self.input is not None
        with open(self.input, encoding="utf-8") as file:
            return file.read()
