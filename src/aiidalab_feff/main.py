"""Main entry point for the AiiDAlab FEFF app."""

from __future__ import annotations

import ipywidgets as ipw
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.common.navigation import (
    create_action_bar,
    create_breadcrumbs,
    create_new_calculation_button,
    update_breadcrumbs,
)
from aiidalab_feff.input import InputWidget
from aiidalab_feff.models import InputModel, ResultsModel, SubmissionModel, WorkflowModel
from aiidalab_feff.process import ProcessWidget
from aiidalab_feff.resources import ResourcesWidget
from aiidalab_feff.results import ResultsWidget
from aiidalab_feff.results_library import ResultsLibraryWidget
from aiidalab_feff.styles import get_style_widget
from aiidalab_feff.workflow import FeffParametersWidget


class FeffApp(ipw.VBox):
    """AiiDAlab FEFF app with a consolidated 5-step wizard and unified Runs browser."""

    STEP_INPUT = 0
    STEP_SETTINGS = 1
    STEP_REVIEW = 2
    STEP_PROGRESS = 3
    STEP_RESULTS = 4

    # Backward compatibility step aliases
    STEP_WORKFLOW = STEP_SETTINGS
    STEP_RESOURCES = STEP_REVIEW
    STEP_PROCESS = STEP_PROGRESS

    TAB_NEW = 0
    TAB_RUNS = 1
    # Backward compatibility tab aliases
    TAB_RESULTS = 1
    TAB_RUNNING = 1

    def __init__(self):
        self.input_model = InputModel()
        self.workflow_model = WorkflowModel()
        self.submission_model = SubmissionModel()
        self.results_model = ResultsModel()

        self.input_widget = InputWidget(self.input_model)
        self.workflow_widget = FeffParametersWidget(self.workflow_model, self.input_model)
        self.resources_widget = ResourcesWidget(self.workflow_model, self.input_model)
        self.process_widget = ProcessWidget(
            self.input_model,
            self.workflow_model,
            self.submission_model,
            self.results_model,
            on_process_loaded=lambda: self._go_to_step(self.STEP_PROGRESS),
            on_results_loaded=self._on_results_loaded,
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
            "1. Structure",
            "2. Settings",
            "3. Review & run",
            "4. Progress",
            "5. Results",
        ]
        self.step_short_titles = [
            "1 Structure",
            "2 Settings",
            "3 Review & run",
            "4 Progress",
            "5 Results",
        ]

        self.breadcrumbs, self._breadcrumb_buttons = create_breadcrumbs(
            self.step_short_titles, self._on_breadcrumb
        )

        # G4 vocabulary: EXAFS from MD trajectories
        self.header = ipw.HTML(
            "<h1 style='margin: 0 0 8px 0; font-size: 22px; color: var(--feff-ink, #1F2933);'>"
            "EXAFS from MD trajectories"
            "</h1>"
        )
        self.progress = ipw.HTML()  # Kept for backward compatibility

        # Action bar buttons (G2: single action bar at the bottom)
        self.back_button_bottom = ipw.Button(description="Back", icon="arrow-left")
        self.next_button_bottom = ipw.Button(
            description="Next: Settings →",
            button_style="primary",
        )
        self.back_button_bottom.on_click(self._on_back)
        self.next_button_bottom.on_click(self._on_next)

        # Aliases for backward compatibility
        self.back_button = self.back_button_bottom
        self.next_button = self.next_button_bottom
        self.back_button_top = self.back_button_bottom
        self.next_button_top = self.next_button_bottom

        # Start over button
        self.new_button_bottom = create_new_calculation_button(self)
        self.new_button = self.new_button_bottom
        self.new_button_top = self.new_button_bottom

        self.action_bar = create_action_bar(
            back_button=self.back_button_bottom,
            primary_button=self.next_button_bottom,
            start_over_button=self.new_button_bottom,
        )

        # Keep for backward compatibility
        self.top_nav_bar = ipw.HBox([], layout=ipw.Layout(display="none"))
        self.bottom_nav_bar = self.action_bar
        self.marimo_link = ipw.HTML()

        self.content = ipw.VBox()
        self.status = Status()

        self.new_calculation_view = ipw.VBox(
            [
                self.breadcrumbs,
                self.status,
                self.content,
                self.action_bar,
            ],
            layout=ipw.Layout(padding="4px 0"),
        )

        # Merged Runs tab (Screen 5)
        self.results_library = ResultsLibraryWidget(
            on_open=self._open_saved_results,
            on_refreshed=self._update_runs_tab_title,
        )
        self.running_tasks = self.results_library  # Backward compatibility alias

        self.app_tabs = ipw.Tab(children=[self.new_calculation_view, self.results_library])
        self.app_tabs.set_title(self.TAB_NEW, "New calculation")
        self.app_tabs.set_title(self.TAB_RUNS, "Runs")
        self.app_tabs.observe(self._on_app_tab_changed, names="selected_index")

        if self.results_library.last_count is not None:
            self._update_runs_tab_title(self.results_library.last_count)

        super().__init__(
            [
                get_style_widget(),
                self.header,
                self.app_tabs,
            ]
        )
        self.add_class("feff-app")

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
        self.status.clear()
        self._current_step = self.STEP_INPUT
        self._update_view()

    def _on_back(self, _):
        if self._current_step > 0:
            self._current_step -= 1
            self._update_view()

    def _open_saved_results(self, process_node):
        """Load a selected completed workflow into the results view inside the same stepper."""
        self.reset()
        self.app_tabs.selected_index = self.TAB_NEW
        self.status.value = f"Loading results for Process {process_node.pk}..."
        # Assigning the trait fires ProcessWidget._on_process_node_change, which
        # runs _monitor_process → _on_finished → _populate_results for a terminated
        # node. Calling _on_finished here as well would do the whole load twice
        # (measured: 15.3 s → 7.7 s for a 31-snapshot run), so we only set the trait
        # and let the observer drive the load.
        self.submission_model.process_node = process_node
        if getattr(process_node, "is_terminated", False):
            # _on_finished's on_results_loaded callback already jumps to the results
            # step; this is a fallback for the (rare) terminated-but-not-finished case.
            self._go_to_step(self.STEP_RESULTS)
        else:
            self._go_to_step(self.STEP_PROGRESS)

    def _open_running_workflow(self, process_node):
        """Load a running workflow into the progress step."""
        self.reset()
        self.app_tabs.selected_index = self.TAB_NEW
        self.submission_model.process_node = process_node
        self._go_to_step(self.STEP_PROGRESS)

    def _on_results_loaded(self):
        """Called when workflow results finish loading into ResultsWidget."""
        self.status.clear()
        self._go_to_step(self.STEP_RESULTS)

    def _on_app_tab_changed(self, change):
        """Refresh the runs tab when it is selected."""
        if change.get("new") == self.TAB_RUNS:
            self.results_library.refresh()

    def _update_runs_tab_title(self, count: int):
        """Show active count in the Runs tab title if any are running."""
        if hasattr(self, "app_tabs"):
            title = f"Runs ({count})" if count else "Runs"
            self.app_tabs.set_title(self.TAB_RUNS, title)

    def _go_to_step(self, step: int):
        """Jump to the given step if it is valid."""
        if 0 <= step < len(self.steps):
            self._current_step = step
            self._update_view()

    def _on_breadcrumb(self, index: int):
        """Handle a breadcrumb click: free backward, validated forward jumps."""
        if index == self._current_step:
            return
        if index < self._current_step:
            self.status.clear()
            self._go_to_step(index)
            return
        for step in range(self._current_step, index):
            errors = self._validate_step(step)
            if errors:
                self.status.failure("<br>".join(f"• {e}" for e in errors))
                return
        self.status.clear()
        self._go_to_step(index)

    def _on_next(self, _):
        errors = self._validate_step(self._current_step)
        if errors:
            self.status.failure("<br>".join(f"• {e}" for e in errors))
            return
        self.status.clear()

        # Step 2: "Run calculation" triggers submission and advances to Progress
        if self._current_step == self.STEP_REVIEW:
            self.process_widget._on_submit(None)
            if self.submission_model.process_node is not None:
                self._current_step = self.STEP_PROGRESS
                self._update_view()
            return

        # Step 3: Progress -> Results
        if self._current_step == self.STEP_PROGRESS:
            self._current_step = self.STEP_RESULTS
            self._update_view()
            return

        if self._current_step < len(self.steps) - 1:
            self._current_step += 1
            self._update_view()

    def _validate_step(self, step: int) -> list[str]:
        if step == self.STEP_INPUT:
            if not self.input_model.is_ensemble():
                return ["Provide a structure or ensemble."]
            if not self.input_model.absorbing_atoms:
                return ["Select at least one absorbing atom."]
            return []
        if step == self.STEP_SETTINGS:
            return self.workflow_widget.validate()
        if step == self.STEP_REVIEW:
            return self.resources_widget.validate()
        return []

    def _update_view(self):
        self.content.children = [self.steps[self._current_step]]
        update_breadcrumbs(self._breadcrumb_buttons, self._current_step)

        # Back button state
        self.back_button_bottom.disabled = self._current_step == 0

        # Primary button state and labels per step
        if self._current_step == self.STEP_INPUT:
            self.next_button_bottom.layout.display = "inline-block"
            self.next_button_bottom.description = "Next: Settings →"
            self.next_button_bottom.icon = "arrow-right"
            self.next_button_bottom.disabled = False
        elif self._current_step == self.STEP_SETTINGS:
            self.workflow_widget.input_model = self.input_model
            self.next_button_bottom.layout.display = "inline-block"
            self.next_button_bottom.description = "Next: Review & run →"
            self.next_button_bottom.icon = "arrow-right"
            self.next_button_bottom.disabled = False
        elif self._current_step == self.STEP_REVIEW:
            self.workflow_widget.get_parameters()
            self.workflow_model.parameters = self.workflow_widget.get_parameters().get_dict()
            self.resources_widget.input_model = self.input_model
            self.resources_widget.update_review_card()
            self.next_button_bottom.layout.display = "inline-block"
            self.next_button_bottom.description = "Run calculation"
            self.next_button_bottom.icon = "play"
            self.next_button_bottom.disabled = False
        elif self._current_step == self.STEP_PROGRESS:
            node = self.submission_model.process_node
            is_term = bool(getattr(node, "is_terminated", False))
            if is_term:
                self.next_button_bottom.layout.display = "inline-block"
                self.next_button_bottom.description = "View results →"
                self.next_button_bottom.icon = "bar-chart"
                self.next_button_bottom.disabled = False
            else:
                self.next_button_bottom.layout.display = "none"
        elif self._current_step == self.STEP_RESULTS:
            self.next_button_bottom.layout.display = "none"


def main():
    """Return the main app widget."""
    return FeffApp()


__all__ = ["FeffApp", "main"]
