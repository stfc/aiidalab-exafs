"""Common navigation helpers for the AiiDAlab FEFF wizard."""

from __future__ import annotations

from typing import TYPE_CHECKING

import ipywidgets as ipw
from aiida.orm import ProcessNode, load_node

if TYPE_CHECKING:
    from aiidalab.widgets import WizardAppWidget


def create_new_calculation_button(wizard: WizardAppWidget) -> ipw.Button:
    """Create a "New calculation" button that resets the wizard."""
    button = ipw.Button(
        description="New calculation",
        button_style="primary",
        icon="plus",
        layout={"width": "140px"},
    )

    def _on_click(_):
        wizard.reset()

    button.on_click(_on_click)
    return button


def create_load_from_pk_button(
    wizard: WizardAppWidget,
    submission_model,
) -> tuple[ipw.HBox, ipw.Text]:
    """Create a "Load from PK" input box with a load button."""
    pk_input = ipw.Text(
        placeholder="Process PK",
        description="Load PK:",
        layout={"width": "220px"},
    )
    load_button = ipw.Button(
        description="Load",
        button_style="info",
        icon="refresh",
        layout={"width": "80px"},
    )

    def _on_click(_):
        try:
            pk = int(pk_input.value)
        except ValueError:
            submission_model.process_node = None
            return
        try:
            node = load_node(pk)
        except Exception:
            submission_model.process_node = None
            return
        if isinstance(node, ProcessNode):
            # Start from a clean slate so previously-displayed structures,
            # results, and status widgets are hidden before loading the
            # requested process. reset() empties the submission model, so we
            # set the node afterwards to trigger the process monitor.
            wizard.reset()
            submission_model.process_node = node

    load_button.on_click(_on_click)
    return ipw.HBox([pk_input, load_button]), pk_input


def make_step_header(title: str) -> ipw.HTML:
    """Return a consistent header widget for a wizard step."""
    return ipw.HTML(f"<h2>{title}</h2>")
