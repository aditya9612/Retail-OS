"""SMS Provider abstraction and mock implementation.

The application uses this abstraction to send OTP codes via SMS. Only a
development‑time mock is provided at the moment; a real provider can be
added later without changing the authentication logic.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple

from app.core.config import get_settings


class SMSProvider(ABC):
    """Abstract base class for SMS providers.

    Implementations must provide a :meth:`send_otp` method that delivers a
    plain‑text OTP to the given phone number for the specified purpose.
    The method should raise an exception on any failure (network error,
    invalid credentials, rate‑limit, etc.).
    """

    @abstractmethod
    def send_otp(self, phone_number: str, otp: str, purpose: str) -> None:
        """Send an OTP.

        Args:
            phone_number: Canonical phone number (e.g., ``"9876543210"``).
            otp: The plain‑text OTP that will be sent to the user.
            purpose: Logical purpose of the OTP (e.g., ``"mobile_login"``).
        """
        raise NotImplementedError


class MockSMSProvider(SMSProvider):
    """In‑memory mock provider used for tests and development.

    It records each call in a class‑level list so that tests can inspect the
    sent messages without performing any external network activity.
    """

    # Stored as ``List[Tuple[phone_number, otp, purpose]]``
    _sent_messages: List[Tuple[str, str, str]] = []

    def send_otp(self, phone_number: str, otp: str, purpose: str) -> None:
        # Record the call – no external side effects.
        self.__class__._sent_messages.append((phone_number, otp, purpose))

    @classmethod
    def get_sent_messages(cls) -> List[Tuple[str, str, str]]:
        """Return a copy of the recorded messages.

        Tests can clear the list via ``cls._sent_messages.clear()``.
        """
        return list(cls._sent_messages)

    @classmethod
    def clear_sent_messages(cls) -> None:
        cls._sent_messages.clear()


def get_sms_provider() -> SMSProvider:
    """Factory that returns the configured SMS provider.

    The ``SMS_PROVIDER`` setting selects the implementation. Currently only
    ``"mock"`` is supported. Adding a real provider only requires adding a new
    class that implements :class:`SMSProvider` and extending this factory.
    """
    settings = get_settings()
    provider_name = getattr(settings, "SMS_PROVIDER", "mock").lower()
    if provider_name == "mock":
        return MockSMSProvider()
    # Placeholder for future providers – raise a clear error.
    raise NotImplementedError(f"SMS provider '{provider_name}' is not implemented")
