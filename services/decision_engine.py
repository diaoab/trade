"""Moteur de decision technique + ML.

Les bonus/malus ci-dessous sont des heuristiques d'analyse technique : ils
fixent un ordre de grandeur raisonnable entre signaux, sans pretention de
precision predictive. Le sens de lecture de chaque signal, lui, est confronte
a l'historique par python -m training.backtest_engine ; c'est ce backtest qui
a conduit a lire les extremes du RSI et de Bollinger titre par titre (voir
_read_extreme).
"""

from services.indicators import RSI_OVERBOUGHT, RSI_OVERSOLD


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
BOLLINGER_WEIGHT = 8
MOMENTUM_WEIGHT = 8

TECHNICAL_SCORE_NEUTRAL = 50
TECHNICAL_SCORE_MIN = 0
TECHNICAL_SCORE_MAX = 100

# Seuils RSI_OVERSOLD / RSI_OVERBOUGHT : definis avec l'indicateur, qui
# s'en sert pour calibrer la lecture des extremes.


# =========================================================
# RISQUE (VOLATILITE)
# =========================================================

VOLATILITY_LOW_THRESHOLD = 0.02
VOLATILITY_MEDIUM_THRESHOLD = 0.05

RISK_SCORE_LOW_VOLATILITY = 90
RISK_SCORE_MEDIUM_VOLATILITY = 65
RISK_SCORE_HIGH_VOLATILITY = 35


# =========================================================
# LIQUIDITE
# =========================================================

# Au-dela de la moitie des 20 dernieres seances sans variation, ou quand la
# seance analysee a echange moins de 5 % du volume moyen, les indicateurs
# sont calcules sur un cours qui ne reflete presque aucun echange reel. Le
# seuil de volume est bas parce que la moyenne est tiree par quelques tres
# grosses seances : la seance mediane n'en represente que 30 a 40 %, et
# 5 % isole environ une seance sur six.
FLAT_SHARE_THRESHOLD = 0.5
LOW_VOLUME_RATIO = 0.05


# =========================================================
# DECISION FINALE
# =========================================================

DECISION_BUY_THRESHOLD = 70
DECISION_HOLD_THRESHOLD = 45
# En dessous de DECISION_HOLD_THRESHOLD : VENDRE.

# Confiance = ecart du score a la neutralite (50), ramene sur 100. Pas de
# plancher : un score de 52 doit afficher une confiance quasi nulle, et non
# un "50 %" qui laisserait croire a une chance sur deux d'avoir raison.
CONFIDENCE_MIN = 0
CONFIDENCE_MAX = 95


def _read_extreme(description, extreme, reading):
    """Traduit un extreme en signal, selon la lecture calibree sur le titre.

    extreme : +1 exces haussier, -1 exces baissier. reading : +1 si, sur ce
    titre, les exces se sont jusqu'ici prolonges (suivi de tendance), -1
    s'ils se sont corriges (retour a la moyenne), 0 si son historique ne
    tranche pas. Retourne (sens du signal, explication).

    Ni la convention classique (survente = achat) ni son inverse ne vaut
    pour tous les titres du catalogue (cf. python -m
    training.backtest_engine) : sans lecture etablie, l'extreme est signale
    mais ne deplace pas le score.
    """

    if reading > 0:

        return extreme, (
            f"{description} : sur ce titre, un tel élan s'est le plus "
            "souvent prolongé."
        )

    if reading < 0:

        return -extreme, (
            f"{description} : sur ce titre, un tel excès s'est le plus "
            "souvent corrigé."
        )

    return 0, (
        f"{description}, mais l'historique de ce titre ne permet pas de "
        "dire si cela annonce une poursuite ou un retournement."
    )


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

    # Sens des signaux affiches a titre indicatif (hors score), pour que le
    # backtest continue de les suivre : {indicateur: +1, 0 ou -1}.
    indicative = {}

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

    # La lecture d'un extreme (surachat, survente) depend du titre : voir
    # _read_extreme et services.indicators.calibrate_extremes.
    if "RSI" in selected_parameters:

        rsi = row["RSI"]

        if rsi > RSI_OVERBOUGHT or rsi < RSI_OVERSOLD:

            direction, reason = _read_extreme(
                "Le RSI est en zone de surachat"
                if rsi > RSI_OVERBOUGHT
                else "Le RSI est en zone de survente",
                1 if rsi > RSI_OVERBOUGHT else -1,
                row.get("RSI_Reading", 0)
            )

            technical_score += direction * RSI_WEIGHT

            positive += direction > 0
            negative += direction < 0
            neutral += direction == 0

            reasons.append(reason)

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
        # la ligne de signal dit si elle accelere ou s'essouffle.
        trend = (
            "au-dessus de zéro, tendance de fond haussière"
            if macd > 0
            else "en dessous de zéro, tendance de fond baissière"
        )

        # Indicatif : affiche et explique, sans deplacer le score. Au
        # backtest (python -m training.backtest_engine), un MACD au-dessus
        # de son signal n'a ete suivi de meilleures variations sur aucun
        # horizon (5, 20, 60 seances) pour deux titres sur trois, et de
        # moins bonnes sur l'ensemble. Le compter ajoutait du bruit.
        indicative["MACD"] = int(macd_gap > 0) - int(macd_gap < 0)

        neutral += 1

        if macd_gap == 0:

            # Cours fige sur une longue periode : MACD et signal se
            # confondent.
            reasons.append(
                "Le MACD se confond avec sa ligne de signal."
            )

        else:

            reasons.append(
                "Le MACD est "
                + ("supérieur" if macd_gap > 0 else "inférieur")
                + f" à sa ligne de signal ({trend}). Indicatif : ce signal "
                "n'entre pas dans le score."
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

            if position >= 100 or position <= 0:

                direction, reason = _read_extreme(
                    "Le cours est sorti par le haut des bandes de Bollinger"
                    if position >= 100
                    else "Le cours est sorti par le bas des bandes de "
                    "Bollinger",
                    1 if position >= 100 else -1,
                    row.get("Bollinger_Reading", 0)
                )

                technical_score += direction * BOLLINGER_WEIGHT

                positive += direction > 0
                negative += direction < 0
                neutral += direction == 0

                reasons.append(reason)

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
    # LIQUIDITE
    # =====================================================

    # Avertissement seulement : il ne deplace pas le score, faute d'avoir
    # mesure de combien un signal perd en fiabilite sur un titre illiquide.
    liquidity_warnings = []

    flat_share = row.get("Flat_Share_20D")

    if flat_share is not None and flat_share >= FLAT_SHARE_THRESHOLD:

        liquidity_warnings.append(
            f"Le cours n'a pas varié sur {flat_share * 100:.0f} % des 20 "
            "dernières séances : titre peu échangé."
        )

    volume_ratio = row.get("Volume_Ratio")

    if volume_ratio is not None and volume_ratio < LOW_VOLUME_RATIO:

        liquidity_warnings.append(
            "Le volume de la séance est très faible "
            f"({volume_ratio * 100:.0f} % de sa moyenne sur 20 séances)."
        )

    # =====================================================
    # SCORE ML
    # =====================================================

    ml_weight = weights["Machine Learning"]

    if ml_result is None:

        # Modele absent ou illisible : l'analyse reste possible sur la seule
        # base technique, plutot que de ne rien rendre du tout.
        ml_score = None

        reasons.append(
            "Le modèle ML n'est pas disponible : la décision repose sur "
            "l'analyse technique."
        )

    else:

        probability_up = ml_result["probability_up"] * 100

        # "ml_score" (percentile de la probabilite dans son historique
        # hors-echantillon) est prefere quand il est fourni par predict_row :
        # une probabilite brute compressee autour du taux de base ne ferait
        # jamais pencher la decision vers l'achat. A defaut (modele plus
        # ancien, sans distribution de reference), on retombe sur la
        # probabilite brute.
        ml_score = ml_result.get("ml_score", probability_up)

        reasons.append(
            f"Le modèle ML estime une probabilité "
            f"de hausse de {probability_up:.1f}%"
            + (
                f" (position dans son historique : {ml_score:.1f}/100)"
                if "ml_score" in ml_result
                else ""
            )
            + (
                ", à titre indicatif : il n'entre pas dans le score."
                if ml_weight == 0
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

    risk_weight = (
        weights["Risque"]
    )

    # Seules les composantes qui disent un SENS (hausse ou baisse) entrent
    # dans la moyenne : l'analyse technique et, s'il est disponible, le
    # modele. Le total des poids est recalcule en consequence.
    components = [
        (technical_score, technical_weight)
    ]

    if ml_score is not None:

        components.append(
            (ml_score, ml_weight)
        )

    directional_weight = sum(
        weight
        for _, weight in components
    )

    # =====================================================
    # SCORE FINAL
    # =====================================================

    if directional_weight == 0:

        # Ni la technique ni le modele ne pesent : rien ne peut dire dans
        # quel sens pencher, quel que soit le niveau de risque.
        final_score = 50.0

        reasons.append(
            "Ni l'analyse technique ni le modèle ne pèsent dans le score : "
            "aucune composante ne peut départager la décision."
        )

    else:

        final_score = sum(
            score * weight
            for score, weight in components
        ) / directional_weight

        # Le risque ne dit pas un sens : une volatilite faible n'est pas une
        # raison d'acheter. Le moyenner avec les autres scores (ce que
        # faisait ce moteur) remontait vers 50 et au-dela une analyse
        # nettement baissiere des que le titre etait calme. Il reduit donc
        # la conviction : plus le risque est eleve, plus le score est ramene
        # vers la neutralite, a hauteur de la part du poids "Risque".
        if risk_score is not None:

            risk_share = risk_weight / (directional_weight + risk_weight)

            conviction = 1 - risk_share * (1 - risk_score / 100)

            final_score = 50 + (final_score - 50) * conviction

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

        "ml_score": (
            round(ml_score, 2)
            if ml_score is not None
            else None
        ),

        "risk_score": (
            round(risk_score, 2)
            if risk_score is not None
            else None
        ),

        "positive": positive,

        "negative": negative,

        "neutral": neutral,

        "reasons": reasons,

        "liquidity_warnings": liquidity_warnings,

        "indicative": indicative
    }
