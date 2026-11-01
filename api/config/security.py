"""Limites de debit et CORS, regroupees ici comme les autres reglages de
securite. Fenetres de 15 minutes, par IP ou par utilisateur."""

import os

from api.config.settings import CORS_ORIGINS


WINDOW_SECONDS = 15 * 60


def _limit(name, default):
    return int(os.environ.get(name, str(default)))


# Filet de securite global par IP (anti-scan), applique a toutes les routes
# avant meme qu'un utilisateur soit identifie. Volontairement large : sur
# mobile (4G, box partagee), beaucoup de clients partagent une IP.
GLOBAL_RATE_LIMIT = {"max_requests": _limit("RATE_LIMIT_GLOBAL", 1000), "window": WINDOW_SECONDS}

# Par utilisateur authentifie (cle = id du compte, pas l'IP) : couvre l'usage
# normal de l'app (un ecran peut declencher plusieurs appels en parallele).
AUTHENTICATED_RATE_LIMIT = {"max_requests": _limit("RATE_LIMIT_USER", 300), "window": WINDOW_SECONDS}

# Inscription, connexion, rafraichissement : anti force brute, par IP.
AUTH_RATE_LIMIT = {"max_requests": _limit("RATE_LIMIT_AUTH", 10), "window": WINDOW_SECONDS}

# Mutations sensibles (suppression du compte, paiement), par utilisateur.
MUTATION_RATE_LIMIT = {"max_requests": _limit("RATE_LIMIT_MUTATION", 20), "window": WINDOW_SECONDS}

# Retour du client apres paiement (/billing/return), par IP : public, et
# chaque appel interroge PayDunya.
PAYMENT_RETURN_RATE_LIMIT = {"max_requests": _limit("RATE_LIMIT_PAYMENT_RETURN", 30), "window": WINDOW_SECONDS}

# Appels d'administration, par IP.
ADMIN_RATE_LIMIT = {"max_requests": _limit("RATE_LIMIT_ADMIN", 200), "window": WINDOW_SECONDS}


CORS_CONFIG = {
    "allow_origins": CORS_ORIGINS,
    "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH"],
    "allow_headers": ["Content-Type", "Authorization", "X-Admin-Key"],
    # Les jetons passent dans l'en-tete Authorization, pas en cookie : les
    # identifiants du navigateur ne sont pas necessaires (et "*" les interdit).
    "allow_credentials": False
}
