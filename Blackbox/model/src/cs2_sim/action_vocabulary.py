"""Shared, versioned vocabulary for replay actions.

The simulator and replay models must use the same action names.  This module
keeps the names small and canonical while leaving action parameters (such as a
movement destination or grenade type) in separate fields.  Detectors live in
``Blackbox.training.action_labeler`` because they depend on replay-parser data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ACTION_VOCABULARY_SCHEMA_VERSION = "action_vocabulary_v1"


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Describe one canonical action without embedding parser logic."""

    name: str
    family: str
    aliases: tuple[str, ...] = ()
    observed: bool = True
    parameter_names: tuple[str, ...] = ()
    abstract_candidate: bool = False


# Keep this order stable: it is used to generate one-hot model columns.
ACTION_DEFINITIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition("hold", "stationary", aliases=("idle",), abstract_candidate=True),
    ActionDefinition(
        "peek",
        "combat_movement",
        aliases=("swing", "wide_peek"),
        parameter_names=("target_zone",),
        abstract_candidate=True,
    ),
    ActionDefinition(
        "move_to_adjacent_zone",
        "movement",
        aliases=("move", "reposition", "rotate"),
        parameter_names=("target_zone",),
        abstract_candidate=True,
    ),
    ActionDefinition(
        "use_utility",
        "utility",
        aliases=("utility", "grenade"),
        parameter_names=("utility_type",),
    ),
    ActionDefinition("plant", "objective"),
    ActionDefinition("defuse", "objective"),
    # Save is legal in the simulator but is not emitted by the replay labeler
    # until economy/round-context evidence is reliable enough to label it.
    ActionDefinition("save", "economy", observed=False),
    ActionDefinition("unknown", "unknown", observed=True),
)

ACTION_NAMES: tuple[str, ...] = tuple(item.name for item in ACTION_DEFINITIONS)
OBSERVABLE_ACTION_NAMES: tuple[str, ...] = tuple(
    item.name for item in ACTION_DEFINITIONS if item.observed
)
ACTION_FEATURE_NAMES: tuple[str, ...] = tuple(f"action_is_{name}" for name in ACTION_NAMES)
ABSTRACT_CANDIDATE_ACTION_NAMES: tuple[str, ...] = tuple(
    "move" if item.name == "move_to_adjacent_zone" else item.name
    for item in ACTION_DEFINITIONS
    if item.abstract_candidate
)
_DEFINITIONS = {item.name: item for item in ACTION_DEFINITIONS}
_ALIASES = {
    alias: item.name
    for item in ACTION_DEFINITIONS
    for alias in (item.name, *item.aliases)
}


def canonical_action(value: Any, *, default: str = "unknown") -> str:
    """Return a canonical base action name.

    Parameterized movement strings (``move_to_adjacent_zone:A_SITE``) are
    intentionally reduced to their base action here; callers should retain
    the suffix as ``target_zone`` separately.
    """

    text = str(value or "").strip().lower()
    base = text.split(":", 1)[0]
    if base in _ALIASES:
        return _ALIASES[base]
    if base.startswith("move_to_"):
        return "move_to_adjacent_zone"
    return default if default in _DEFINITIONS else "unknown"


def action_parameters(value: Any, parameters: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Extract action parameters without making them additional classes."""

    result = dict(parameters or {})
    text = str(value or "").strip()
    base, separator, suffix = text.partition(":")
    action = canonical_action(base)
    if separator and suffix and action in {"move_to_adjacent_zone", "peek"}:
        result.setdefault("target_zone", suffix.strip() or None)
    return {
        key: value
        for key, value in result.items()
        if value not in (None, "")
    }


def action_family(value: Any) -> str:
    """Return the broad family used for sparse-data backoff."""

    return _DEFINITIONS[canonical_action(value)].family


def action_features(value: Any) -> dict[str, float]:
    """Encode a nominal action as stable one-hot columns.

    One-hot encoding avoids implying that, for example, ``peek`` is halfway
    between ``hold`` and ``plant`` as a numeric action code would.
    """

    action = canonical_action(value)
    return {name: float(name == f"action_is_{action}") for name in ACTION_FEATURE_NAMES}


def action_definition(value: Any) -> ActionDefinition:
    """Return the definition for a canonical or aliased action value."""

    return _DEFINITIONS[canonical_action(value)]


__all__ = [
    "ABSTRACT_CANDIDATE_ACTION_NAMES",
    "ACTION_DEFINITIONS",
    "ACTION_FEATURE_NAMES",
    "ACTION_NAMES",
    "ACTION_VOCABULARY_SCHEMA_VERSION",
    "OBSERVABLE_ACTION_NAMES",
    "ActionDefinition",
    "action_definition",
    "action_family",
    "action_features",
    "action_parameters",
    "canonical_action",
]
