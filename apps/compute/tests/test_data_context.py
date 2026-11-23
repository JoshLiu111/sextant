"""ctx carries the signed-in user, so user-keyed data is cached per user only."""

from data_fixtures import FixtureAdapter, price_frame, serving
from sextant_compute.data.cache import InMemoryCache
from sextant_compute.envelope import DataSource
from tests.auth_helpers import bearer, sign_in

BODY = {"tickers": ["AAA"], "benchmark": "AAA", "start": "2024-01-01", "end": "2024-12-31"}
USER_KEYED = DataSource(id="tiingo", name="Tiingo", is_demo=False)


def test_user_keyed_data_is_never_served_to_another_user_or_anonymous_visitor(client):
    adapter = FixtureAdapter({"AAA": price_frame("2024-01-01", [10.0, 11.0, 10.5])}, source=USER_KEYED, scope="user")
    alice = bearer(sign_in(client, "sub-alice", email="alice@example.test"))
    bob = bearer(sign_in(client, "sub-bob", email="bob@example.test"))

    with serving(adapter, on=client.app, user_cache=InMemoryCache()) as service:
        for headers in (alice, alice):
            assert client.post("/api/compute/risk/metrics", json=BODY, headers=headers).status_code == 200
        assert adapter.calls == 1  # Alice's repeat is served from her own cache

        assert client.post("/api/compute/risk/metrics", json=BODY, headers=bob).status_code == 200
        assert client.post("/api/compute/risk/metrics", json=BODY).status_code == 200
        assert adapter.calls == 3  # neither Bob nor an anonymous visitor hits Alice's entry
        assert len(service.shared_cache) == 0
