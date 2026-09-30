# Financial AI Advisor

Assistant expérimental d'analyse technique et de prédiction pour des titres
cotés (historiques Excel, format BRVM). Combine des indicateurs techniques
classiques (moyennes mobiles, RSI, MACD, Bollinger), un modèle de machine
learning entraîné sur l'ensemble des titres disponibles, et un moteur de
décision qui pondère les deux.

**Ce n'est pas un outil de conseil financier.** Les résultats sont
expérimentaux ; voir [Limites connues](#limites-connues) avant d'en tirer
la moindre conclusion.

## Installation

Fonctionne de Python 3.9 à 3.14 (les deux sont testés par la CI).

```bash
python -m venv .venv
```

Active ensuite l'environnement virtuel — `source .venv/bin/activate` sur
macOS ou Linux, `.venv\\Scripts\\activate` sur Windows — puis installe les
dépendances :

```bash
python -m pip install -r requirements.txt
```

Sur macOS, l'entraînement du modèle (xgboost) demande en plus
`brew install libomp`.

`openpyxl` est inclus dans les dépendances d'exécution : il est nécessaire à
Pandas pour lire les fichiers Excel `.xlsx` importés dans l'application. Si
les autres dépendances sont déjà installées, tu peux aussi corriger
l'environnement actuel avec `python -m pip install openpyxl`.

Pour lancer les tests, installe en plus les dépendances de développement :

```bash
python -m pip install -r requirements-dev.txt
```

Toutes les commandes ci-dessous passent par `python -m ...`, environnement
virtuel activé : la même ligne fonctionne sur macOS, Linux et Windows.

## Utilisation

**Lancer l'application :**

```bash
python -m streamlit run app.py
```

Elle lit les historiques `.xlsx` du dossier `data/` (un fichier par titre ;
un nouveau titre peut aussi être importé depuis la barre latérale). Les
colonnes sont détectées automatiquement, en français comme en anglais (voir
`COLUMN_CANDIDATES` dans `services/market_data.py`), et les nombres au format
francophone (virgule décimale, espace comme séparateur de milliers) sont
tolérés.

**Entraîner (ou réentraîner) le modèle ML :**

```bash
python -m training.train
```

Empile tous les titres de `data/`, calcule les indicateurs, sélectionne le
meilleur modèle par validation croisée glissante, puis sauvegarde dans
`models/` :

- `financial_model.pkl` — le modèle calibré (probabilités utilisables telles
  quelles)
- `features.pkl` — la liste des variables attendues, dans l'ordre
- `metadata.json` — date d'entraînement, modèle retenu, score sur le test,
  et si la référence naïve ("toujours répondre baisse") est battue ; affiché
  dans l'application sous le résultat de l'analyse

**Lancer les tests :**

```bash
python -m pytest
```

Les tests incluent un test de fumée (`tests/test_app_smoke.py`) qui lance
réellement chaque page : c'est lui qui signale une fonction Streamlit
absente de la version installée.

**Rejouer les signaux techniques sur l'historique :**

```bash
python -m training.backtest_engine
```

Montre ce que le cours a fait après chaque signal (tableau repris dans la
page Journal).

**Activer l'assistant conversationnel (facultatif) :**

La page Analyse propose, sous le résultat, de poser des questions à un
assistant qui explique la décision. Il passe par l'API Claude (service
payant, facturé à l'usage) et demande une clé, à définir avant de lancer
l'application :

```bash
export ANTHROPIC_API_KEY=...
```

Sans clé, tout le reste fonctionne, y compris l'assistant vocal qui lit le
résultat (synthèse vocale du navigateur, gratuite).

## Structure du projet

```
app.py                  Point d'entrée Streamlit : marque, navigation,
                          import de structures, sélection de structure
app_pages/
  analyse.py              Cours, graphique, comparaison à l'indice,
                            décision, assistants vocal et conversationnel
  marche.py               Signal de chaque structure, « Quoi de neuf »
  portefeuille.py         Lignes détenues, plus-value, dividendes, frais
  dividendes.py           Rendement et calendrier des détachements
  journal.py              Analyses passées confrontées au cours réel,
                            backtest des signaux (5, 20, 60 séances)
  parametres.py           Palette, indicateurs, dividendes, jours fériés,
                            indice de référence, frais de courtage
config.py               Chemins, logging, valeurs par défaut partagées
services/
  market_data.py          Chargement/normalisation des historiques Excel,
                            dividendes, import
  indicators.py           Indicateurs techniques et lecture des extrêmes
                            calibrée titre par titre
  decision_engine.py      Score technique + ML pondéré -> décision
  analysis.py             Analyse d'une séance, partagée entre les pages
  backtest.py             Rejeu des signaux sur l'historique
  predictor.py            Chargement du modèle et prédiction
  portfolio.py            Positions saisies et leur valorisation
  trading_calendar.py     Jours fériés BRVM
  prediction_log.py       Journal des analyses
  narration.py, avatar.py Assistant vocal
  assistant_chat.py       Assistant conversationnel (API Claude)
  loaders.py              Chargements Streamlit mis en cache
  themes.py               Palettes de couleurs
training/
  train.py                Entraînement du modèle ML (CLI)
  walk_forward.py         Stabilité du modèle dans le temps (CLI)
  backtest_engine.py      Backtest des signaux techniques (CLI)
tests/                  Tests pytest, dont un test de fumée des pages
data/                   Historiques .xlsx, portefeuille et réglages
                          (non versionnés), registre des structures et
                          jours fériés saisis
models/                 Modèle entraîné (non versionné, régénérable)
results/                Sorties d'entraînement, backtest, journal
```

## Limites connues

- **Peu de données** : le modèle partagé est entraîné sur les titres présents
  dans `data/` (quelques centaines de lignes au total à ce jour). Son pouvoir
  prédictif réel reste faible — regarde `models/metadata.json` après chaque
  entraînement pour voir s'il bat la référence naïve sur le test, pas
  seulement l'accuracy brute.
- **Moteur de décision heuristique** : les poids de `decision_engine.py`
  restent des conventions. Le backtest (`python -m training.backtest_engine`,
  repris dans la page Journal) montre que seuls les extrêmes du RSI et de
  Bollinger ont été suivis de mouvements nets, et dans un sens qui dépend du
  titre : ils sont donc lus titre par titre, d'après l'historique de chacun
  (`calibrate_extremes`). MM20, MACD et momentum n'ont presque pas départagé
  hausses et baisses sur les titres actuels ; le score global discrimine
  donc peu.
- **Modèle ML exclu du score tant qu'il ne bat pas la référence naïve** : il
  reste affiché à titre indicatif.
- **Dividendes saisis à la main** : les dates ex-dividende et montants se
  renseignent par structure dans Paramètres (stockés dans
  `data/structures.json`). L'historique antérieur à un détachement est alors
  recalé avant le calcul des indicateurs, à l'entraînement comme dans l'app ;
  la date butoir d'achat ne tient compte que des week-ends, pas des jours
  fériés BRVM.
- **Pas de flux de données en direct** : les cotations s'importent
  manuellement (fichier Excel), il n'y a pas de connexion à un flux BRVM.
- **Fichiers Excel non versionnés** : `data/*.xlsx` est dans `.gitignore`
  (ce sont des données, pas du code) — un clone du dépôt démarre sans
  historique tant qu'on n'en importe pas.
