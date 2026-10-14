"""Entry point: ``python3 -m homestarter``."""

import logging

from aiohttp import web

from . import __version__
from .privacy import PrivacyFilter
from .server import create_app
from .settings import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # aiohttp's access log would record full request lines; keep it quiet.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    settings = Settings.from_env()
    for handler in logging.getLogger().handlers:
        handler.addFilter(PrivacyFilter((settings.token.reveal(),)))
    logging.getLogger("homestarter").info(
        "Home Starter %s listening on %s:%s (Supervisor token %s)",
        __version__,
        settings.host,
        settings.port,
        "present" if settings.token else "MISSING",
    )
    web.run_app(create_app(settings), host=settings.host, port=settings.port, print=None, access_log=None)


if __name__ == "__main__":
    main()
