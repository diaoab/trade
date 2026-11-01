# Financial AI Advisor

Assistant expérimental d'analyse technique et de prédiction pour des titres
cotés (historiques Excel, format BRVM). Combine des indicateurs techniques
classiques (moyennes mobiles, RSI, MACD, Bollinger), un modèle de machine
learning entraîné sur l'ensemble des titres disponibles, et un moteur de
décision qui pondère les deux.

Le projet est réparti en trois dossiers voisins :

- `trade_back` (ce dossier) : cœur métier (`core/engine/`, `core/constants.py`),
  entraînement du modèle, API FastAPI, données et modèle ;
- `trade_admin` : back-office React (comptes, paiements, historiques, modèle),
  branché sur l'API ;
- `trade_mobile` : app Expo (iPhone, Android, web) branchée sur l'API.

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

**Lancer le back-office :** voir `../trade_admin/README.md`.

Les historiques `.xlsx` sont lus dans le dossier `data/` (un fichier par
titre). Les
colonnes sont détectées automatiquement, en français comme en anglais (voir
`COLUMN_CANDIDATES` dans `core/engine/market_data.py`), et les nombres au format
francophone (virgule décimale, espace comme séparateur de milliers) sont
tolérés.

**Entraîner (ou réentraîner) le modèle ML :**

```bash
python -m core.training.train
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

**Rejouer les signaux techniques sur l'historique :**

```bash
python -m core.training.backtest_engine
```

Montre ce que le cours a fait après chaque signal (tableau repris dans la
page Journal).

**Activer l'assistant conversationnel (facultatif) :**

L'API propose de poser des questions à
un assistant qui explique la décision. Il passe par l'API Claude (service
payant, facturé à l'usage) et demande une clé, à définir avant de lancer
l'application :

```bash
export ANTHROPIC_API_KEY=...
```

Sans clé, tout le reste fonctionne, y compris l'assistant vocal qui lit le
résultat (synthèse vocale du navigateur, gratuite).

## Structure du projet

```
core/                   Cœur métier, sans base de données ni HTTP
  constants.py            Chemins, logging, valeurs par défaut partagées
  engine/
    market_data.py          Chargement/normalisation des historiques Excel,
                              dividendes, import
    indicators.py           Indicateurs techniques et lecture des extrêmes
                              calibrée titre par titre
    decision_engine.py      Score technique + ML pondéré -> décision
    analysis.py             Analyse d'une séance
    backtest.py             Rejeu des signaux sur l'historique
    predictor.py            Chargement du modèle et prédiction
    portfolio.py            Positions saisies et leur valorisation
    trading_calendar.py     Jours fériés BRVM
    prediction_log.py       Journal des analyses
    narration.py            Texte lu par l'assistant vocal
    assistant_chat.py       Assistant conversationnel (API Claude)
  training/
    train.py                Entraînement du modèle ML (CLI)
    walk_forward.py         Stabilité du modèle dans le temps (CLI)
    backtest_engine.py      Backtest des signaux techniques (CLI)
api/                    API FastAPI, même découpage que le back Sign
                          (voir plus bas) ; importe core, jamais l'inverse
deploy/                 Nginx, installation du VPS, déploiement,
                          sauvegardes, crontab, initdb Postgres
tests/core/             Tests pytest du cœur métier
tests/api/              Tests pytest de l'API
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
  restent des conventions. Le backtest (`python -m core.training.backtest_engine`,
  repris dans la page Journal) montre que seuls les extrêmes du RSI et de
  Bollinger ont été suivis de mouvements nets, et dans un sens qui dépend du
  titre : ils sont donc lus titre par titre, d'après l'historique de chacun
  (`calibrate_extremes`). MM20, MACD et momentum n'ont presque pas départagé
  hausses et baisses sur les titres actuels ; le score global discrimine
  donc peu.
- **Modèle ML exclu du score tant qu'il n'a pas fait ses preuves** : il doit
  battre la meilleure réponse constante sur le test *et* atteindre un ROC AUC
  de 0,55. Il prévoit la performance à 60 séances, seul horizon où il dépasse
  le hasard année après année (0,60 en validation croisée), mais il retombe
  à 0,50 sur la dernière période (2024-2025) : il reste donc affiché à titre
  indicatif. Un ROC AUC de 0,98 n'est pas un objectif atteignable sur des
  cours de bourse ; un tel score signalerait une fuite de données.
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

## Service en ligne (API + app mobile)

`api/` est une API FastAPI multi-utilisateurs (comptes, portefeuille et
réglages par personne, quota de questions à l'assistant, abonnement Pro)
qui réutilise `core/engine/`. `../trade_mobile` (app Expo pour iPhone, Android
et le web) la consomme.

### Organisation

Même découpage que le back Node de Sign : chaque requête traverse
route → middlewares → controller → service → modèle.

```
api/
  main.py          Application : middlewares, erreurs, /health, routes
  config/          settings (variables d'environnement), security
                     (limites de débit, CORS), db (session SQLAlchemy)
  routes/          Déclaration des routes, sous /trade/v1
  controllers/     Lecture de la requête, mise en forme de la réponse
                     (admin/ : back-office, idem pour routes/ et services/)
  services/        Logique métier (auth, jetons, compte, marché,
                     assistant, portefeuille, paiement, admin)
  models/          Tables SQLAlchemy (un fichier par table)
  validations/     Corps de requête attendus (Pydantic), un fichier
                     par domaine (auth, account, market, portfolio, billing)
  middlewares/     Authentification, clé admin, limites de débit,
                     journal des requêtes, gestion centralisée des erreurs
  errors/          AppError et ses sous-classes (400, 401, 403...)
  utils/           Format des réponses, logger, format_user
  migrations/      Migrations Alembic
  jobs/            Tâches planifiées (cours du soir, purge des jetons)
  scripts/         seed_dev (comptes de démonstration locaux), list_users,
                     grant_admin, grant_pro, reset_password
```

Toutes les réponses JSON ont la même forme :

```json
{ "success": true,  "message": "Connexion réussie", "data": { ... } }
{ "success": false, "message": "Données invalides", "details": ["email : ..."] }
```

### Routes (préfixe `/trade/v1`)

| Route | Rôle |
|---|---|
| `POST /auth/register`, `POST /auth/login` | Création de compte, connexion : `token` (accès, 60 min) + `refresh_token` (30 j) |
| `POST /auth/refresh` | Nouvelle paire de jetons ; l'ancien `refresh_token` est révoqué (réutilisé → toutes les sessions fermées) |
| `POST /auth/logout`, `PUT /auth/password` | Déconnexion d'un appareil, changement de mot de passe (ferme les autres sessions) |
| `GET/DELETE /account/me`, `GET/PUT /account/preferences` | Profil, suppression du compte, réglages d'analyse |
| `GET /market`, `GET /structures`, `GET /structures/{symbol}/analysis` | Vue du marché, liste des titres, analyse détaillée |
| `POST /structures/{symbol}/assistant` | Question à l'assistant (quota quotidien selon l'offre) |
| `GET /portfolio`, `POST /portfolio/positions`, `DELETE /portfolio/positions/{id}` | Portefeuille |
| `GET /billing/offer`, `POST /billing/checkout`, `POST /billing/confirm` | Offre Pro et paiement PayDunya |
| `GET /billing/return`, `POST /billing/ipn` | Retour du client et notification PayDunya |
| `GET /admin/stats` | Indicateurs du tableau de bord du back-office |
| `GET /admin/users`, `GET/PATCH /admin/users/{id}`, `POST /admin/users/{id}/revoke-sessions` | Comptes (recherche, pagination), offre Pro offerte, rôle, déconnexion forcée |
| `GET /admin/payments` | Paiements PayDunya |
| `GET/POST /admin/structures`, `POST /admin/refresh`, `POST /admin/retrain`, `GET /admin/model` | Historiques, import, cours du jour, réentraînement, état du modèle |

Les routes `/admin` acceptent le jeton d'un compte au rôle `admin` (back-office)
ou l'en-tête `X-Admin-Key` (tâches planifiées, curl). Modifier un compte exige
un compte admin : on sait ainsi qui a fait quoi. Le rôle ne s'attribue jamais
par l'API publique, seulement par `python -m api.scripts.grant_admin <email>`.

`GET /health` (hors préfixe) vérifie aussi la base.

### En local

```bash
python -m alembic upgrade head
python -m api.scripts.seed_dev
python -m uvicorn api.main:app --reload
```

`seed_dev` crée un compte de démonstration et un compte du back-office
(identifiants affichés). Scripts de gestion des comptes : `list_users`,
`grant_admin`, `grant_pro`, `reset_password` (`python -m api.scripts.<nom>`).

SQLite par défaut (`data/saas.db`), documentation sur
http://127.0.0.1:8000/docs. Pour une base créée avant les migrations :
`python -m alembic stamp 0001 && python -m alembic upgrade head`.
Avec PostgreSQL : `docker compose up --build`.

Après un changement de modèle (`api/models/`), générer la migration :
`python -m alembic revision --autogenerate -m "description"` ; le test
`test_migrations_match_models` échoue tant qu'elle manque.

### Production (VPS)

Toutes les variables sont listées dans [.env.example](.env.example). Avec
`ENV=production`, l'API refuse de démarrer sans `JWT_SECRET` et
`JWT_REFRESH_SECRET` distincts, sans PostgreSQL, ou avec `CORS_ORIGINS=*`.

1. Sur un VPS Ubuntu neuf : `sudo bash deploy/setup-server.sh --domain api.exemple.com`
   (Docker, Nginx, pare-feu, certificat Let's Encrypt).
2. `git clone` dans `/var/www/trade-api`, `cp .env.example .env`, remplir.
3. `docker compose -f docker-compose.prod.yml up -d --build` : PostgreSQL
   et l'API (migrations appliquées au démarrage), publiée sur
   `127.0.0.1:8000` derrière Nginx.
4. `crontab deploy/crontab` : cours du soir et réentraînement (lundi-vendredi
   18 h 30 UTC), purge des jetons expirés, sauvegarde quotidienne de la base
   et des données (`deploy/backup-postgres.sh`, copie Google Drive si rclone
   est configuré).
5. Créer le premier administrateur (compte inscrit depuis l'app) :
   `docker compose -f docker-compose.prod.yml exec backend python -m api.scripts.grant_admin moi@exemple.com`,
   puis déployer le back-office (`../trade_admin/README.md`).
6. Importer les historiques puis entraîner le modèle (depuis le back-office,
   ou en curl) :
   ```bash
   curl -X POST "https://api.exemple.com/trade/v1/admin/structures?name=PALM%20CI" \
        -H "X-Admin-Key: $ADMIN_API_KEY" --data-binary @PALM_CI.xlsx
   curl -X POST "https://api.exemple.com/trade/v1/admin/retrain" -H "X-Admin-Key: $ADMIN_API_KEY"
   ```

Ensuite, chaque push sur `main` dont la CI passe est déployé par
`.github/workflows/deploy.yml` (secrets `VPS_HOST`, `VPS_USER`,
`VPS_SSH_KEY`) ; `bash deploy/deploy.sh` fait la même chose à la main.

- **Paiement** : offre Pro payée par PayDunya (`api/services/paydunya.py`).
  Renseigner les clés `PAYDUNYA_*` (mode `test` d'abord) ; chaque paiement
  prolonge l'offre de `PRO_DAYS` jours.
- **Cours** : import d'un classeur par `POST /admin/structures`, ou flux
  quotidien d'un fournisseur (`QUOTES_FEED_URL`, `api/services/quotes_feed.py`).
- **App** : la version web et les builds iPhone/Android sont dans
  `../trade_mobile` (`eas.json`).
