"""Internal typing aliases for model modules."""

from typing import Protocol


class ActionLike(Protocol):
    action_type: object
    target_zone: str | None

