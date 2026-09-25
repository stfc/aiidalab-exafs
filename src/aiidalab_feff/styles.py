"""Design tokens and CSS styling for the AiiDAlab FEFF app (G5)."""

from __future__ import annotations

import ipywidgets as ipw

# Okabe-Ito color-blind safe palette
COLOR_SIMULATION = "#0072B2"  # Blue
COLOR_EXPERIMENTAL = "#000000"  # Black
COLOR_RESIDUAL = "#D55E00"  # Vermilion
COLOR_WINDOW = "#E69F00"  # Amber
COLOR_PALETTE = [
    "#0072B2",  # Blue
    "#D55E00",  # Vermilion
    "#009E73",  # Bluish green
    "#CC79A7",  # Reddish purple
    "#56B4E9",  # Sky blue
    "#E69F00",  # Orange
    "#F0E442",  # Yellow
]

APP_CSS = """
<style>
:root {
  --feff-ink: var(--jp-ui-font-color1, #1F2933);
  --feff-ink-muted: var(--jp-ui-font-color2, #52606D);
  --feff-surface: var(--jp-layout-color2, #F4F6F8);
  --feff-surface-elevated: var(--jp-layout-color1, #FFFFFF);
  --feff-rule: var(--jp-border-color2, #D5DBE1);
  --feff-rule-light: var(--jp-border-color1, #E4E7EB);
  --feff-accent: var(--jp-brand-color1, #1B5E9B);
  --feff-accent-hover: #144978;
  --feff-success: var(--jp-success-color1, #2E7D4F);
  --feff-caution: var(--jp-warn-color1, #B26A00);
  --feff-danger: var(--jp-error-color1, #C52707);
  --feff-font: var(--jp-ui-font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif);
}

.feff-app {
  font-family: var(--feff-font);
  color: var(--feff-ink);
  line-height: 1.5;
}

.feff-tabular-num, .feff-tabular-num input {
  font-variant-numeric: tabular-nums !important;
  text-align: right !important;
}

/* Stepper breadcrumbs */
.feff-stepper {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0 14px 0;
  border-bottom: 1px solid var(--feff-rule);
  margin-bottom: 16px;
}

.feff-step-btn {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 5px 14px !important;
  border-radius: 16px !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  white-space: nowrap !important;
  cursor: pointer !important;
  transition: all 0.15s ease-in-out !important;
}

.feff-step-btn.feff-step-active {
  background-color: var(--feff-accent) !important;
  color: #ffffff !important;
  border: 1px solid var(--feff-accent) !important;
  font-weight: 600 !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12) !important;
}

.feff-step-btn.feff-step-completed {
  background-color: var(--feff-surface-elevated) !important;
  color: var(--feff-ink) !important;
  border: 1px solid var(--feff-rule) !important;
}

.feff-step-btn.feff-step-completed:hover {
  border-color: var(--feff-accent) !important;
  color: var(--feff-accent) !important;
}

.feff-step-btn.feff-step-upcoming {
  background-color: var(--feff-surface) !important;
  color: var(--feff-ink-muted) !important;
  border: 1px dashed var(--feff-rule) !important;
  opacity: 0.75 !important;
}

/* Action bar at the bottom of each view */
.feff-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0 6px 0;
  margin-top: 20px;
  border-top: 1px solid var(--feff-rule);
  gap: 12px;
  flex-wrap: wrap;
}

.feff-card {
  background: var(--feff-surface);
  border: 1px solid var(--feff-rule);
  border-radius: 6px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.feff-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--feff-ink);
  margin-bottom: 8px;
}

/* Hide stray matplotlib header / figure number */
.jupyter-matplotlib-figure .ui-dialog-titlebar,
.jupyter-matplotlib-header,
.ipympl-header {
  display: none !important;
}

/* Table styles */
.feff-table-header {
  background: var(--feff-surface);
  color: var(--feff-ink);
  font-weight: 600;
  border-bottom: 2px solid var(--feff-rule);
}

.feff-table-row {
  border-bottom: 1px solid var(--feff-rule-light);
  transition: background 0.1s ease;
}

.feff-table-row:hover {
  background: var(--feff-surface) !important;
}

.feff-table-row.selected {
  background: #EBF4FF !important;
}

/* Badge styles */
.feff-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.feff-badge-running {
  background: #E3F2FD;
  color: #0D47A1;
}
.feff-badge-done {
  background: #E8F5E9;
  color: #1B5E20;
}
.feff-badge-failed {
  background: #FFEBEE;
  color: #B71C1C;
}

/* Cost preview callout */
.feff-cost-callout {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--feff-surface);
  border-left: 3px solid var(--feff-accent);
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--feff-ink);
  margin: 8px 0;
}
</style>
"""


def get_style_widget() -> ipw.HTML:
    """Return an HTML widget injecting the global CSS styling."""
    return ipw.HTML(APP_CSS)
