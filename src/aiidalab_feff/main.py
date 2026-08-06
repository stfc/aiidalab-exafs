"""Main entry point for the AiiDAlab FEFF app."""

from __future__ import annotations

import ipywidgets as ipw
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.common.navigation import (
    create_new_calculation_button,
)
from aiidalab_feff.input import InputWidget
from aiidalab_feff.models import InputModel, ResultsModel, SubmissionModel, WorkflowModel
from aiidalab_feff.process import ProcessWidget
from aiidalab_feff.resources import ResourcesWidget
from aiidalab_feff.results import ResultsWidget
from aiidalab_feff.results_library import ResultsLibraryWidget
from aiidalab_feff.workflow import FeffParametersWidget


class FeffApp(ipw.VBox):
    """AiiDAlab FEFF app with a custom step wizard."""

    STEP_INPUT = 0
    STEP_WORKFLOW = 1
    STEP_RESOURCES = 2
    STEP_PROCESS = 3
    STEP_RESULTS = 4

    def __init__(self):
        self.input_model = InputModel()
        self.workflow_model = WorkflowModel()
        self.submission_model = SubmissionModel()
        self.results_model = ResultsModel()

        self.input_widget = InputWidget(self.input_model)
        self.workflow_widget = FeffParametersWidget(self.workflow_model)
        self.resources_widget = ResourcesWidget(self.workflow_model)
        self.process_widget = ProcessWidget(
            self.input_model,
            self.workflow_model,
            self.submission_model,
            self.results_model,
            on_process_loaded=lambda: self._go_to_step(self.STEP_PROCESS),
            on_results_loaded=lambda: self._go_to_step(self.STEP_RESULTS),
        )
        self.results_widget = ResultsWidget(self.results_model)

        self.steps = [
            self.input_widget,
            self.workflow_widget,
            self.resources_widget,
            self.process_widget,
            self.results_widget,
        ]

        self.step_titles = [
            "1. Input structures",
            "2. FEFF parameters",
            "3. Resources",
            "4. Submit / monitor",
            "5. Results",
        ]

        self.header = ipw.HTML("<h1>AiiDAlab FEFF — EXAFS / MD-EXAFS</h1>")
        self.progress = ipw.HTML()

        self.back_button = ipw.Button(description="Back", icon="arrow-left")
        self.next_button = ipw.Button(
            description="Next",
            icon="arrow-right",
            button_style="primary",
        )
        self.back_button.on_click(self._on_back)
        self.next_button.on_click(self._on_next)

        self.new_button = create_new_calculation_button(self)

        self.nav_bar = ipw.HBox(
            [
                self.back_button,
                self.next_button,
                self.new_button,
            ]
        )

        self.content = ipw.VBox()
        self.status = Status()
        self.new_calculation_view = ipw.VBox(
            [
                self.progress,
                self.nav_bar,
                self.status,
                self.content,
            ]
        )
        self.results_library = ResultsLibraryWidget(self._open_saved_results)
        self.app_tabs = ipw.Tab(children=[self.new_calculation_view, self.results_library])
        self.app_tabs.set_title(0, "New calculation")
        self.app_tabs.set_title(1, "Previous results")

        super().__init__(
            [
                self.header,
                self.app_tabs,
            ]
        )

        self._current_step = self.STEP_INPUT
        self._update_view()

    def reset(self):
        """Reset the entire app to its initial state."""
        self.input_model.reset()
        self.workflow_model.reset()
        self.submission_model.reset()
        self.results_model.reset()
        self.input_widget.reset()
        self.workflow_widget.reset()
        self.resources_widget.reset()
        self.process_widget.reset()
        self.results_widget.reset()
        self._current_step = self.STEP_INPUT
        self._update_view()

    def _on_back(self, _):
        if self._current_step > 0:
            self._current_step -= 1
            self._update_view()

    def _open_saved_results(self, process_node):
        """Load a selected successful workflow into the results view."""
        self.reset()
        self.app_tabs.selected_index = 0
        self.submission_model.process_node = process_node

    def _go_to_step(self, step: int):
        """Jump to the given step if it is valid."""
        if 0 <= step < len(self.steps):
            self._current_step = step
            self._update_view()

    def _on_next(self, _):
        errors = self._validate_current_step()
        if errors:
            self.status.failure("<br>".join(f"• {e}" for e in errors))
            return
        self.status.clear()
        if self._current_step < len(self.steps) - 1:
            self._current_step += 1
            self._update_view()

    def _validate_current_step(self) -> list[str]:
        step = self._current_step
        if step == self.STEP_INPUT:
            if not self.input_model.is_ensemble():
                return ["Provide a structure or ensemble."]
            if not self.input_model.absorbing_atoms:
                return ["Select at least one absorbing atom."]
            return []
        if step == self.STEP_WORKFLOW:
            return self.workflow_widget.validate()
        if step == self.STEP_RESOURCES:
            return self.resources_widget.validate()
        return []

    def _update_view(self):
        step = self._current_step + 1
        title = self.step_titles[self._current_step]
        self.progress.value = f"Step {step} of {len(self.steps)}: {title}"
        self.content.children = [self.steps[self._current_step]]
        self.back_button.disabled = self._current_step == 0
        self.next_button.disabled = self._current_step == len(self.steps) - 1

        if self._current_step == self.STEP_PROCESS:
            self.workflow_widget.get_parameters()  # ensure model.parameters is current
            self.workflow_model.parameters = self.workflow_widget.get_parameters().get_dict()


def main():
    """Return the main app widget."""
    return FeffApp()


__all__ = ["FeffApp", "main"]
