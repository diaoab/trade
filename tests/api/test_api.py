"""Tests de l'API du service en ligne (api/), sur une base SQLite en
memoire et un historique synthetique : rien n'est lu ni ecrit dans le vrai
projet."""

import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api import main
from api.config import settings
from api.config.db import get_db
from api.middlewares import rate_limit
from api.models import Base
from api.services import assistant_service, market_service, paydunya, quotes_feed
from core.engine import market_data


V1 = settings.API_PREFIX


@pytest.fixture
def client(tmp_path, monkeypatch):

    rng = np.random.default_rng(0)

    sessions = 150

    pd.DataFrame({
        "Date": pd.bdate_range("2025-01-01", periods=sessions),
        "Close": 1000 + np.cumsum(rng.normal(0, 10, sessions)),
        "Volume": rng.integers(1, 500, sessions)
    }).to_excel(tmp_path / "TEST.xlsx", index=False)

    monkeypatch.setattr(market_data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(market_data, "REGISTRY_PATH", tmp_path / "structures.json")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[get_db] = override

    rate_limit.reset_all()

    monkeypatch.setattr(settings, "WARM_CACHE", False)

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()


def _register(client, email="a@example.com"):

    response = client.post(
        f"{V1}/auth/register",
        json={"email": email, "password": "motdepasse1"}
    )

    assert response.status_code == 201

    return response.json()["data"]


def _signup(client, email="a@example.com"):
    return {"Authorization": f"Bearer {_register(client, email)['token']}"}


def _data(response):

    body = response.json()

    assert body["success"] is True, body

    return body["data"]


# =========================================================
# FORMAT DES REPONSES
# =========================================================

def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "db": "connected"}


def test_errors_share_one_format(client):

    unknown = client.get(f"{V1}/inconnu")

    assert unknown.status_code == 404
    assert unknown.json() == {"success": False, "message": "Route introuvable"}

    invalid = client.post(f"{V1}/auth/register", json={"email": "a@example.com"})

    assert invalid.status_code == 422
    assert invalid.json()["success"] is False
    assert invalid.json()["details"]


def test_security_headers(client):

    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


# =========================================================
# COMPTE ET SESSIONS
# =========================================================

def test_register_login_and_me(client):

    registered = _register(client)

    assert registered["user"]["plan"] == "free"
    assert registered["refresh_token"]

    conflict = client.post(
        f"{V1}/auth/register",
        json={"email": "A@example.com", "password": "motdepasse1"}
    )

    assert conflict.status_code == 409
    assert conflict.json()["message"] == "Un compte existe déjà avec cette adresse."

    assert client.post(
        f"{V1}/auth/login",
        json={"email": "a@example.com", "password": "mauvais"}
    ).status_code == 401

    token = _data(client.post(
        f"{V1}/auth/login",
        json={"email": "a@example.com", "password": "motdepasse1"}
    ))["token"]

    me = client.get(f"{V1}/account/me", headers={"Authorization": f"Bearer {token}"})

    assert _data(me)["plan"] == "free"
    assert "password_hash" not in _data(me)


def test_requires_token(client):

    assert client.get(f"{V1}/market").status_code == 401

    assert client.get(
        f"{V1}/market",
        headers={"Authorization": "Bearer faux"}
    ).status_code == 401


def test_refresh_token_rotates_and_detects_reuse(client):

    first = _register(client)["refresh_token"]

    rotated = client.post(f"{V1}/auth/refresh", json={"refresh_token": first})

    second = _data(rotated)["refresh_token"]

    assert second != first

    assert client.get(
        f"{V1}/account/me",
        headers={"Authorization": f"Bearer {_data(rotated)['token']}"}
    ).status_code == 200

    # Le refresh token ne sert pas de jeton d'acces.
    assert client.get(
        f"{V1}/account/me",
        headers={"Authorization": f"Bearer {second}"}
    ).status_code == 401

    # Ancien jeton presente de nouveau : fuite supposee, toutes les sessions
    # du compte sont fermees, y compris la plus recente.
    assert client.post(f"{V1}/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post(f"{V1}/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_logout_closes_the_session(client):

    refresh_token = _register(client)["refresh_token"]

    assert client.post(f"{V1}/auth/logout", json={"refresh_token": refresh_token}).status_code == 200

    assert client.post(
        f"{V1}/auth/refresh",
        json={"refresh_token": refresh_token}
    ).status_code == 401


def test_change_password_closes_other_sessions(client):

    registered = _register(client)

    headers = {"Authorization": f"Bearer {registered['token']}"}

    assert client.put(
        f"{V1}/auth/password",
        headers=headers,
        json={"current_password": "mauvais", "new_password": "nouveau-mdp"}
    ).status_code == 401

    session = _data(client.put(
        f"{V1}/auth/password",
        headers=headers,
        json={"current_password": "motdepasse1", "new_password": "nouveau-mdp"}
    ))

    assert client.post(
        f"{V1}/auth/refresh",
        json={"refresh_token": registered["refresh_token"]}
    ).status_code == 401

    assert client.post(
        f"{V1}/auth/refresh",
        json={"refresh_token": session["refresh_token"]}
    ).status_code == 200

    assert client.post(
        f"{V1}/auth/login",
        json={"email": "a@example.com", "password": "nouveau-mdp"}
    ).status_code == 200


def test_login_is_rate_limited(client, monkeypatch):

    monkeypatch.setattr(rate_limit.auth_limiter, "max_requests", 2)

    credentials = {"email": "x@example.com", "password": "mauvais-mdp"}

    for _ in range(2):
        assert client.post(f"{V1}/auth/login", json=credentials).status_code == 401

    blocked = client.post(f"{V1}/auth/login", json=credentials)

    assert blocked.status_code == 429
    assert blocked.json()["success"] is False
    assert "Retry-After" in blocked.headers


def test_delete_account(client):

    headers = _signup(client)

    assert client.delete(f"{V1}/account/me", headers=headers).status_code == 200

    assert client.get(f"{V1}/account/me", headers=headers).status_code == 401


def test_preferences(client):

    headers = _signup(client)

    updated = _data(client.put(
        f"{V1}/account/preferences",
        headers=headers,
        json={"selected_parameters": ["RSI"], "round_trip_fee": 1.5}
    ))

    assert updated["selected_parameters"] == ["RSI"]
    assert updated["round_trip_fee"] == 1.5

    assert client.put(
        f"{V1}/account/preferences",
        headers=headers,
        json={"selected_parameters": ["Inconnu"]}
    ).status_code == 422


# =========================================================
# MARCHE, PORTEFEUILLE, ASSISTANT
# =========================================================

def test_market_and_analysis(client):

    headers = _signup(client)

    overview = _data(client.get(f"{V1}/market", headers=headers))

    assert [entry["symbol"] for entry in overview] == ["TEST"]

    assert overview[0]["decision"] in ("ACHETER", "CONSERVER", "VENDRE")

    body = _data(client.get(f"{V1}/structures/TEST/analysis", headers=headers))

    assert body["result"]["decision"] == overview[0]["decision"]

    assert len(body["chart"]["dates"]) == len(body["chart"]["Close"])

    assert client.get(
        f"{V1}/structures/INCONNU/analysis",
        headers=headers
    ).status_code == 404


def test_market_is_revalidated_with_etag(client, tmp_path):

    headers = _signup(client)

    first = client.get(f"{V1}/market", headers=headers)

    etag = first.headers["etag"]

    assert etag.startswith('W/"')

    # Meme version : 304 sans corps.
    again = client.get(f"{V1}/market", headers={**headers, "If-None-Match": etag})

    assert again.status_code == 304
    assert again.content == b""

    analysis = client.get(f"{V1}/structures/TEST/analysis", headers=headers)

    assert client.get(
        f"{V1}/structures/TEST/analysis",
        headers={**headers, "If-None-Match": analysis.headers["etag"]}
    ).status_code == 304

    # D'autres reglages ou de nouveaux cours changent la version.
    client.put(f"{V1}/account/preferences", json={"selected_parameters": ["RSI"]}, headers=headers)

    changed = client.get(f"{V1}/market", headers={**headers, "If-None-Match": etag})

    assert changed.status_code == 200
    assert changed.headers["etag"] != etag

    etag = changed.headers["etag"]

    workbook = tmp_path / "TEST.xlsx"
    workbook.write_bytes(workbook.read_bytes())
    os.utime(workbook, ns=(1, 1))

    assert client.get(f"{V1}/market", headers={**headers, "If-None-Match": etag}).status_code == 200


def test_market_is_computed_once_for_same_settings(client, monkeypatch):

    calls = []

    original = market_service._market_overview

    def counting(preferences):
        calls.append(preferences)
        return original(preferences)

    monkeypatch.setattr(market_service, "_market_overview", counting)

    for email in ("a@example.com", "b@example.com"):
        assert client.get(f"{V1}/market", headers=_signup(client, email)).status_code == 200

    # Deux comptes aux reglages par defaut : un seul calcul.
    assert len(calls) == 1


def test_portfolio_is_private_to_each_user(client):

    alice = _signup(client, "alice@example.com")
    bob = _signup(client, "bob@example.com")

    added = _data(client.post(
        f"{V1}/portfolio/positions",
        headers=alice,
        json={
            "symbol": "TEST",
            "quantity": 10,
            "buy_price": 900,
            "buy_date": "2025-02-03"
        }
    ))

    assert len(added["positions"]) == 1

    assert added["positions"][0]["valuation"]["cost"] == 9000

    assert _data(client.get(f"{V1}/portfolio", headers=bob))["positions"] == []

    position_id = added["positions"][0]["id"]

    assert client.delete(
        f"{V1}/portfolio/positions/{position_id}",
        headers=bob
    ).status_code == 404

    assert _data(client.delete(
        f"{V1}/portfolio/positions/{position_id}",
        headers=alice
    ))["positions"] == []


def test_assistant_quota(client, monkeypatch):

    headers = _signup(client)

    monkeypatch.setattr(
        assistant_service,
        "stream_answer",
        lambda context, history: iter(["Réponse ", "simulée"])
    )

    monkeypatch.setitem(settings.ASSISTANT_DAILY_LIMITS, "free", 1)

    question = {"messages": [{"role": "user", "content": "Pourquoi ?"}]}

    first = _data(client.post(
        f"{V1}/structures/TEST/assistant",
        headers=headers,
        json=question
    ))

    assert first["answer"] == "Réponse simulée"

    assert first["assistant"] == {"used": 1, "limit": 1}

    assert client.post(
        f"{V1}/structures/TEST/assistant",
        headers=headers,
        json=question
    ).status_code == 429


def _events(response):
    """Evenements Server-Sent Events d'une reponse : [(nom, donnees)]."""

    events = []

    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))

    return events


def test_assistant_streams_the_answer(client, monkeypatch):

    headers = _signup(client)

    monkeypatch.setattr(
        assistant_service,
        "stream_answer",
        lambda context, history: iter(["Réponse ", "simulée"])
    )

    monkeypatch.setitem(settings.ASSISTANT_DAILY_LIMITS, "free", 1)

    question = {"messages": [{"role": "user", "content": "Pourquoi ?"}]}

    response = client.post(f"{V1}/structures/TEST/assistant/stream", headers=headers, json=question)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    assert _events(response) == [
        ("delta", {"text": "Réponse "}),
        ("delta", {"text": "simulée"}),
        ("done", {"assistant": {"used": 1, "limit": 1}})
    ]

    # Quota atteint : refuse avant le flux, en JSON.
    refused = client.post(f"{V1}/structures/TEST/assistant/stream", headers=headers, json=question)

    assert refused.status_code == 429
    assert refused.json()["success"] is False


def test_assistant_stream_error_gives_the_question_back(client, monkeypatch):

    from core.engine.assistant_chat import AssistantUnavailable

    headers = _signup(client)

    def failing(context, history):
        yield "Début"
        raise AssistantUnavailable("Service injoignable.")

    monkeypatch.setattr(assistant_service, "stream_answer", failing)

    question = {"messages": [{"role": "user", "content": "Pourquoi ?"}]}

    events = _events(client.post(f"{V1}/structures/TEST/assistant/stream", headers=headers, json=question))

    assert events[-1] == ("error", {"message": "Service injoignable."})

    me = _data(client.get(f"{V1}/account/me", headers=headers))

    assert me["assistant"]["used"] == 0


# =========================================================
# PAIEMENT PAYDUNYA
# =========================================================

@pytest.fixture
def paydunya_sandbox(monkeypatch):
    """PayDunya simule : les factures creees sont payees des que le test
    met leur etat a "completed"."""

    invoices = {}

    def create_invoice(user, client=None):
        token = f"test_{len(invoices) + 1}"
        invoices[token] = {"status": "pending", "amount": 5000, "user_id": user.id}
        return token, f"https://paydunya.com/sandbox-checkout/invoice/{token}"

    monkeypatch.setattr(paydunya, "create_invoice", create_invoice)
    monkeypatch.setattr(paydunya, "confirm_invoice", lambda token, client=None: invoices[token])
    monkeypatch.setattr(paydunya, "configured", lambda: True)
    monkeypatch.setattr(settings, "PAYDUNYA_MASTER_KEY", "cle-test")

    return invoices


def test_payment_extends_pro_once(client, paydunya_sandbox):

    headers = _signup(client)

    token = _data(client.post(
        f"{V1}/billing/checkout",
        headers=headers,
        json={"redirect_url": "finadvisor://settings"}
    ))["token"]

    pending = _data(client.post(f"{V1}/billing/confirm", headers=headers, json={"token": token}))

    assert pending["user"]["plan"] == "free"

    paydunya_sandbox[token]["status"] = "completed"

    returned = client.get(
        f"{V1}/billing/return",
        params={"token": token},
        follow_redirects=False
    )

    assert returned.headers["location"].startswith("finadvisor://settings?billing=completed")

    me = _data(client.get(f"{V1}/account/me", headers=headers))

    assert me["plan"] == "pro"
    assert me["assistant"]["limit"] == settings.ASSISTANT_DAILY_LIMITS["pro"]

    first_until = me["pro_until"]

    # Notification arrivee apres le retour : pas de second mois offert.
    client.post(f"{V1}/billing/confirm", headers=headers, json={"token": token})

    assert _data(client.get(f"{V1}/account/me", headers=headers))["pro_until"] == first_until


def test_checkout_rejects_foreign_redirect(client, paydunya_sandbox):

    headers = _signup(client)

    assert client.post(
        f"{V1}/billing/checkout",
        headers=headers,
        json={"redirect_url": "https://site-pirate.example/"}
    ).status_code == 422


def test_ipn_requires_paydunya_hash(client, paydunya_sandbox):

    headers = _signup(client)

    token = _data(client.post(f"{V1}/billing/checkout", headers=headers, json={}))["token"]

    paydunya_sandbox[token]["status"] = "completed"

    form = {"data[invoice][token]": token, "data[hash]": "faux"}

    assert client.post(f"{V1}/billing/ipn", data=form).status_code == 403

    form["data[hash]"] = hashlib.sha512(b"cle-test").hexdigest()

    assert client.post(f"{V1}/billing/ipn", data=form).status_code == 200

    assert _data(client.get(f"{V1}/account/me", headers=headers))["plan"] == "pro"


def test_confirm_other_users_payment_is_refused(client, paydunya_sandbox):

    alice = _signup(client, "alice@example.com")
    bob = _signup(client, "bob@example.com")

    token = _data(client.post(f"{V1}/billing/checkout", headers=alice, json={}))["token"]

    assert client.post(
        f"{V1}/billing/confirm",
        headers=bob,
        json={"token": token}
    ).status_code == 404


# =========================================================
# ADMINISTRATION ET FLUX DE COURS
# =========================================================

def _admin(client, email="admin@example.com"):
    """Compte promu admin directement en base (comme grant_admin)."""

    headers = _signup(client, email)

    db = next(main.app.dependency_overrides[get_db]())

    from api.models import User

    db.query(User).filter(User.email == email).update({"role": "admin"})
    db.commit()

    return headers


def test_admin_requires_key_or_admin_account(client, monkeypatch):

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret-admin")

    assert client.post(f"{V1}/admin/structures?name=X", content=b"").status_code == 403

    assert client.post(
        f"{V1}/admin/structures?name=X",
        content=b"",
        headers={"X-Admin-Key": "mauvais"}
    ).status_code == 403

    # Un compte ordinaire n'entre pas ; un jeton invalide rend 401 (a
    # rafraichir), pas 403.
    assert client.get(f"{V1}/admin/stats", headers=_signup(client)).status_code == 403

    assert client.get(
        f"{V1}/admin/stats",
        headers={"Authorization": "Bearer pas-un-jeton"}
    ).status_code == 401

    assert client.get(f"{V1}/admin/stats", headers={"X-Admin-Key": "secret-admin"}).status_code == 200

    assert client.get(f"{V1}/admin/stats", headers=_admin(client)).status_code == 200


def test_role_is_never_set_by_the_public_api(client):

    response = client.post(
        f"{V1}/auth/register",
        json={"email": "pirate@example.com", "password": "motdepasse1", "role": "admin"}
    )

    assert _data(response)["user"]["role"] == "user"


def test_admin_stats_and_structures(client):

    headers = _admin(client)

    _signup(client, "b@example.com")

    stats = _data(client.get(f"{V1}/admin/stats", headers=headers))

    assert stats["users"]["total"] == 2
    assert stats["users"]["admins"] == 1
    assert stats["structures"] == 1
    assert len(stats["signups"]) == 30
    assert stats["signups"][-1]["count"] == 2

    structures = _data(client.get(f"{V1}/admin/structures", headers=headers))

    assert structures[0]["symbol"] == "TEST"
    assert structures[0]["rows"] == 150

    assert "training" in _data(client.get(f"{V1}/admin/model", headers=headers))


def test_admin_manages_users(client):

    headers = _admin(client)

    for index in range(3):
        _signup(client, f"user{index}@example.com")

    page = _data(client.get(f"{V1}/admin/users?limit=2", headers=headers))

    assert page["pagination"] == {"total": 4, "page": 1, "limit": 2, "pages": 2}
    assert all("password_hash" not in user for user in page["items"])

    found = _data(client.get(f"{V1}/admin/users?search=USER1", headers=headers))["items"]

    assert [user["email"] for user in found] == ["user1@example.com"]

    user_id = found[0]["id"]

    updated = _data(client.patch(f"{V1}/admin/users/{user_id}", json={"plan": "pro"}, headers=headers))

    assert updated["effective_plan"] == "pro"

    assert _data(client.get(f"{V1}/admin/users?plan=pro", headers=headers))["pagination"]["total"] == 1

    assert client.patch(
        f"{V1}/admin/users/{user_id}",
        json={"plan": "platinum"},
        headers=headers
    ).status_code == 422

    detail = _data(client.get(f"{V1}/admin/users/{user_id}", headers=headers))

    assert detail["email"] == "user1@example.com"
    assert detail["payments"] == []

    assert client.get(f"{V1}/admin/users/9999", headers=headers).status_code == 404


def test_admin_cannot_demote_itself(client):

    headers = _admin(client)

    me = _data(client.get(f"{V1}/admin/users", headers=headers))["items"][0]

    response = client.patch(f"{V1}/admin/users/{me['id']}", json={"role": "user"}, headers=headers)

    assert response.status_code == 422


def test_admin_revokes_sessions(client):

    headers = _admin(client)

    session = _register(client, "victime@example.com")

    user_id = session["user"]["id"]

    assert client.post(f"{V1}/admin/users/{user_id}/revoke-sessions", headers=headers).status_code == 200

    assert client.post(
        f"{V1}/auth/refresh",
        json={"refresh_token": session["refresh_token"]}
    ).status_code == 401


def test_account_actions_need_an_admin_account_not_the_key(client, monkeypatch):

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret-admin")

    user_id = _register(client)["user"]["id"]

    assert client.patch(
        f"{V1}/admin/users/{user_id}",
        json={"plan": "pro"},
        headers={"X-Admin-Key": "secret-admin"}
    ).status_code == 403


def test_admin_edits_identity(client):

    headers = _admin(client)

    user_id = _register(client, "awa@example.com")["user"]["id"]

    updated = _data(client.patch(
        f"{V1}/admin/users/{user_id}",
        json={"first_name": " Awa ", "last_name": "Diop", "phone": "+221770000000"},
        headers=headers
    ))

    assert (updated["first_name"], updated["last_name"]) == ("Awa", "Diop")
    assert updated["plan"] == "free"

    found = _data(client.get(f"{V1}/admin/users?search=diop", headers=headers))["items"]

    assert [user["id"] for user in found] == [user_id]

    # null efface, un champ absent reste.
    cleared = _data(client.patch(f"{V1}/admin/users/{user_id}", json={"phone": None}, headers=headers))

    assert cleared["phone"] is None
    assert cleared["last_name"] == "Diop"


def test_admin_deactivates_and_reactivates(client):

    headers = _admin(client)

    session = _register(client, "b@example.com")

    user_id = session["user"]["id"]

    user_headers = {"Authorization": f"Bearer {session['token']}"}

    off = _data(client.post(f"{V1}/admin/users/{user_id}/deactivate", headers=headers))

    assert off["is_active"] is False

    # Jeton d'acces refuse, sessions fermees, connexion impossible.
    assert client.get(f"{V1}/account/me", headers=user_headers).status_code == 403

    assert client.post(
        f"{V1}/auth/refresh",
        json={"refresh_token": session["refresh_token"]}
    ).status_code == 401

    login = {"email": "b@example.com", "password": "motdepasse1"}

    assert client.post(f"{V1}/auth/login", json=login).status_code == 403

    assert client.post(
        f"{V1}/auth/login",
        json={**login, "password": "mauvais-mdp"}
    ).status_code == 401

    assert _data(client.get(f"{V1}/admin/users?status=inactive", headers=headers))["pagination"]["total"] == 1
    assert _data(client.get(f"{V1}/admin/stats", headers=headers))["users"]["inactive"] == 1

    assert _data(client.post(f"{V1}/admin/users/{user_id}/activate", headers=headers))["is_active"] is True

    assert client.post(f"{V1}/auth/login", json=login).status_code == 200


def test_admin_cannot_deactivate_or_delete_itself(client):

    headers = _admin(client)

    me = _data(client.get(f"{V1}/admin/users", headers=headers))["items"][0]

    assert client.post(f"{V1}/admin/users/{me['id']}/deactivate", headers=headers).status_code == 422
    assert client.delete(f"{V1}/admin/users/{me['id']}", headers=headers).status_code == 422


def test_admin_deletes_user(client):

    headers = _admin(client)

    user_headers = _signup(client, "b@example.com")

    user_id = _data(client.get(f"{V1}/account/me", headers=user_headers))["id"]

    assert client.delete(f"{V1}/admin/users/{user_id}", headers=headers).status_code == 200

    assert client.get(f"{V1}/admin/users/{user_id}", headers=headers).status_code == 404
    assert client.delete(f"{V1}/admin/users/{user_id}", headers=headers).status_code == 404


def test_admin_creates_admin_with_provisional_password(client):

    headers = _admin(client)

    body = {"email": " New@Example.com ", "password": "Provisoire1", "first_name": "Moussa"}

    admin = _data(client.post(f"{V1}/admin/users/admins", json=body, headers=headers))

    assert admin["email"] == "new@example.com"
    assert admin["role"] == "admin"
    assert admin["is_active"] is True
    assert admin["must_change_password"] is True

    assert client.post(f"{V1}/admin/users/admins", json=body, headers=headers).status_code == 409

    # Mot de passe d'admin : majuscule et chiffre exiges.
    assert client.post(
        f"{V1}/admin/users/admins",
        json={"email": "x@example.com", "password": "motdepasse1"},
        headers=headers
    ).status_code == 422

    login = _data(client.post(f"{V1}/auth/login", json={"email": "new@example.com", "password": "Provisoire1"}))

    assert login["user"]["must_change_password"] is True

    new_headers = {"Authorization": f"Bearer {login['token']}"}

    # Back-office ferme tant que le mot de passe provisoire n'est pas change.
    assert client.get(f"{V1}/admin/stats", headers=new_headers).status_code == 403

    changed = _data(client.put(
        f"{V1}/auth/password",
        json={"current_password": "Provisoire1", "new_password": "Personnel2"},
        headers=new_headers
    ))

    assert client.get(
        f"{V1}/admin/stats",
        headers={"Authorization": f"Bearer {changed['token']}"}
    ).status_code == 200


def test_admin_exports_users_csv(client):

    headers = _admin(client)

    _signup(client, "b@example.com")

    response = client.get(f"{V1}/admin/users/export?role=user", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    lines = response.content.decode("utf-8-sig").splitlines()

    assert lines[0].startswith("E-mail,Prénom,Nom")
    assert len(lines) == 2
    assert lines[1].startswith("b@example.com,")


# =========================================================
# MOT DE PASSE OUBLIE ET PROFIL
# =========================================================

@pytest.fixture
def outbox(monkeypatch):
    """E-mails envoyes, captures au lieu de partir chez Resend."""

    from api.services import mailer

    sent = []

    monkeypatch.setattr(mailer, "send", lambda to, subject, body: sent.append({"to": to, "body": body}))

    return sent


def _code(mail):
    import re

    return re.search(r"\b(\d{6})\b", mail["body"]).group(1)


def test_forgot_password_resets_with_emailed_code(client, outbox):

    session = _register(client, "b@example.com")

    response = client.post(f"{V1}/auth/forgot-password", json={"email": "B@example.com"})

    assert response.status_code == 200
    assert [mail["to"] for mail in outbox] == ["b@example.com"]

    code = _code(outbox[0])

    check = {"email": "b@example.com", "code": code}

    assert client.post(f"{V1}/auth/verify-reset-code", json=check).status_code == 200

    assert client.post(
        f"{V1}/auth/reset-password",
        json={**check, "new_password": "court"}
    ).status_code == 422

    assert client.post(
        f"{V1}/auth/reset-password",
        json={**check, "new_password": "nouveaumdp1"}
    ).status_code == 200

    # Code a usage unique, anciennes sessions fermees, nouveau mot de passe actif.
    assert client.post(
        f"{V1}/auth/reset-password",
        json={**check, "new_password": "encoreun1"}
    ).status_code == 400

    assert client.post(
        f"{V1}/auth/refresh",
        json={"refresh_token": session["refresh_token"]}
    ).status_code == 401

    assert client.post(
        f"{V1}/auth/login",
        json={"email": "b@example.com", "password": "nouveaumdp1"}
    ).status_code == 200


def test_forgot_password_does_not_reveal_accounts(client, outbox):

    unknown = client.post(f"{V1}/auth/forgot-password", json={"email": "inconnu@example.com"})

    assert unknown.status_code == 200
    assert outbox == []

    assert client.post(
        f"{V1}/auth/verify-reset-code",
        json={"email": "inconnu@example.com", "code": "123456"}
    ).status_code == 400


def test_reset_code_attempts_are_limited(client, outbox, monkeypatch):

    monkeypatch.setattr(settings, "RESET_CODE_MAX_ATTEMPTS", 2)

    _register(client, "b@example.com")

    client.post(f"{V1}/auth/forgot-password", json={"email": "b@example.com"})

    code = _code(outbox[0])

    wrong = "000000" if code != "000000" else "111111"

    for _ in range(2):
        assert client.post(
            f"{V1}/auth/verify-reset-code",
            json={"email": "b@example.com", "code": wrong}
        ).status_code == 400

    # Essais epuises : meme le bon code est refuse.
    assert client.post(
        f"{V1}/auth/verify-reset-code",
        json={"email": "b@example.com", "code": code}
    ).status_code == 400


def test_user_updates_profile(client):

    headers = _signup(client)

    profile = _data(client.patch(
        f"{V1}/account/me",
        json={"first_name": "Awa", "last_name": " Diop ", "phone": ""},
        headers=headers
    ))

    assert (profile["first_name"], profile["last_name"], profile["phone"]) == ("Awa", "Diop", None)

    # Le role et l'offre ne passent pas par le profil.
    profile = _data(client.patch(f"{V1}/account/me", json={"role": "admin", "plan": "pro"}, headers=headers))

    assert profile["role"] == "user"
    assert profile["plan"] == "free"
    assert profile["first_name"] == "Awa"


def test_admin_lists_payments(client):

    headers = _admin(client)

    page = _data(client.get(f"{V1}/admin/payments", headers=headers))

    assert page["items"] == []
    assert page["pagination"]["total"] == 0


def test_quotes_feed_appends_sessions(client):

    before = len(market_data.load_structure("TEST"))

    feed = quotes_feed.parse_feed(
        b"name,date,open,high,low,close,volume\n"
        b"test,2030-01-02,1000,1010,990,1005,12\n"
        b"test,2030-01-03,1005,1020,1000,1015,30\n"
    )

    report = quotes_feed.apply_feed(feed)

    assert report["test"] == {"symbol": "TEST", "rows_added": 2}

    history = market_data.load_structure("TEST")

    assert len(history) == before + 2

    assert history["Close"].iloc[-1] == 1015


# =========================================================
# MIGRATIONS
# =========================================================

def test_migrations_match_models(tmp_path):
    """Les migrations Alembic produisent exactement le schema des modeles :
    un modele modifie sans migration fait echouer ce test."""

    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext

    url = f"sqlite:///{tmp_path / 'migrations.db'}"

    config = Config(str(settings.BASE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)

    command.upgrade(config, "head")

    with create_engine(url).connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []

    command.downgrade(config, "base")
