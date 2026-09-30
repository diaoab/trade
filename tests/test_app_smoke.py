"""Test de fumee : lance reellement chaque page de l'application.

Les autres tests couvrent les services, pas les pages. Or une page peut
echouer pour une raison qu'aucun test de service ne voit : un argument que la
version installee de Streamlit ne connait pas (st.metric(icon=...) sous
Streamlit 1.50, par exemple). Ici chaque page est executee de bout en bout,
sur un historique synthetique et des fichiers temporaires, avec pour seule
exigence qu'aucune exception ne soit levee.
"""

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from services import (
    loaders,
    portfolio,
    market_data,
    prediction_log,
    predictor,
    preferences,
    trading_calendar
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirige donnees, reglages, journal et modele vers un dossier
    temporaire : le test ne lit ni n'ecrit rien dans le vrai projet."""

    rng = np.random.default_rng(0)

    sessions = 150

    pd.DataFrame({
        "Date": pd.bdate_range("2025-01-01", periods=sessions),
        "Close": 1000 + np.cumsum(rng.normal(0, 10, sessions)),
        "Volume": rng.integers(1, 500, sessions)
    }).to_excel(tmp_path / "TEST.xlsx", index=False)

    # Seconde structure, declaree indice de reference dans les reglages :
    # la page Analyse affiche alors la comparaison a l'indice.
    pd.DataFrame({
        "Date": pd.bdate_range("2025-01-01", periods=sessions),
        "Close": 200 + np.cumsum(rng.normal(0, 1, sessions))
    }).to_excel(tmp_path / "ZINDICE.xlsx", index=False)

    (tmp_path / "preferences.json").write_text(
        '{"benchmark_symbol": "ZINDICE"}',
        encoding="utf-8"
    )

    monkeypatch.setattr(market_data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(market_data, "REGISTRY_PATH", tmp_path / "structures.json")
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", tmp_path / "preferences.json")
    monkeypatch.setattr(prediction_log, "PREDICTION_LOG_PATH", tmp_path / "log.csv")
    monkeypatch.setattr(trading_calendar, "HOLIDAYS_PATH", tmp_path / "holidays.json")
    monkeypatch.setattr(portfolio, "PORTFOLIO_PATH", tmp_path / "portfolio.json")

    # Pas de modele : l'analyse doit aboutir sur la seule base technique.
    for name in ("MODEL_PATH", "FEATURES_PATH", "MODEL_METADATA_PATH"):
        monkeypatch.setattr(predictor, name, tmp_path / "absent")

    # Un dividende deja detache et un a venir, une ligne en portefeuille :
    # les pages Marche, Portefeuille et Dividendes ont de quoi s'afficher.
    market_data.set_dividends(
        "TEST",
        [
            {"ex_date": "2025-04-01", "amount": 20},
            {"ex_date": "2025-08-04", "amount": 25}
        ]
    )

    portfolio.save_positions([{
        "symbol": "TEST",
        "quantity": 10,
        "buy_price": 990,
        "buy_date": "2025-02-03"
    }])

    for cached in (
        loaders.load_prepared,
        loaders.load_signal_backtest
    ):
        cached.clear()

    return tmp_path


def _rerun(app):
    """Relance le script apres une interaction.

    AppTest suppose qu'un st.pills renvoie toujours une liste ; en selection
    simple il renvoie une chaine, que le harnais parcourt alors caractere
    par caractere. On lui redonne la forme qu'il attend avant de relancer.
    """

    for group in app.button_group:

        if isinstance(group.value, str):
            group.set_value([group.value])

    return app.run()


def _run(page=None):

    app = AppTest.from_file("app.py", default_timeout=60).run()

    assert not app.exception, app.exception

    if page is not None:

        app.switch_page(page)

        _rerun(app)

        assert not app.exception, app.exception

    return app


def test_analysis_page_renders_and_analyses(sandbox):

    app = _run()

    analyse = next(
        button
        for button in app.button
        if button.label == "Analyser"
    )

    analyse.click()

    _rerun(app)

    assert not app.exception, app.exception

    assert any(
        "Résultat de l'analyse" in header.value
        for header in app.header
    )

    assert any(
        "Face à l'indice" in markdown.value
        for markdown in app.markdown
    )

    # L'analyse a ete tracee dans le journal (temporaire).
    assert len(prediction_log.load_prediction_log()) == 1


@pytest.mark.parametrize(
    "page",
    [
        "app_pages/marche.py",
        "app_pages/portefeuille.py",
        "app_pages/dividendes.py",
        "app_pages/journal.py",
        "app_pages/parametres.py"
    ]
)
def test_other_pages_render(sandbox, page):

    _run(page)
