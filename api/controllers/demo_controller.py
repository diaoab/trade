"""Mode demo de l'app mobile : sans compte, en lecture seule.

Le visiteur voit le Marche et l'Analyse d'un titre avec les reglages par
defaut. Tout ce qui enregistre ou consomme un service (portefeuille,
favoris, alertes, assistant, reglages) reste sur les routes authentifiees.
"""

from fastapi import Request

from api.errors.app_error import ValidationError
from api.services import market_service
from api.services.portfolio_service import require_structure
from api.utils.response import revalidated


def overview(request: Request):

    key = market_service.result_key("market", None)

    return revalidated(request, key, lambda: market_service.market_overview(None, key))


def analysis(symbol: str, request: Request):

    require_structure(symbol)

    key = market_service.result_key("analysis", None, symbol)

    def compute():
        try:
            return market_service.analyse_structure(symbol, None, key)
        except ValueError as error:
            raise ValidationError(str(error))

    return revalidated(request, key, compute)
