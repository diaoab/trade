"""Reponses API coherentes.

Succes : { success: true,  message, data }
Erreur : { success: false, message, details? }  (cf. error_handler)

Usage dans un controller :
    return ok(data, "Profil récupéré")
"""

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from api.services.market_service import to_json


def ok(data=None, message="Succès", status_code=200):

    return JSONResponse(
        status_code=status_code,
        content={"success": True, "message": message, "data": jsonable_encoder(to_json(data))}
    )


def _etag_matches(header, etag):
    """If-None-Match contient-il cet ETag ? (comparaison faible : Nginx
    rend les ETag faibles quand il compresse.)"""

    for candidate in header.split(","):

        candidate = candidate.strip()

        if candidate == "*" or candidate.removeprefix("W/").strip('"') == etag:
            return True

    return False


def revalidated(request, etag, compute, message="Succès"):
    """Reponse que le client garde en cache et revalide : 304 sans corps
    (et sans calcul) s'il a deja cette version, sinon ok(compute()).

    etag : empreinte qui change des que la reponse changerait.
    """

    headers = {
        "ETag": f'W/"{etag}"',
        # A revalider a chaque fois ; propre au compte (reglages).
        "Cache-Control": "private, no-cache",
        "Vary": "Authorization"
    }

    if _etag_matches(request.headers.get("if-none-match", ""), etag):
        return Response(status_code=304, headers=headers)

    response = ok(compute(), message)

    response.headers.update(headers)

    return response


def created(data=None, message="Créé avec succès"):
    return ok(data, message, status_code=201)


def fail(message, status_code=400, details=None, headers=None):

    content = {"success": False, "message": message}

    if details:
        content["details"] = details

    return JSONResponse(status_code=status_code, content=content, headers=headers)
