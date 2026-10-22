"""Seasonal date windows.

A season whose months cross a calendar year is labelled with the year in which it ends:
dry season 2020 = 2019-11-01 .. 2020-03-31.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from indus_delta.config import SeasonConfig


@dataclass(frozen=True)
class SeasonWindow:
    season: str
    label_year: int
    start: date  # inclusive
    end: date  # exclusive

    def completeness(self, data_end: date) -> str:
        """'complete', 'partial' or 'not_started' given the last date with available data."""
        if data_end < self.start:
            return "not_started"
        return "complete" if data_end >= self.end else "partial"


def season_window(name: str, season: SeasonConfig, label_year: int) -> SeasonWindow:
    first, last = season.months[0], season.months[-1]
    crosses_year = last < first
    start_year = label_year - 1 if crosses_year else label_year
    end = date(label_year + 1, 1, 1) if last == 12 else date(label_year, last + 1, 1)
    return SeasonWindow(name, label_year, date(start_year, first, 1), end)
