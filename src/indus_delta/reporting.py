"""Plain Markdown tables (no extra dependency)."""

from __future__ import annotations

import math

import pandas as pd


def _fmt(v, floatfmt: str) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, float):
        return format(v, floatfmt)
    return str(v).replace("|", "\\|")


def md_table(df: pd.DataFrame, index: bool = False, floatfmt: str = ".3f") -> str:
    frame = df.reset_index() if index else df
    cols = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join(_fmt(v, floatfmt) for v in row) + " |")
    return "\n".join(lines)
