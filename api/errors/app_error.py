"""Erreurs metier de l'API.

Une AppError est attendue : son message part tel quel au client. Toute
autre exception est un bug : journalisee en entier, masquee en production
(cf. api.middlewares.error_handler).
"""


class AppError(Exception):

    status_code = 500

    default_message = "Erreur interne du serveur"

    def __init__(self, message=None, details=None, headers=None):

        self.message = message or self.default_message
        self.details = details or []
        self.headers = headers

        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    default_message = "Requête invalide"


class UnauthorizedError(AppError):
    status_code = 401
    default_message = "Session expirée ou invalide : reconnecte-toi."

    def __init__(self, message=None, details=None):
        super().__init__(message, details, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenError(AppError):
    status_code = 403
    default_message = "Accès refusé"


class NotFoundError(AppError):
    status_code = 404
    default_message = "Ressource introuvable"


class ConflictError(AppError):
    status_code = 409
    default_message = "Cette ressource existe déjà"


class ValidationError(AppError):
    status_code = 422
    default_message = "Données invalides"


class TooManyRequestsError(AppError):
    status_code = 429
    default_message = "Trop de requêtes. Réessaie dans 15 minutes."


class ServiceUnavailableError(AppError):
    status_code = 503
    default_message = "Service temporairement indisponible"


class BadGatewayError(AppError):
    status_code = 502
    default_message = "Réponse invalide d'un service externe"
