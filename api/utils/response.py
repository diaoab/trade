"""Reponses API coherentes.

Succes : { success: true,  message, data }
Erreur : { success: false, message, details? }  (cf. error_handler)

Usage dans un controller :
    return ok(data, "Profil récupéré")
"""

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from api.services.market_service import to_json


def ok(data=None, message="Succès", status_code=200):

    return JSONResponse(
        status_code=status_code,
        content={"success": True, "message": message, "data": jsonable_encoder(to_json(data))}
    )


def created(data=None, message="Créé avec succès"):
    return ok(data, message, status_code=201)


def fail(message, status_code=400, details=None, headers=None):

    content = {"success": False, "message": message}

    if details:
        content["details"] = details

    return JSONResponse(status_code=status_code, content=content, headers=headers)
