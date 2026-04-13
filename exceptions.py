from abc import ABC

class AimHarderError(Exception):
    """Base exception for AimHarder API errors."""
    pass

class ErrorResponse(ABC, AimHarderError):
    key_phrase = None

class TooManyWrongAttempts(ErrorResponse):
    key_phrase = "Too Many Wrong Attempts"

class IncorrectCredentials(ErrorResponse):
    key_phrase = "Incorrect Credentials"

class BookingFailed(AimHarderError):
    pass

class NoBookingGoal(AimHarderError):
    pass

class BoxClosed(AimHarderError):
    pass
