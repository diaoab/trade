"""Tests de l'API du service en ligne (api/), sur une base SQLite en
memoire et un historique synthetique : rien n'est lu ni ecrit dans le vrai
projet."""

import hashlib

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
from api.services import assistant_service, paydunya, quotes_feed
from api.services.engine import market_data


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

def test_admin_requires_key(client, monkeypatch):

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret-admin")

    assert client.post(f"{V1}/admin/structures?name=X", content=b"").status_code == 403

    assert client.post(
        f"{V1}/admin/structures?name=X",
        content=b"",
        headers={"X-Admin-Key": "mauvais"}
    ).status_code == 403


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
