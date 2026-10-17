import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from homestarter.core import CoreClient, CoreError
from homestarter.settings import Secret


@pytest.mark.parametrize(
    "status,mime,content,accepted",
    [(200, "image/jpeg", b"\xff\xd8\xff" + b"fixture", True), (200, "text/html", b"login", False), (503, "image/jpeg", b"\xff\xd8\xff", False)],
)
async def test_native_snapshot_check_is_bounded_and_rejects_login_or_error_pages(status, mime, content, accepted):
    async def picture(request):
        assert request.headers["Authorization"] == "Bearer example-test-token"
        return web.Response(status=status, content_type=mime, body=content)

    app = web.Application()
    app.router.add_get("/api/camera_proxy/camera.fixture", picture)
    async with TestServer(app) as server, aiohttp.ClientSession() as connection:
        core = CoreClient(connection, str(server.make_url("/api")), "ws://example.invalid", Secret("example-test-token"))
        if accepted:
            await core.check_camera("camera.fixture")
        else:
            with pytest.raises(CoreError):
                await core.check_camera("camera.fixture")
        with pytest.raises(ValueError):
            await core.check_camera("https://example.com")
