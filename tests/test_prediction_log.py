"""Tests de services/prediction_log.py, sur un fichier temporaire pour ne
jamais toucher au vrai journal (results/prediction_log.csv)."""

import pandas as pd
import pytest

from services import prediction_log


@pytest.fixture
def log_path(tmp_path, monkeypatch):

    path = tmp_path / "prediction_log.csv"

    monkeypatch.setattr(prediction_log, "PREDICTION_LOG_PATH", path)

    return path


def _fake_result(**overrides):

    result = {
        "decision": "CONSERVER",
        "score": 55.0,
        "confidence": 60.0,
        "technical_score": 60.0,
        "ml_score": 50.0,
        "risk_score": 70.0
    }

    result.update(overrides)

    return result


def test_load_prediction_log_is_empty_before_any_analysis(log_path):

    log = prediction_log.load_prediction_log()

    assert log.empty
    assert list(log.columns) == prediction_log.LOG_COLUMNS


def test_log_prediction_creates_file_with_one_row(log_path):

    prediction_log.log_prediction(
        symbol="CORIS_1",
        structure_name="Coris_1",
        session_date=pd.Timestamp("2025-12-31"),
        close=10780.0,
        result=_fake_result(),
        ml_result={"probability_up": 0.58},
        weights={"Technique": 40, "Machine Learning": 40, "Risque": 20}
    )

    assert log_path.exists()

    log = prediction_log.load_prediction_log()

    assert len(log) == 1
    assert log.iloc[0]["symbol"] == "CORIS_1"
    assert log.iloc[0]["decision"] == "CONSERVER"
    assert log.iloc[0]["probability_up"] == pytest.approx(0.58)


def test_log_prediction_appends_without_overwriting(log_path):

    for score in (55.0, 62.0):

        prediction_log.log_prediction(
            symbol="CORIS_1",
            structure_name="Coris_1",
            session_date=pd.Timestamp("2025-12-31"),
            close=10780.0,
            result=_fake_result(score=score),
            ml_result={"probability_up": 0.58},
            weights={"Technique": 40, "Machine Learning": 40, "Risque": 20}
        )

    log = prediction_log.load_prediction_log()

    assert len(log) == 2
    assert list(log["score"]) == [55.0, 62.0]


def test_log_prediction_handles_missing_session_date(log_path):
    """Un historique sans colonne Date (cas rare, cf. app.py) ne doit pas
    faire planter le journal."""

    prediction_log.log_prediction(
        symbol="CORIS_1",
        structure_name="Coris_1",
        session_date=None,
        close=10780.0,
        result=_fake_result(),
        ml_result={"probability_up": 0.58},
        weights={"Technique": 40, "Machine Learning": 40, "Risque": 20}
    )

    log = prediction_log.load_prediction_log()

    assert pd.isna(log.iloc[0]["session_date"])


# =========================================================
# CONFRONTATION AU COURS REEL
# =========================================================

def _history(closes):

    return pd.DataFrame({
        "Date": pd.bdate_range("2025-01-06", periods=len(closes)),
        "Close": closes
    })


def _log(*rows):

    return pd.DataFrame(
        [
            {
                "symbol": "X",
                "session_date": pd.Timestamp(session_date),
                "decision": decision
            }
            for session_date, decision in rows
        ]
    )


def test_evaluate_predictions_judges_buy_and_sell_against_the_future_close():

    # +10 % cinq seances apres la premiere.
    rising = _history([100, 100, 100, 100, 100, 110, 110])

    evaluated = prediction_log.evaluate_predictions(
        _log(
            ("2025-01-06", "ACHETER"),
            ("2025-01-06", "VENDRE"),
            ("2025-01-06", "CONSERVER")
        ),
        load_history=lambda symbol: rising
    )

    assert evaluated["realized_return"].tolist() == pytest.approx([0.1] * 3)
    assert evaluated["outcome"].tolist() == ["juste", "fausse", "non jugée"]


def test_evaluate_predictions_waits_for_enough_history():

    evaluated = prediction_log.evaluate_predictions(
        _log(("2025-01-08", "ACHETER"), ("2030-01-01", "ACHETER")),
        load_history=lambda symbol: _history([100] * 7)
    )

    assert evaluated["outcome"].tolist() == ["en attente", "introuvable"]
    assert evaluated["realized_return"].isna().all()


def test_evaluate_predictions_survives_a_removed_structure():

    def missing(symbol):
        raise FileNotFoundError(symbol)

    evaluated = prediction_log.evaluate_predictions(
        _log(("2025-01-06", "ACHETER")),
        load_history=missing
    )

    assert evaluated["outcome"].tolist() == ["introuvable"]


def test_summary_counts_a_session_analysed_twice_only_once():

    rising = _history([100, 100, 100, 100, 100, 110, 110])

    evaluated = prediction_log.evaluate_predictions(
        _log(("2025-01-06", "ACHETER"), ("2025-01-06", "ACHETER")),
        load_history=lambda symbol: rising
    )

    summary = prediction_log.summarize_performance(evaluated)

    assert summary["ACHETER"]["count"] == 1
    assert summary["ACHETER"]["hit_rate"] == 1.0
    assert summary["ACHETER"]["mean_return"] == pytest.approx(0.1)


def test_duplicated_header_line_is_ignored_on_load(log_path):

    header = ",".join(prediction_log.LOG_COLUMNS)

    log_path.write_text(
        header + "\n" + header + "\n"
        + "2026-01-01T00:00:00+00:00,X,X,2025-12-31T00:00:00,100.0,VENDRE,"
        "38.5,50,30,21.3,0.48,90,40,40,20\n",
        encoding="utf-8"
    )

    log = prediction_log.load_prediction_log()

    assert len(log) == 1
    assert log.iloc[0]["score"] == 38.5
