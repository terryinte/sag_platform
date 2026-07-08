from __future__ import annotations

from data_collectors.models import CollectionError


class ProviderError(Exception):
    def __init__(self, provider: str, operation: str, retryable: bool, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.operation = operation
        self.retryable = retryable
        self.message = message

    def to_collection_error(self) -> CollectionError:
        return CollectionError(
            provider=self.provider,
            operation=self.operation,
            retryable=self.retryable,
            message=self.message,
        )
