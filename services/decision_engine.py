"""Moteur de decision technique + ML.

Les bonus/malus ci-dessous sont des heuristiques d'analyse technique : ils
fixent un ordre de grandeur raisonnable entre signaux, sans pretention de
precision predictive. Le sens de lecture de chaque signal, lui, est confronte
a l'historique par python -m training.backtest_engine ; c'est ce backtest qui
a conduit a lire RSI et Bollinger en suivi de tendance (voir plus bas).
"""


# =========================================================
# POIDS DES SIGNAUX TECHNIQUES
# =========================================================
#
# Chaque signal deplace le score technique (centre sur 50) de sa valeur, dans
# un sens ou dans l'autre. Les ecarts relatifs entre signaux refletent leur
# importance usuelle en analyse technique (ex : un croisement de MM50 est
# generalement considere plus significatif qu'un simple momentum 5 jours).

MM20_WEIGHT = 8
MM50_WEIGHT = 10
RSI_WEIGHT = 12
MACD_WEIGHT = 10
BOLLINGER_WEIGHT = 8
MOMENTUM_WEIGHT = 8

TECHNICAL_SCORE_NEUTRAL = 50
TECHNICAL_SCORE_MIN = 0
TECHNICAL_SCORE_MAX = 100

RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70


# =========================================================
# RISQUE (VOLATILITE)
# =========================================================

VOLATILITY_LOW_THRESHOLD = 0.02
VOLATILITY_MEDIUM_THRESHOLD = 0.05

RISK_SCORE_LOW_VOLATILITY = 90
RISK_SCORE_MEDIUM_VOLATILITY = 65
RISK_SCORE_HIGH_VOLATILITY = 35


# =========================================================
# DECISION FINALE
# =========================================================

DECISION_BUY_THRESHOLD = 70
DECISION_HOLD_THRESHOLD = 45
# En dessous de DECISION_HOLD_THRESHOLD : VENDRE.

CONFIDENCE_MIN = 50
CONFIDENCE_MAX = 95


def analyze(
    row,
    ml_result,
    selected_parameters,
    weights
):

    technical_score = TECHNICAL_SCORE_NEUTRAL

    reasons = []

    positive = 0
    negative = 0
    neutral = 0

    # =====================================================
    # MM20
    # =====================================================

    if (
        "MM20" in selected_parameters
        and row["Close"] > row["MM20"]
    ):

        technical_score += MM20_WEIGHT

        positive += 1

        reasons.append(
            "Le cours est supérieur à la MM20."
        )

    elif "MM20" in selected_parameters:

        technical_score -= MM20_WEIGHT

        negative += 1

        reasons.append(
            "Le cours est inférieur à la MM20."
        )

    # =====================================================
    # MM50
    # =====================================================

    if (
        "MM50" in selected_parameters
        and row["Close"] > row["MM50"]
    ):

        technical_score += MM50_WEIGHT

        positive += 1

        reasons.append(
            "Le cours est supérieur à la MM50."
        )

    elif "MM50" in selected_parameters:

        technical_score -= MM50_WEIGHT

        negative += 1

        reasons.append(
            "Le cours est inférieur à la MM50."
        )

    # =====================================================
    # RSI
    # =====================================================

    # Lecture en suivi de tendance, et non a contre-courant : la convention
    # classique (survente = occasion d'achat, surachat = signal de vente)
    # suppose un retour a la moyenne que le backtest ne retrouve pas sur les
    # titres du catalogue (cf. python -m training.backtest_engine). Sur
    # 3 854 seances de BIBI CI et PALM CI, un RSI > 70 a ete suivi de +1,8 %
    # en moyenne a 5 seances (hausse dans 53 % des cas, contre 43 % toutes
    # seances confondues) et un RSI < 30 de -0,9 % (hausse dans 34 % des
    # cas). Sur un marche peu liquide ou la variation quotidienne est
    # plafonnee, un mouvement fort s'etale sur plusieurs seances.
    if "RSI" in selected_parameters:

        rsi = row["RSI"]

        if rsi > RSI_OVERBOUGHT:

            technical_score += RSI_WEIGHT

            positive += 1

            reasons.append(
                "Le RSI est en zone de surachat : élan haussier fort, qui "
                "s'est le plus souvent prolongé sur ce marché."
            )

        elif rsi < RSI_OVERSOLD:

            technical_score -= RSI_WEIGHT

            negative += 1

            reasons.append(
                "Le RSI est en zone de survente : élan baissier fort, qui "
                "s'est le plus souvent prolongé sur ce marché."
            )

        else:

            neutral += 1

            reasons.append(
                "Le RSI se situe dans une zone neutre."
            )

    # =====================================================
    # MACD
    # =====================================================

    if "MACD" in selected_parameters:

        macd = row["MACD"]

        macd_gap = macd - row["MACD_Signal"]

        # La position par rapport a zero dit la tendance de fond (moyenne
        # courte au-dessus ou en dessous de la longue) ; le croisement avec
        # la ligne de signal dit si elle accelere ou s'essouffle. Seul le
        # croisement deplace le score, la ligne zero nuance l'explication.
        trend = (
            "au-dessus de zéro, tendance de fond haussière"
            if macd > 0
            else "en dessous de zéro, tendance de fond baissière"
        )

        if macd_gap > 0:

            technical_score += MACD_WEIGHT

            positive += 1

            reasons.append(
                f"Le MACD est supérieur à sa ligne de signal ({trend})."
            )

        elif macd_gap < 0:

            technical_score -= MACD_WEIGHT

            negative += 1

            reasons.append(
                f"Le MACD est inférieur à sa ligne de signal ({trend})."
            )

        else:

            # Cours fige sur une longue periode : MACD et signal se
            # confondent, il n'y a ni croisement haussier ni baissier.
            neutral += 1

            reasons.append(
                "Le MACD se confond avec sa ligne de signal."
            )

    # =====================================================
    # BOLLINGER
    # =====================================================

    if "Bollinger" in selected_parameters:

        close = row["Close"]

        upper = row["Bollinger_Upper"]

        lower = row["Bollinger_Lower"]

        width = upper - lower

        if not width > 0:

            # Vingt seances sans aucune variation (frequent sur les titres
            # peu liquides) : les deux bandes se confondent avec le cours.
            # Sans ce cas, "cours <= bande basse" serait vrai et donnerait
            # un faux signal d'achat.
            neutral += 1

            reasons.append(
                "Les bandes de Bollinger sont resserrées sur le cours "
                "(aucune variation récente) : pas de signal."
            )

        else:

            # 0 % sur la bande basse, 100 % sur la bande haute.
            position = (close - lower) / width * 100

            # Meme lecture en suivi de tendance que le RSI, pour la meme
            # raison : une sortie par le haut a ete suivie de +2,9 % en
            # moyenne a 5 seances, une sortie par le bas de -0,2 %.
            if position >= 100:

                technical_score += BOLLINGER_WEIGHT

                positive += 1

                reasons.append(
                    "Le cours est sorti par le haut des bandes de Bollinger "
                    "(élan haussier)."
                )

            elif position <= 0:

                technical_score -= BOLLINGER_WEIGHT

                negative += 1

                reasons.append(
                    "Le cours est sorti par le bas des bandes de Bollinger "
                    "(élan baissier)."
                )

            else:

                neutral += 1

                reasons.append(
                    "Le cours évolue à l'intérieur des bandes de Bollinger "
                    f"(à {position:.0f} % entre la basse et la haute)."
                )

    # =====================================================
    # MOMENTUM
    # =====================================================

    if "Momentum" in selected_parameters:

        if row["Return_5D"] > 0:

            technical_score += MOMENTUM_WEIGHT

            positive += 1

            reasons.append(
                "Le momentum sur 5 jours est positif."
            )

        elif row["Return_5D"] < 0:

            technical_score -= MOMENTUM_WEIGHT

            negative += 1

            reasons.append(
                "Le momentum sur 5 jours est négatif."
            )

        else:

            neutral += 1

            reasons.append(
                "Le cours est inchangé sur 5 jours."
            )

    # =====================================================
    # VOLATILITE
    # =====================================================

    # Sans indicateur de volatilite selectionne, le risque n'est pas mesure :
    # il reste None et sort de la moyenne ponderee. Lui donner 100 par defaut
    # reviendrait a faire monter le score global quand on decoche la case,
    # donc a pousser vers l'achat en retirant de l'information.
    risk_score = None

    if "Volatilité" in selected_parameters:

        volatility = row[
            "Volatility_10D"
        ]

        if volatility < VOLATILITY_LOW_THRESHOLD:

            risk_score = RISK_SCORE_LOW_VOLATILITY

            reasons.append(
                "La volatilité récente est relativement faible."
            )

        elif volatility < VOLATILITY_MEDIUM_THRESHOLD:

            risk_score = RISK_SCORE_MEDIUM_VOLATILITY

            reasons.append(
                "La volatilité récente est modérée."
            )

        else:

            risk_score = RISK_SCORE_HIGH_VOLATILITY

            reasons.append(
                "La volatilité récente est élevée."
            )

    # =====================================================
    # SCORE ML
    # =====================================================

    probability_up = ml_result["probability_up"] * 100

    # "ml_score" (percentile de la probabilite dans son historique
    # hors-echantillon) est prefere quand il est fourni par predict_row :
    # une probabilite brute compressee autour du taux de base ne ferait
    # jamais pencher la decision vers l'achat. A defaut (modele plus ancien,
    # sans distribution de reference), on retombe sur la probabilite brute.
    ml_score = ml_result.get("ml_score", probability_up)

    reasons.append(
        f"Le modèle ML estime une probabilité "
        f"de hausse de {probability_up:.1f}%"
        + (
            f" (position dans son historique : {ml_score:.1f}/100)."
            if "ml_score" in ml_result
            else "."
        )
    )

    # =====================================================
    # NORMALISATION
    # =====================================================

    technical_score = max(
        TECHNICAL_SCORE_MIN,
        min(
            TECHNICAL_SCORE_MAX,
            technical_score
        )
    )

    # =====================================================
    # POIDS
    # =====================================================

    technical_weight = (
        weights["Technique"]
    )

    ml_weight = (
        weights["Machine Learning"]
    )

    risk_weight = (
        weights["Risque"]
    )

    # Seules les composantes reellement mesurees entrent dans la moyenne, et
    # le total des poids est recalcule en consequence.
    components = [
        (technical_score, technical_weight),
        (ml_score, ml_weight)
    ]

    if risk_score is not None:

        components.append(
            (risk_score, risk_weight)
        )

    total_weight = sum(
        weight
        for _, weight in components
    )

    # =====================================================
    # SCORE FINAL
    # =====================================================

    if total_weight == 0:

        # Tous les curseurs a zero : aucune composante ne pese, on ne peut
        # rien conclure plutot que de renvoyer un score arbitraire.
        final_score = 50.0

        reasons.append(
            "Tous les poids sont a zero : aucune composante ne peut "
            "departager la decision."
        )

    else:

        final_score = sum(
            score * weight
            for score, weight in components
        ) / total_weight

    final_score = round(
        final_score,
        2
    )

    # =====================================================
    # DECISION
    # =====================================================

    if final_score >= DECISION_BUY_THRESHOLD:

        decision = "ACHETER"

    elif final_score >= DECISION_HOLD_THRESHOLD:

        decision = "CONSERVER"

    else:

        decision = "VENDRE"

    # =====================================================
    # CONFIANCE
    # =====================================================

    confidence = abs(
        final_score - 50
    ) * 2

    confidence = min(
        CONFIDENCE_MAX,
        max(
            CONFIDENCE_MIN,
            confidence
        )
    )

    confidence = round(
        confidence,
        1
    )

    return {

        "decision": decision,

        "score": final_score,

        "confidence": confidence,

        "technical_score": round(
            technical_score,
            2
        ),

        "ml_score": round(
            ml_score,
            2
        ),

        "risk_score": (
            round(risk_score, 2)
            if risk_score is not None
            else None
        ),

        "positive": positive,

        "negative": negative,

        "neutral": neutral,

        "reasons": reasons
    }
