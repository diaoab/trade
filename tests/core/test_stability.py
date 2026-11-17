"""Stabilisation du signal (core.engine.stability)."""

from core.engine.stability import DECISION_MARGIN, stabilize


def _results(scores):
    return [{"score": score, "decision": "?"} for score in scores]


def _decisions(scores):
    return [result["decision"] for result in stabilize(_results(scores))]


def test_a_one_session_spike_does_not_flip_the_signal():
    # Score brut qui saute au-dessus de 45 une seule seance (cas PALM CI).
    decisions = _decisions([25, 25, 25, 56, 25, 25])
    assert set(decisions) == {"VENDRE"}


def test_a_lasting_move_flips_the_signal():
    decisions = _decisions([25, 25, 60, 60, 60, 60, 60])
    assert decisions[0] == "VENDRE"
    assert decisions[-1] == "CONSERVER"


def test_margin_keeps_the_current_signal_near_the_threshold():
    # Lisse a 46 : CONSERVER des la premiere seance ; il faut descendre sous
    # 45 - marge pour repasser a VENDRE.
    stable = stabilize(_results([46] + [45 - DECISION_MARGIN + 1] * 30))
    assert {result["decision"] for result in stable} == {"CONSERVER"}


def test_keeps_raw_values_and_recomputes_confidence():
    stable = stabilize(_results([80, 20]))
    last = stable[-1]
    assert last["session_score"] == 20
    assert last["session_decision"] == "?"
    assert last["score"] == 0.3 * 20 + 0.7 * 80
    assert last["confidence"] == round(abs(last["score"] - 50) * 2, 1)
