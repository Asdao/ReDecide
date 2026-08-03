"""Factory for selecting the small or full model profile."""

from typing import Literal, overload

from .full import FullLightGBMModel
from .small import SmallStatisticalModel

ModelProfile = Literal["small", "full"]


@overload
def create_model(profile: Literal["small"]) -> SmallStatisticalModel: ...


@overload
def create_model(profile: Literal["full"]) -> FullLightGBMModel: ...


def create_model(profile: ModelProfile):
    """Create a model while keeping the analyser's policy interface unchanged."""

    if profile == "small":
        return SmallStatisticalModel()
    if profile == "full":
        return FullLightGBMModel()
    raise ValueError(f"unknown model profile: {profile!r}")

