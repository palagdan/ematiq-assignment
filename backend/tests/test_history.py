import httpx

from tests.conftest import ClientFactory


async def play_and_give_up(host: httpx.AsyncClient, guest: httpx.AsyncClient) -> str:
    code: str = (await host.post("/api/rooms")).json()["code"]
    await guest.post(f"/api/rooms/{code}/join")
    for client in (host, guest):
        await client.put(f"/api/rooms/{code}/meal", json={"amount": "100", "currency": "CZK"})
    await host.post(f"/api/rooms/{code}/start")
    await host.post(f"/api/rooms/{code}/give-up")
    return code


async def test_history_filters_and_pages(make_user: ClientFactory) -> None:
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    first = await play_and_give_up(alice, bob)
    second = await play_and_give_up(bob, carol)
    third = await play_and_give_up(carol, alice)

    everything = (await alice.get("/api/history")).json()
    assert [e["code"] for e in everything["items"]] == [third, second, first]

    mine = (await alice.get("/api/history", params={"mine": True})).json()
    assert [e["code"] for e in mine["items"]] == [third, first]

    page = (await alice.get("/api/history", params={"limit": 2})).json()
    assert page["has_more"] is True and len(page["items"]) == 2
    rest = (await alice.get("/api/history", params={"limit": 2, "offset": 2})).json()
    assert rest["has_more"] is False and [e["code"] for e in rest["items"]] == [first]

    entry = everything["items"][0]
    assert entry["loser_username"] == "carol"
    assert entry["totals"]["CZK"] == "200.00"
