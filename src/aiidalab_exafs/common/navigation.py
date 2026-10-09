"""Common navigation helpers for the AiiDAlab FEFF wizard."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import ipywidgets as ipw
from aiida.orm import ProcessNode, load_node
from alc_aiidalab_widgets.widgets.mesages import MessageBox

if TYPE_CHECKING:
    from aiidalab.widgets import WizardAppWidget


def create_new_calculation_button(
    wizard: WizardAppWidget,
    description: str = "Start over",
) -> ipw.Widget:
    """Create a "Start over" button that confirms and resets the wizard."""
    button = ipw.Button(
        description=description,
        button_style="",
        icon="undo",
        tooltip="Reset all inputs and progress to start over",
        layout={"width": "auto", "min_width": "110px"},
    )
    button.add_class("feff-btn-secondary")
    container = ipw.VBox([button])
    container.click = button.click

    def _on_click(_):
        has_input_state = hasattr(wizard, "input_model") and (
            wizard.input_model.structure is not None
            or wizard.input_model.trajectory is not None
            or bool(getattr(wizard.input_model, "structures", None))
        )
        has_sub_state = (
            hasattr(wizard, "submission_model")
            and getattr(wizard.submission_model, "process_node", None) is not None
        )

        if not (has_input_state or has_sub_state):
            wizard.reset()
            return

        msg_box = MessageBox(
            "Start over? Current inputs and progress will be reset.",
            layout={"margin": "4px 0"},
        )

        def _on_decision(change):
            if change["new"] is True:
                container.children = [button]
                wizard.reset()
            elif change["new"] is False:
                container.children = [button]

        msg_box.observe(_on_decision, names="state")
        container.children = [button, msg_box]

    button.on_click(_on_click)
    return container


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


def create_breadcrumbs(
    labels: list[str],
    on_select: Callable[[int], None],
) -> tuple[ipw.HBox, list[ipw.Button]]:
    """Create a clickable breadcrumb row for wizard steps.

    Returns the container and the step buttons (in order) so the caller can
    update their highlight state as the current step changes.
    """
    buttons: list[ipw.Button] = []
    children: list = []
    for index, label in enumerate(labels):
        if index:
            children.append(
                ipw.HTML(
                    '<span style="color:var(--feff-rule, #ccc);margin:0 4px;font-size:14px;">›</span>'
                )
            )
        button = ipw.Button(
            description=label,
            layout=ipw.Layout(width="auto", height="30px", min_width="80px"),
        )
        button.add_class("feff-step-btn")
        button.on_click(lambda _, index=index: on_select(index))
        buttons.append(button)
        children.append(button)
    container = ipw.HBox(
        children,
        layout=ipw.Layout(margin="4px 0 12px 0", align_items="center", flex_flow="row wrap"),
    )
    container.add_class("feff-stepper")
    return container, buttons


def update_breadcrumbs(buttons: list[ipw.Button], current_step: int) -> None:
    """Update breadcrumb buttons based on the active step."""
    for index, button in enumerate(buttons):
        if index == current_step:
            button.button_style = "primary"
            button.icon = ""
            button.disabled = False
            button.add_class("feff-step-active")
            button.remove_class("feff-step-completed")
            button.remove_class("feff-step-upcoming")
        elif index < current_step:
            button.button_style = ""
            button.icon = "check"
            button.disabled = False
            button.add_class("feff-step-completed")
            button.remove_class("feff-step-active")
            button.remove_class("feff-step-upcoming")
        else:
            button.button_style = ""
            button.icon = ""
            button.disabled = False
            button.add_class("feff-step-upcoming")
            button.remove_class("feff-step-active")
            button.remove_class("feff-step-completed")


def create_action_bar(
    back_button: ipw.Button | None = None,
    primary_button: ipw.Button | None = None,
    start_over_button: ipw.Widget | None = None,
    extra_widgets: list[ipw.Widget] | None = None,
) -> ipw.HBox:
    """Create a unified bottom action bar with exactly one primary button."""
    left_items: list[ipw.Widget] = []
    if back_button is not None:
        back_button.button_style = ""
        back_button.layout.width = "auto"
        back_button.layout.min_width = "90px"
        back_button.add_class("feff-btn-secondary")
        left_items.append(back_button)

    if start_over_button is not None:
        left_items.append(start_over_button)

    right_items: list[ipw.Widget] = []
    if extra_widgets:
        right_items.extend(extra_widgets)
    if primary_button is not None:
        primary_button.button_style = "primary"
        primary_button.layout.width = "auto"
        primary_button.layout.min_width = "120px"
        primary_button.add_class("feff-btn-primary")
        right_items.append(primary_button)

    left_box = ipw.HBox(left_items, layout=ipw.Layout(align_items="center", grid_gap="8px"))
    right_box = ipw.HBox(right_items, layout=ipw.Layout(align_items="center", grid_gap="8px"))

    action_bar = ipw.HBox(
        [left_box, right_box],
        layout=ipw.Layout(
            justify_content="space-between",
            align_items="center",
            width="100%",
            margin="20px 0 10px 0",
            padding="12px 0 0 0",
            border_top="1px solid var(--feff-rule, #e0e0e0)",
        ),
    )
    action_bar.add_class("feff-action-bar")
    return action_bar
