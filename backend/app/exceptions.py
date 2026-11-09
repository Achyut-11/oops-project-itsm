class ITSMError(Exception):
    status_code = 500
    default_message = "Internal error"

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(ITSMError):
    status_code = 404
    default_message = "Resource not found"


class IncidentNotFound(NotFoundError):
    default_message = "Incident not found"


class UserNotFound(NotFoundError):
    default_message = "User not found"


class NotificationNotFound(NotFoundError):
    default_message = "Notification not found"


class ValidationError(ITSMError):
    status_code = 400
    default_message = "Invalid input"


class InvalidStateTransition(ValidationError):
    default_message = "Invalid state transition"


class Forbidden(ITSMError):
    status_code = 403
    default_message = "You are not allowed to perform this action"


class Unauthorized(ITSMError):
    status_code = 401
    default_message = "Invalid or missing credentials"


class Conflict(ITSMError):
    status_code = 409
    default_message = "The resource was modified, please refresh and try again"


class NoTechnicianAvailable(ITSMError):
    status_code = 503
    default_message = "No suitable technician is currently available"