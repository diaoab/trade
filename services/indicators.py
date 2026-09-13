"""Indicateurs techniques calcules sur un historique normalise.

Le DataFrame recu doit provenir de services.market_data : colonnes au
vocabulaire interne et lignes triees par date croissante. Toutes les fonctions
de ce module sont pures et n'appellent rien d'autre.
"""

import numpy as np


MM_SHORT = 20
MM_LONG = 50

BOLLINGER_WINDOW = 20
BOLLINGER_SIGMA = 2

RSI_WINDOW = 14

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

VOLATILITY_WINDOW = 10


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

    ema_fast = (
        df["Close"]
        .ewm(
            span=MACD_FAST,
            adjust=False
        )
        .mean()
    )

    ema_slow = (
        df["Close"]
        .ewm(
            span=MACD_SLOW,
            adjust=False
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
            adjust=False
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
