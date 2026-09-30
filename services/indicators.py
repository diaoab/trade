"""Indicateurs techniques calcules sur un historique normalise.

Le DataFrame recu doit provenir de services.market_data : colonnes au
vocabulaire interne et lignes triees par date croissante. Toutes les fonctions
de ce module sont pures et n'appellent rien d'autre.
"""

import numpy as np

from services.targets import compute_future_return


MM_SHORT = 20
MM_LONG = 50

BOLLINGER_WINDOW = 20
BOLLINGER_SIGMA = 2

RSI_WINDOW = 14

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

VOLATILITY_WINDOW = 10

LIQUIDITY_WINDOW = 20

RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# Calibration de la lecture des extremes (cf. calibrate_extremes) : nombre
# minimal d'extremes passes dont l'issue est connue, et niveau de preuve
# (statistique t de leur rendement moyen) en dessous desquels on ne conclut
# pas.
CALIBRATION_MIN_EVENTS = 30
CALIBRATION_MIN_T = 2

# Horizon auquel on juge ce qui a suivi un extreme, en seances. Court et
# independant de l'horizon du modele ML : c'est a 5 seances que la lecture
# titre par titre a ete validee sans regard vers l'avenir, et un horizon
# court donne plus vite assez d'extremes a l'issue connue pour conclure.
CALIBRATION_HORIZON = 5


def calibrate_extremes(extreme, close, horizon=CALIBRATION_HORIZON):
    """Dit, seance par seance, comment lire un extreme sur CE titre.

    extreme vaut +1 sur un exces haussier (RSI en surachat, cours au-dessus
    de la bande haute de Bollinger), -1 sur un exces baissier, 0 sinon. Deux
    lectures s'opposent : le suivi de tendance (l'exces se prolonge) et le
    retour a la moyenne (l'exces se corrige). Le backtest montre qu'aucune
    n'est vraie partout : sur PALM CI les exces se prolongent, sur TOTAL CI
    ils se corrigent, sur BIBI CI ni l'un ni l'autre ne ressort.

    On regarde donc ce que le cours de ce titre a fait, `horizon` seances
    plus tard, apres chacun de ses extremes passes. Retourne +1 (lire en
    suivi de tendance), -1 (lire a contre-courant) ou 0 (l'historique ne
    tranche pas : trop peu d'extremes, ou issue trop partagee).

    Sans regard vers l'avenir : a une seance donnee, seuls comptent les
    extremes dont l'issue etait deja connue ce jour-la. La lecture d'une
    seance passee est donc celle qu'on aurait eue a l'epoque.
    """

    outcome = (
        extreme
        * compute_future_return(close, horizon)
    ).where(extreme != 0)

    # L'issue d'un extreme n'est connue que `horizon` seances plus tard.
    known = outcome.shift(horizon)

    count = known.notna().cumsum()

    mean = known.expanding().mean()

    t_stat = mean / (
        known.expanding().std()
        / np.sqrt(count)
    )

    conclusive = (
        (count >= CALIBRATION_MIN_EVENTS)
        & (t_stat.abs() >= CALIBRATION_MIN_T)
    )

    return (
        np.sign(mean)
        .where(conclusive, 0)
        .fillna(0)
        .astype(int)
    )


def calculate_indicators(df):

    df = df.copy()

    # ==============================
    # MOYENNES MOBILES
    # ==============================

    df["MM20"] = (
        df["Close"]
        .rolling(MM_SHORT)
        .mean()
    )

    df["MM50"] = (
        df["Close"]
        .rolling(MM_LONG)
        .mean()
    )

    # ==============================
    # BOLLINGER
    # ==============================

    rolling_mean = (
        df["Close"]
        .rolling(BOLLINGER_WINDOW)
        .mean()
    )

    # ddof=0 : ecart-type de population, la convention utilisee par TA-Lib et
    # la quasi-totalite des plateformes pour les bandes de Bollinger. Le
    # defaut pandas (ddof=1, ecart-type d'echantillon) donne des bandes
    # legerement plus larges que la reference du marche.
    rolling_std = (
        df["Close"]
        .rolling(BOLLINGER_WINDOW)
        .std(ddof=0)
    )

    df["Bollinger_Middle"] = rolling_mean

    df["Bollinger_Upper"] = (
        rolling_mean
        + BOLLINGER_SIGMA * rolling_std
    )

    df["Bollinger_Lower"] = (
        rolling_mean
        - BOLLINGER_SIGMA * rolling_std
    )

    # ==============================
    # RSI
    # ==============================

    delta = df["Close"].diff()

    # Lissage de Wilder (formule originale, 1978) : moyenne mobile
    # exponentielle recursive, alpha = 1/periode. C'est LA definition de
    # reference du RSI, celle utilisee par TradingView, MetaTrader et la
    # quasi-totalite des plateformes de marche.
    rsi_alpha = 1 / RSI_WINDOW

    gain = (
        delta
        .clip(lower=0)
        .ewm(alpha=rsi_alpha, adjust=False, min_periods=RSI_WINDOW)
        .mean()
    )

    loss = (
        -delta
        .clip(upper=0)
        .ewm(alpha=rsi_alpha, adjust=False, min_periods=RSI_WINDOW)
        .mean()
    )

    # Aucune baisse sur la fenetre : rs vaut l'infini, donc RSI = 100. C'est
    # frequent sur les titres peu liquides de la BRVM, ou une serie de seances
    # sans echange laisse le cours inchange.
    rs = gain / loss

    df["RSI"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    # Fenetre entierement plate : ni hausse ni baisse, donc RSI neutre plutot
    # que le 0/0 -> NaN qui ferait disparaitre la seance du jeu de donnees.
    df.loc[
        (gain == 0) & (loss == 0),
        "RSI"
    ] = 50

    # ==============================
    # MACD
    # ==============================

    # min_periods : une moyenne exponentielle part de la toute premiere
    # cloture et met du temps a s'en detacher. Sans periode de chauffe, le
    # MACD afficherait des valeurs des la premiere seance (0, puis un ecart
    # artificiellement petit) alors que MM, Bollinger et RSI restent vides
    # tant que leur fenetre n'est pas pleine. La valeur une fois la chauffe
    # passee est inchangee.
    ema_fast = (
        df["Close"]
        .ewm(
            span=MACD_FAST,
            adjust=False,
            min_periods=MACD_FAST
        )
        .mean()
    )

    ema_slow = (
        df["Close"]
        .ewm(
            span=MACD_SLOW,
            adjust=False,
            min_periods=MACD_SLOW
        )
        .mean()
    )

    df["MACD"] = (
        ema_fast - ema_slow
    )

    df["MACD_Signal"] = (
        df["MACD"]
        .ewm(
            span=MACD_SIGNAL,
            adjust=False,
            min_periods=MACD_SIGNAL
        )
        .mean()
    )

    df["MACD_Hist"] = (
        df["MACD"]
        - df["MACD_Signal"]
    )

    # ==============================
    # RENDEMENTS
    # ==============================

    df["Return_1D"] = (
        df["Close"]
        .pct_change()
    )

    df["Return_5D"] = (
        df["Close"]
        .pct_change(5)
    )

    # ==============================
    # VOLATILITE
    # ==============================

    df["Volatility_10D"] = (
        df["Return_1D"]
        .rolling(VOLATILITY_WINDOW)
        .std()
    )

    # ==============================
    # LIQUIDITE
    # ==============================

    # Part des seances sans aucune variation sur la fenetre : sur la BRVM,
    # un cours qui ne bouge pas signale le plus souvent un titre qui ne
    # s'echange pas, pas un marche a l'equilibre.
    df["Flat_Share_20D"] = (
        (df["Return_1D"] == 0)
        .astype(float)
        .where(df["Return_1D"].notna())
        .rolling(LIQUIDITY_WINDOW)
        .mean()
    )

    # ==============================
    # DISTANCE AUX MM
    # ==============================

    df["Distance_MM20"] = (
        df["Close"]
        / df["MM20"]
        - 1
    )

    df["Distance_MM50"] = (
        df["Close"]
        / df["MM50"]
        - 1
    )

    # ==============================
    # VERSIONS RELATIVES
    # ==============================
    #
    # Le modele est partage entre plusieurs structures, dont les cours
    # n'ont pas le meme ordre de grandeur. Un MACD de 12 ne veut pas dire
    # la meme chose sur un titre a 1 300 FCFA et sur un titre a 50 000.
    # Ces variantes ramenent chaque indicateur a une echelle comparable.

    df["MACD_Rel"] = (
        df["MACD"]
        / df["Close"]
    )

    df["MACD_Hist_Rel"] = (
        df["MACD_Hist"]
        / df["Close"]
    )

    # Position dans les bandes de Bollinger : 0 sur la bande basse,
    # 1 sur la bande haute.
    bollinger_width = (
        df["Bollinger_Upper"]
        - df["Bollinger_Lower"]
    )

    df["Bollinger_Position"] = (
        (df["Close"] - df["Bollinger_Lower"])
        / bollinger_width.replace(0, np.nan)
    )

    df["Bollinger_Width"] = (
        bollinger_width
        / df["Bollinger_Middle"]
    )

    # ==============================
    # LECTURE DES EXTREMES
    # ==============================

    df["RSI_Reading"] = calibrate_extremes(
        (df["RSI"] > RSI_OVERBOUGHT).astype(int)
        - (df["RSI"] < RSI_OVERSOLD).astype(int),
        df["Close"]
    )

    # Bandes confondues (cours fige) : pas un extreme, cf. decision_engine.
    has_width = bollinger_width > 0

    df["Bollinger_Reading"] = calibrate_extremes(
        (has_width & (df["Close"] >= df["Bollinger_Upper"])).astype(int)
        - (has_width & (df["Close"] <= df["Bollinger_Lower"])).astype(int),
        df["Close"]
    )

    if "Volume" in df.columns:

        average_volume = (
            df["Volume"]
            .rolling(MM_SHORT)
            .mean()
        )

        df["Volume_Ratio"] = (
            df["Volume"]
            / average_volume.replace(0, np.nan)
        )

    return df
