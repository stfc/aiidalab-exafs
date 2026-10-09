"""Design tokens and CSS styling for the AiiDAlab EXAFS app."""

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
  --exafs-ink: var(--jp-ui-font-color1, #1F2933);
  --exafs-ink-muted: var(--jp-ui-font-color2, #52606D);
  --exafs-surface: var(--jp-layout-color2, #F4F6F8);
  --exafs-surface-elevated: var(--jp-layout-color1, #FFFFFF);
  --exafs-rule: var(--jp-border-color2, #D5DBE1);
  --exafs-rule-light: var(--jp-border-color1, #E4E7EB);
  --exafs-accent: var(--jp-brand-color1, #1B5E9B);
  --exafs-accent-hover: #144978;
  --exafs-success: var(--jp-success-color1, #2E7D4F);
  --exafs-caution: var(--jp-warn-color1, #B26A00);
  --exafs-danger: var(--jp-error-color1, #C52707);
  --exafs-font: var(--jp-ui-font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif);

  /* Backward compatibility aliases */
  --feff-ink: var(--exafs-ink);
  --feff-ink-muted: var(--exafs-ink-muted);
  --feff-surface: var(--exafs-surface);
  --feff-surface-elevated: var(--exafs-surface-elevated);
  --feff-rule: var(--exafs-rule);
  --feff-rule-light: var(--exafs-rule-light);
  --feff-accent: var(--exafs-accent);
  --feff-accent-hover: var(--exafs-accent-hover);
  --feff-success: var(--exafs-success);
  --feff-caution: var(--exafs-caution);
  --feff-danger: var(--exafs-danger);
  --feff-font: var(--exafs-font);
}

.exafs-app, .feff-app {
  font-family: var(--exafs-font);
  color: var(--exafs-ink);
  line-height: 1.5;
}

.exafs-tabular-num, .exafs-tabular-num input,
.feff-tabular-num, .feff-tabular-num input {
  font-variant-numeric: tabular-nums !important;
  text-align: right !important;
}

/* Stepper breadcrumbs */
.exafs-stepper, .feff-stepper {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0 14px 0;
  border-bottom: 1px solid var(--exafs-rule);
  margin-bottom: 16px;
}

.exafs-step-btn, .feff-step-btn {
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

.exafs-step-btn.exafs-step-active, .feff-step-btn.feff-step-active {
  background-color: var(--exafs-accent) !important;
  color: #ffffff !important;
  border: 1px solid var(--exafs-accent) !important;
  font-weight: 600 !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12) !important;
}

.exafs-step-btn.exafs-step-completed, .feff-step-btn.feff-step-completed {
  background-color: var(--exafs-surface-elevated) !important;
  color: var(--exafs-ink) !important;
  border: 1px solid var(--exafs-rule) !important;
}

.exafs-step-btn.exafs-step-completed:hover, .feff-step-btn.feff-step-completed:hover {
  border-color: var(--exafs-accent) !important;
  color: var(--exafs-accent) !important;
}

.exafs-step-btn.exafs-step-upcoming, .feff-step-btn.feff-step-upcoming {
  background-color: var(--exafs-surface) !important;
  color: var(--exafs-ink-muted) !important;
  border: 1px dashed var(--exafs-rule) !important;
  opacity: 0.75 !important;
}

/* Action bar at the bottom of each view */
.exafs-action-bar, .feff-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0 6px 0;
  margin-top: 20px;
  border-top: 1px solid var(--exafs-rule);
  gap: 12px;
  flex-wrap: wrap;
}

.exafs-card, .feff-card {
  background: var(--exafs-surface);
  border: 1px solid var(--exafs-rule);
  border-radius: 6px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.exafs-card-title, .feff-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--exafs-ink);
  margin-bottom: 8px;
}

/* Hide stray matplotlib header / figure number */
.jupyter-matplotlib-figure .ui-dialog-titlebar,
.jupyter-matplotlib-header,
.ipympl-header {
  display: none !important;
}

/* Table styles */
.exafs-table-header, .feff-table-header {
  background: var(--exafs-surface);
  color: var(--exafs-ink);
  font-weight: 600;
  border-bottom: 2px solid var(--exafs-rule);
}

.exafs-table-row, .feff-table-row {
  border-bottom: 1px solid var(--exafs-rule-light);
  transition: background 0.1s ease;
}

.exafs-table-row:hover, .feff-table-row:hover {
  background: var(--exafs-surface) !important;
}

.exafs-table-row.selected, .feff-table-row.selected {
  background: #EBF4FF !important;
}

/* Badge styles */
.exafs-badge, .feff-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.exafs-badge-running, .feff-badge-running {
  background: #E3F2FD;
  color: #0D47A1;
}
.exafs-badge-done, .feff-badge-done {
  background: #E8F5E9;
  color: #1B5E20;
}
.exafs-badge-failed, .feff-badge-failed {
  background: #FFEBEE;
  color: #B71C1C;
}

/* Cost preview callout */
.exafs-cost-callout, .feff-cost-callout {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--exafs-surface);
  border-left: 3px solid var(--exafs-accent);
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--exafs-ink);
  margin: 8px 0;
}
</style>
"""


def get_style_widget() -> ipw.HTML:
    """Return an HTML widget injecting the global CSS styling."""
    return ipw.HTML(APP_CSS)
