import httpx
from httpx_ws import AsyncWebSocketSession, aconnect_ws
from httpx_ws._exceptions import WebSocketDisconnect
from httpx_ws.transport import ASGIWebSocketTransport

from lunch.main import app
from tests.conftest import BASE_URL, ClientFactory


def socket_client(cookies: httpx.Cookies) -> httpx.AsyncClient:
    # Opened inside the test task: the WS transport's task group must not cross tasks.
    return httpx.AsyncClient(
        transport=ASGIWebSocketTransport(app), base_url=BASE_URL, cookies=cookies
    )


async def test_room_updates_are_pushed(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    bob = await make_user("bob")
    code = (await alice.post("/api/rooms")).json()["code"]

    async with (
        socket_client(alice.cookies) as client,
        aconnect_ws(
            f"{BASE_URL}/ws/rooms/{code}", client, session_class=AsyncWebSocketSession
        ) as ws,
    ):
        initial = await ws.receive_json()
        assert initial["type"] == "room.state"
        assert initial["room"]["version"] == 0

        await bob.post(f"/api/rooms/{code}/join")
        update = await ws.receive_json()
        assert update["room"]["version"] == 1
        assert [p["username"] for p in update["room"]["players"]] == ["alice", "bob"]


async def test_socket_requires_login(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    code = (await alice.post("/api/rooms")).json()["code"]

    async with socket_client(httpx.Cookies()) as client:
        try:
            async with aconnect_ws(f"{BASE_URL}/ws/rooms/{code}", client):
                raise AssertionError("anonymous socket was accepted")
        except* WebSocketDisconnect as group:
            codes = [e.code for e in group.exceptions if isinstance(e, WebSocketDisconnect)]
            assert codes == [4401]


async def test_heartbeat_ping_gets_pong(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    code = (await alice.post("/api/rooms")).json()["code"]
    async with (
        socket_client(alice.cookies) as client,
        aconnect_ws(
            f"{BASE_URL}/ws/rooms/{code}", client, session_class=AsyncWebSocketSession
        ) as ws,
    ):
        assert (await ws.receive_json())["type"] == "room.state"
        await ws.send_text("ping")
        assert await ws.receive_json() == {"type": "pong"}
        await ws.send_text("anything else")  # ignored, connection stays usable
        await ws.send_text("ping")
        assert await ws.receive_json() == {"type": "pong"}
