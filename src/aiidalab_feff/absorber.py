"""Absorber selection widget with element chips, site filters, and 3D visualization."""

from __future__ import annotations

import ipywidgets as ipw
import weas_widget
from aiida.orm import StructureData
from aiida_feff.workflows.ensemble import _resolve_absorber_sites
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.models import InputModel
from aiidalab_feff.utils import get_symbols


class AbsorberSelectorWidget(ipw.VBox):
    """Widget for selecting absorbing atom sites with element chips and site filtering."""

    def __init__(self, model: InputModel):
        """Initialize the absorber selector with element chips and 3D viewer."""
        self.model = model

        self.header = ipw.HTML("<h3>Absorbing atoms</h3>")

        # Element selection chips
        self.element_chips = ipw.ToggleButtons(
            options=[],
            description="Element:",
            style={"description_width": "initial", "button_width": "auto"},
            layout={"margin": "4px 0"},
        )
        self.element_chips.observe(self._on_element_chip_change, names="value")

        # Backward compatibility dropdown
        self.element_selector = ipw.Dropdown(
            options=[],
            description="Element:",
            layout={"width": "200px", "display": "none"},
        )
        self.element_selector.observe(self._on_element_change, names="value")

        # Filter mode within the chosen element
        self.filter_mode = ipw.RadioButtons(
            options=[
                ("All atoms of this element", "all"),
                ("First N atoms", "first_n"),
                ("Specific sites", "specific"),
            ],
            value="all",
            description="Select:",
            style={"description_width": "initial"},
            layout={"margin": "6px 0"},
        )
        self.filter_mode.observe(self._on_filter_mode_change, names="value")

        self.first_n_slider = ipw.IntSlider(
            value=1,
            min=1,
            max=1,
            description="Count:",
            style={"description_width": "initial"},
            layout={"width": "280px", "display": "none"},
        )
        self.first_n_slider.observe(self._on_first_n_change, names="value")

        self.site_selector = ipw.SelectMultiple(
            options=[],
            description="Sites:",
            style={"description_width": "initial"},
            layout={"width": "280px", "height": "140px", "display": "none"},
        )
        self.site_selector.observe(self._on_site_change, names="value")

        self.summary = ipw.HTML(
            "<div style='color:var(--feff-ink-muted, #666);font-size:13px;'>No structure loaded.</div>"
        )

        # Advanced free-text selection with live validation
        self.input_field = ipw.Text(
            value="",
            placeholder="e.g. Fe, Fe:0,1, 0,1,2",
            description="Syntax:",
            style={"description_width": "initial"},
            layout={"width": "100%"},
        )
        self.input_field.observe(self._on_input_change, names="value")

        self.validate_button = ipw.Button(
            description="Validate",
            button_style="info",
            icon="check",
            layout={"display": "none"},
        )
        self.validate_button.on_click(self._validate_and_apply)

        advanced_box = ipw.VBox(
            [
                ipw.HTML(
                    "<div style='font-size:12px;color:var(--feff-ink-muted, #555);margin-bottom:6px;'>"
                    "Advanced selection syntax (supports <code>Fe</code>, <code>Fe:0,1</code>, "
                    "or comma-separated site indices like <code>0,1,2</code>). Changes validate live."
                    "</div>"
                ),
                self.input_field,
            ]
        )
        self.advanced_accordion = ipw.Accordion(children=[advanced_box])
        self.advanced_accordion.set_title(0, "Advanced selection syntax")
        self.advanced_accordion.selected_index = None

        self.status = Status()

        self.viewer = weas_widget.WeasWidget()
        self.viewer.layout = {"width": "100%", "height": "360px", "min_height": "320px"}

        controls_box = ipw.VBox(
            [
                self.element_chips,
                self.filter_mode,
                self.first_n_slider,
                self.site_selector,
                self.summary,
                self.advanced_accordion,
                self.status,
            ],
            layout=ipw.Layout(flex="1 1 340px", min_width="280px"),
        )

        viewer_box = ipw.VBox(
            [
                ipw.HTML(
                    "<div style='font-size:12px;font-weight:600;margin-bottom:4px;color:var(--feff-ink-muted);'>3D Structure (selected absorbers highlighted):</div>"
                ),
                self.viewer,
            ],
            layout=ipw.Layout(flex="1 1 380px", min_width="300px"),
        )

        main_row = ipw.HBox(
            [controls_box, viewer_box],
            layout=ipw.Layout(
                flex_flow="row wrap",
                align_items="flex-start",
                grid_gap="20px",
                margin="10px 0",
            ),
        )

        super().__init__(
            [
                self.header,
                main_row,
            ]
        )

        self.model.observe(self._on_structure_change, names="structure")
        self.model.observe(self._on_structures_change, names="structures")
        self.model.observe(self._on_trajectory_change, names="trajectory")
        self.model.observe(self._on_trajectory_change, names="selected_indices")
        self._reference = None
        self._silence_site_update = False

    def _reference_structure(self) -> StructureData | None:
        """Return the structure to use for absorber selection."""
        if self.model.structure is not None:
            return self.model.structure  # type: ignore[return-value]
        structures = self.model.get_structures()
        if structures:
            return next(iter(structures.values()))  # type: ignore[return-value]
        if self.model.trajectory is not None and self.model.selected_indices:
            step_id = self.model.selected_indices[0]
            frame_index = self.model.trajectory.get_index_from_stepid(step_id)
            return self.model.trajectory.get_step_structure(frame_index)
        return None

    def _on_structure_change(self, change):
        if change["new"] is not None:
            self._refresh(change["new"])

    def _on_structures_change(self, change):
        if self.model.structure is None:
            ref = self._reference_structure()
            if ref is not None:
                self._refresh(ref)
            else:
                self._clear()

    def _on_trajectory_change(self, _):
        if self.model.structure is None:
            ref = self._reference_structure()
            if ref is not None:
                self._refresh(ref)

    def _refresh(self, structure: StructureData):
        self._reference = structure
        self.input_field.value = ""
        self.model.absorbing_atoms = []
        symbols = get_symbols(structure)
        elements = sorted(set(symbols))
        self.element_selector.options = [("All", "")] + [(e, e) for e in elements]
        self.element_selector.value = ""
        self.element_chips.options = elements
        if elements:
            self.element_chips.value = elements[0]
            self.element_selector.value = elements[0]
        self._populate_site_selector()
        self._update_selection_from_ui()
        self.viewer.from_aiida(structure)
        self._update_highlight()

    def _clear(self):
        self._reference = None
        self.element_selector.options = []
        self.element_chips.options = []
        self.site_selector.options = []
        self.input_field.value = ""
        self.status.clear()
        self.summary.value = "<div style='color:var(--feff-ink-muted, #666);font-size:13px;'>No structure loaded.</div>"
        self._reset_viewer()

    def _populate_site_selector(self, element_filter: str = ""):
        if self._reference is None:
            return
        symbols = get_symbols(self._reference)
        options = []
        for i, sym in enumerate(symbols):
            if element_filter and sym != element_filter:
                continue
            options.append((f"Site {i}: {sym}", i))
        self.site_selector.options = options
        if element_filter:
            count = len(options)
            self.first_n_slider.max = max(1, count)
            self.first_n_slider.value = min(self.first_n_slider.value, count)

    def _on_element_chip_change(self, change):
        if not change["new"]:
            return
        elem = change["new"]
        self.element_selector.value = elem
        self._populate_site_selector(elem)
        self._update_selection_from_ui()

    def _on_filter_mode_change(self, change):
        mode = change["new"]
        if mode == "all":
            self.first_n_slider.layout.display = "none"
            self.site_selector.layout.display = "none"
        elif mode == "first_n":
            self.first_n_slider.layout.display = "block"
            self.site_selector.layout.display = "none"
        elif mode == "specific":
            self.first_n_slider.layout.display = "none"
            self.site_selector.layout.display = "block"
        self._update_selection_from_ui()

    def _on_first_n_change(self, _):
        if self.filter_mode.value == "first_n":
            self._update_selection_from_ui()

    def _update_selection_from_ui(self):
        if self._silence_site_update or self._reference is None:
            return
        elem = self.element_chips.value
        if not elem:
            return
        symbols = get_symbols(self._reference)
        elem_indices = [i for i, s in enumerate(symbols) if s == elem]
        if not elem_indices:
            return

        mode = self.filter_mode.value
        if mode == "all":
            selected = elem_indices
        elif mode == "first_n":
            n = min(self.first_n_slider.value, len(elem_indices))
            selected = elem_indices[:n]
        elif mode == "specific":
            selected = [i for i in self.site_selector.value if i in elem_indices]
            if not selected:
                selected = elem_indices[:1]
                self._silence_site_update = True
                self.site_selector.value = tuple(selected)
                self._silence_site_update = False
        else:
            selected = elem_indices

        self._silence_site_update = True
        self.input_field.value = f"{elem}:{','.join(str(elem_indices.index(i)) for i in selected)}"
        self._silence_site_update = False
        self._apply_indices(selected)

    def _on_element_change(self, change):
        self._populate_site_selector(change["new"])

    def _on_site_change(self, change):
        if self._silence_site_update or self._reference is None:
            return
        selected = list(change["new"])
        if not selected:
            return
        symbols = get_symbols(self._reference)
        elements = {symbols[i] for i in selected}
        if len(elements) == 1:
            element = next(iter(elements))
            element_indices = [j for j, s in enumerate(symbols) if s == element]
            relative = [element_indices.index(i) for i in selected]
            self._silence_site_update = True
            self.input_field.value = f"{element}:{','.join(str(r) for r in relative)}"
            self._silence_site_update = False
        else:
            self._silence_site_update = True
            self.input_field.value = ",".join(str(i) for i in selected)
            self._silence_site_update = False
        self._apply_indices(selected)

    def _on_input_change(self, change):
        if self._silence_site_update:
            return
        self.status.clear()
        if not change["new"].strip():
            self.model.absorbing_atoms = []
            self._update_highlight()
            return
        self._validate_and_apply()

    def _validate_and_apply(self, _=None):
        text = self.input_field.value.strip()
        if not text:
            self.model.absorbing_atoms = []
            self.status.clear()
            self._update_highlight()
            return
        ref = self._reference_structure()
        if ref is None:
            self.status.failure("Upload a structure first.")
            return
        try:
            indices = _resolve_absorber_sites(ref, text)
        except ValueError as exc:
            self.status.failure(str(exc))
            self.model.absorbing_atoms = []
            self._update_highlight()
            return
        self._apply_indices(indices)
        self._sync_site_selector(indices)

    def _apply_indices(self, indices: list[int]):
        self.model.absorbing_atoms = indices
        ref = self._reference_structure()
        symbols = get_symbols(ref) if ref is not None else []
        element = symbols[indices[0]] if indices and symbols else ""
        count = len(indices)
        plural = "absorbers" if count != 1 else "absorber"
        indices_preview = ", ".join(str(i) for i in indices[:8])
        if count > 8:
            indices_preview += f", ... (+{count - 8} more)"
        self.summary.value = (
            f"<div style='font-size:13px;padding:8px 12px;background:var(--feff-surface, #F4F6F8);"
            f"border-left:3px solid var(--feff-accent, #1B5E9B);border-radius:4px;margin:8px 0;'>"
            f"<strong>{count} {element} {plural} selected</strong> "
            f"<span style='color:var(--feff-ink-muted, #666);'>(sites: {indices_preview})</span>"
            f"</div>"
        )
        self._update_highlight()

    def _sync_site_selector(self, indices: list[int]):
        ref = self._reference_structure()
        symbols = get_symbols(ref) if ref is not None else []
        if not indices or not symbols:
            return
        element = symbols[indices[0]]
        if self.element_selector.value != element:
            self.element_selector.value = element
            self._populate_site_selector(element)
        self._silence_site_update = True
        self.site_selector.value = tuple(indices)
        self._silence_site_update = False

    def _update_highlight(self):
        selected = list(self.model.absorbing_atoms or [])
        settings = self.viewer.avr.highlight.get_default_settings()
        settings["selection"]["indices"] = selected
        self.viewer.avr.highlight.settings = settings

    def reset(self):
        """Reset absorber selections, element options, and viewer state."""
        self.input_field.value = ""
        self.element_selector.options = []
        self.element_chips.options = []
        self.site_selector.options = []
        self.filter_mode.value = "all"
        self.status.clear()
        self.summary.value = "<div style='color:var(--feff-ink-muted, #666);font-size:13px;'>No structure loaded.</div>"
        self._reference = None
        self._reset_viewer()

    def _reset_viewer(self):
        """Replace the embedded weas-widget viewer with a fresh, empty one.

        ``self.viewer`` is a child of this VBox; simply reassigning the
        attribute leaves the old widget referenced by ``self.children`` and so
        the previous structure keeps being rendered. Swap it in ``children``.
        """
        old = self.viewer
        fresh = weas_widget.WeasWidget()
        fresh.layout = {"width": "100%", "height": "400px"}
        self.viewer = fresh
        children = list(self.children)
        for i, child in enumerate(children):
            if child is old:
                children[i] = fresh
                self.children = children
                return
        # Viewer not yet in children (called before __init__); nothing to do.
