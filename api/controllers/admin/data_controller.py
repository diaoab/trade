from fastapi import BackgroundTasks, Request

from api.services.admin import data_service
from api.utils.response import ok


async def upload_structure(name: str, request: Request):
    """Importe ou complete l'historique d'un titre : corps de la requete =
    le classeur .xlsx. Exemple :
    curl -X POST "$API/trade/v1/admin/structures?name=PALM%20CI" \
         -H "X-Admin-Key: $ADMIN_API_KEY" --data-binary @PALMCI.xlsx
    """

    report = data_service.upload_structure(name, await request.body())

    return ok(report, "Historique importé")


def refresh(background: BackgroundTasks, retrain: bool = False):
    """Cours du jour depuis le flux ; retrain=true relance ensuite
    l'entrainement du modele en arriere-plan."""

    report = data_service.refresh_quotes()

    if retrain:
        background.add_task(data_service.retrain)

    return ok({"structures": report, "retrain": retrain}, "Cours mis à jour")


def retrain(background: BackgroundTasks):
    """Relance l'entrainement du modele en arriere-plan (quelques minutes),
    par exemple apres le premier import des historiques."""

    background.add_task(data_service.retrain)

    return ok({"retrain": True}, "Entraînement lancé")


def list_structures():

    return ok(data_service.list_structures(), "Historiques récupérés")


def model_status():

    return ok(data_service.model_status(), "État du modèle récupéré")
