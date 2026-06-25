from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    number: int
    train_periods: tuple[str, ...]
    validation_period: str
    train_index: pd.Index
    validation_index: pd.Index


def walk_forward_splits(
    periods: pd.Series,
    ordered_periods: list[str],
    min_train_periods: int = 1,
) -> list[WalkForwardFold]:
    normalized = periods.astype(str)
    folds: list[WalkForwardFold] = []
    for validation_position in range(min_train_periods, len(ordered_periods)):
        train_periods = tuple(ordered_periods[:validation_position])
        validation_period = ordered_periods[validation_position]
        train_index = normalized[normalized.isin(train_periods)].index
        validation_index = normalized[normalized == validation_period].index
        if train_index.empty or validation_index.empty:
            raise ValueError(
                f"Empty walk-forward fold for validation period {validation_period}"
            )
        folds.append(
            WalkForwardFold(
                number=len(folds) + 1,
                train_periods=train_periods,
                validation_period=validation_period,
                train_index=train_index,
                validation_index=validation_index,
            )
        )
    if not folds:
        raise ValueError("Walk-forward configuration produced no folds")
    return folds

