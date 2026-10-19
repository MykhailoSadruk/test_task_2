import uvicorn

from app.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "app.main:get_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
    )


if __name__ == "__main__":
    main()
