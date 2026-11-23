"""Operator view of users (issue #51): registered users, sign-ups per UTC day, recent sign-ins.

Operator-only like the AI usage view; everyone else gets a 404.
"""

from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient

from tests.auth_helpers import bearer, sign_in
from tests.test_operator_ai_usage import OPERATOR, operator, user_id, utc_day  # noqa: F401  (operator is a fixture)

USERS = "/api/compute/operator/users"


def backdate(db_url: str, uid: str, *, created_days_ago: int, last_login_days_ago: int) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "UPDATE users SET created_at = now() - make_interval(days => %s),"
            " last_login_at = now() - make_interval(days => %s) WHERE id = %s",
            (created_days_ago, last_login_days_ago, uid),
        )


def new_user(client: TestClient, db_url: str, label: str, *, created_days_ago: int, last_login_days_ago: int) -> None:
    token = sign_in(client, f"google-sub-{label}", email=f"{label}@example.test", name=label)
    backdate(db_url, user_id(client, token), created_days_ago=created_days_ago, last_login_days_ago=last_login_days_ago)


def test_visitors_and_non_operators_get_a_404(client, monkeypatch):
    monkeypatch.setenv("OPERATOR_EMAILS", OPERATOR)
    alice = sign_in(client)

    for headers in ({}, bearer(alice)):
        response = client.get(USERS, headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_counts_registered_users_sign_ups_per_day_and_recent_sign_ins(client, operator, db_url):  # noqa: F811
    # The operator signed up and signed in today.
    new_user(client, db_url, "today", created_days_ago=0, last_login_days_ago=0)
    new_user(client, db_url, "yesterday-a", created_days_ago=1, last_login_days_ago=3)
    new_user(client, db_url, "yesterday-b", created_days_ago=1, last_login_days_ago=10)
    new_user(client, db_url, "old", created_days_ago=60, last_login_days_ago=20)
    new_user(client, db_url, "dormant", created_days_ago=90, last_login_days_ago=45)

    body = client.get(USERS, params={"days": 3}, headers=bearer(operator)).json()

    assert body["total_users"] == 6
    assert (body["since"], body["until"]) == (utc_day(2), utc_day(0))
    # Every UTC day in the window, newest first, days without sign-ups included.
    assert body["sign_ups"] == [
        {"day": utc_day(0), "users": 2},
        {"day": utc_day(1), "users": 2},
        {"day": utc_day(2), "users": 0},
    ]
    assert body["signed_in_within"] == [{"days": 7, "users": 3}, {"days": 30, "users": 5}]


def test_the_default_window_is_the_last_30_utc_days(client, operator, db_url):  # noqa: F811
    new_user(client, db_url, "edge", created_days_ago=29, last_login_days_ago=29)
    new_user(client, db_url, "outside", created_days_ago=31, last_login_days_ago=31)

    body = client.get(USERS, headers=bearer(operator)).json()

    assert (body["since"], body["until"]) == (utc_day(29), utc_day(0))
    assert len(body["sign_ups"]) == 30
    assert body["sign_ups"][-1] == {"day": utc_day(29), "users": 1}
    assert sum(d["users"] for d in body["sign_ups"]) == 2  # the operator today, plus "edge"
    assert body["total_users"] == 3
    assert client.get(USERS, params={"days": 0}, headers=bearer(operator)).status_code == 422
