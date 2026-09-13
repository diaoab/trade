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

Nécessite Python 3.14 (voir `venv/pyvenv.cfg` pour la version exacte utilisée
en développement).

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Pour lancer les tests, installe en plus les dépendances de développement :

```bash
venv\Scripts\pip install -r requirements-dev.txt
```

> Si `venv` a été copié ou déplacé après sa création, les scripts
> `venv\Scripts\*.exe` (streamlit.exe, pip.exe...) gardent un chemin Python
> figé et échouent avec *"Unable to create process"*. Passe par le module à
> la place (`python -m streamlit run app.py`), ou réinstalle ces scripts avec
> `python -m pip install --force-reinstall --no-deps streamlit`.

## Utilisation

**Lancer l'application :**

```bash
venv\Scripts\streamlit run app.py
```

Elle lit les historiques `.xlsx` du dossier `data/` (un fichier par titre ;
un nouveau titre peut aussi être importé depuis la barre latérale). Les
colonnes sont détectées automatiquement, en français comme en anglais (voir
`COLUMN_CANDIDATES` dans `services/market_data.py`), et les nombres au format
francophone (virgule décimale, espace comme séparateur de milliers) sont
tolérés.

**Entraîner (ou réentraîner) le modèle ML :**

```bash
venv\Scripts\python -m training.train
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
venv\Scripts\pytest
```

## Structure du projet

```
app.py                  Interface Streamlit
config.py                Chemins, logging
services/
  market_data.py         Chargement/normalisation des historiques Excel
  indicators.py           Indicateurs techniques (MM, RSI, MACD, Bollinger...)
  decision_engine.py      Score technique + ML pondéré -> décision
  predictor.py             Chargement du modèle et prédiction
training/
  train.py                 Pipeline d'entraînement (CLI)
tests/                    Tests pytest des modules ci-dessus
data/                     Historiques .xlsx (non versionnés, voir .gitignore)
models/                  Modèle entraîné (non versionné, régénérable)
results/                 Sorties d'entraînement : comparaison de modèles,
                          importance des variables, dataset préparé
```

## Limites connues

- **Peu de données** : le modèle partagé est entraîné sur les titres présents
  dans `data/` (quelques centaines de lignes au total à ce jour). Son pouvoir
  prédictif réel reste faible — regarde `models/metadata.json` après chaque
  entraînement pour voir s'il bat la référence naïve sur le test, pas
  seulement l'accuracy brute.
- **Moteur de décision heuristique** : les poids de `decision_engine.py`
  (croisement de moyennes mobiles, zones RSI...) suivent des conventions
  usuelles d'analyse technique mais n'ont pas été validés par un backtest.
- **Pas de flux de données en direct** : les cotations s'importent
  manuellement (fichier Excel), il n'y a pas de connexion à un flux BRVM.
- **Fichiers Excel non versionnés** : `data/*.xlsx` est dans `.gitignore`
  (ce sont des données, pas du code) — un clone du dépôt démarre sans
  historique tant qu'on n'en importe pas.
