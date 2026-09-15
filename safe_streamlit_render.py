"""HTML renderers that avoid Streamlit's native PyArrow dataframe conversion."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st


def _display_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:,.0f}"
        return f"{value:,.3f}".rstrip("0").rstrip(".")
    return str(value)


def render_html_table(frame: pd.DataFrame, maximum_rows: int = 200) -> None:
    """Render a dataframe without passing it through PyArrow."""
    visible = frame.head(maximum_rows)
    headings = "".join(f"<th>{escape(str(column))}</th>" for column in visible.columns)
    rows = []
    for row in visible.itertuples(index=False, name=None):
        cells = "".join(f"<td>{escape(_display_value(value))}</td>" for value in row)
        rows.append(f"<tr>{cells}</tr>")
    st.html(
        f"""
        <style>
          .canopy-table-wrap {{ max-height: 430px; overflow: auto; color: var(--canopy-text, #173f2b); background: var(--canopy-surface, #fff); border: 1px solid var(--canopy-border, #d9e0d8); border-radius: 9px; }}
          .canopy-table {{ width: 100%; border-collapse: collapse; color: inherit; font: 13px/1.45 system-ui, sans-serif; }}
          .canopy-table th {{ position: sticky; top: 0; z-index: 1; background: var(--canopy-surface-strong, #edf2eb); color: var(--canopy-text, #173f2b); text-align: left; }}
          .canopy-table th, .canopy-table td {{ padding: 8px 10px; border-bottom: 1px solid var(--canopy-border, #e3e8e2); white-space: nowrap; }}
          .canopy-table tr:nth-child(even) td {{ background: var(--canopy-accent-soft, #fafbf8); }}
        </style>
        <div class="canopy-table-wrap" role="region" aria-label="FVS result table" tabindex="0">
          <table class="canopy-table"><thead><tr>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table>
        </div>
        """
    )


def render_html_bar_chart(frame: pd.DataFrame, category_column: str, value_column: str) -> None:
    """Render an acreage bar chart as HTML/CSS without PyArrow or Vega."""
    if frame.empty:
        return
    values = pd.to_numeric(frame[value_column], errors="coerce").fillna(0.0)
    maximum = float(values.max()) or 1.0
    bars = []
    for category, value in zip(frame[category_column], values):
        height = max(1.0, float(value) / maximum * 100.0)
        label = escape(_display_value(category))
        formatted_value = escape(f"{float(value):,.1f} acres")
        bars.append(
            f"""
            <div class="canopy-bar-item" title="{label}: {formatted_value}">
              <div class="canopy-bar-value">{formatted_value}</div>
              <div class="canopy-bar-track"><div class="canopy-bar" style="height:{height:.3f}%"></div></div>
              <div class="canopy-bar-label">{label}</div>
            </div>
            """
        )
    minimum_width = max(760, len(bars) * 34)
    st.html(
        f"""
        <style>
          .canopy-chart-scroll {{ overflow-x: auto; color: var(--canopy-text, #173f2b); background: var(--canopy-surface, #fff); border: 1px solid var(--canopy-border, #d9e0d8); border-radius: 9px; padding: 14px 12px 6px; }}
          .canopy-chart {{ display: flex; align-items: end; gap: 5px; height: 365px; min-width: {minimum_width}px; }}
          .canopy-bar-item {{ flex: 1 0 27px; min-width: 27px; height: 100%; display: grid; grid-template-rows: 28px 1fr 54px; }}
          .canopy-bar-value {{ font: 9px system-ui, sans-serif; color: var(--canopy-muted, #5b6b60); writing-mode: vertical-rl; overflow: hidden; opacity: 0; }}
          .canopy-bar-item:hover .canopy-bar-value {{ opacity: 1; }}
          .canopy-bar-track {{ display: flex; align-items: end; min-height: 0; border-bottom: 1px solid var(--canopy-muted, #8a998e); }}
          .canopy-bar {{ width: 100%; min-height: 1px; background: var(--canopy-accent, #4f8a5b); }}
          .canopy-bar-label {{ padding-top: 7px; font: 10px system-ui, sans-serif; color: var(--canopy-text, #33463a); writing-mode: vertical-rl; overflow: hidden; }}
        </style>
        <div class="canopy-chart-scroll" role="img" aria-label="Sum of acres by {escape(category_column)}">
          <div class="canopy-chart">{''.join(bars)}</div>
        </div>
        """
    )
