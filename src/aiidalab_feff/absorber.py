"""Absorber selection widget with CLI syntax and structure visualisation."""

from __future__ import annotations

import ipywidgets as ipw
import weas_widget
from aiida.orm import StructureData
from aiida_feff.workflows.ensemble import _resolve_absorber_sites

from aiidalab_feff.models import InputModel
from aiidalab_feff.utils import get_symbols


class AbsorberSelectorWidget(ipw.VBox):
    """Widget for selecting one or more absorber sites from a structure.

    Supports the same selection syntax as the aiida-feff plugin CLI:

    - ``Fe``             all Fe atoms
    - ``Fe:0,1``         first and second Fe atoms (relative within element)
    - ``0,1,2``          absolute atom indices
    - ``1``              single absolute index

    The selected absorber sites are highlighted in the embedded weas-widget viewer.
    """

    def __init__(self, model: InputModel):
        self.model = model

        self.header = ipw.HTML("<h3>Select absorbing atoms</h3>")

        self.input_field = ipw.Text(
            value="",
            placeholder="e.g. Fe, Fe:0,1, 0,1,2",
            description="Selection:",
            layout={"width": "400px"},
        )
        self.input_field.observe(self._on_input_change, names="value")

        self.validate_button = ipw.Button(
            description="Validate",
            button_style="info",
            icon="check",
        )
        self.validate_button.on_click(self._validate_and_apply)

        self.element_selector = ipw.Dropdown(
            options=[],
            description="Element:",
            layout={"width": "200px"},
        )
        self.element_selector.observe(self._on_element_change, names="value")

        self.site_selector = ipw.SelectMultiple(
            options=[],
            description="Sites:",
            layout={"width": "300px", "height": "150px"},
        )
        self.site_selector.observe(self._on_site_change, names="value")

        self.status = ipw.HTML()
        self.summary = ipw.HTML()

        self.viewer = weas_widget.WeasWidget()
        self.viewer.layout = {"width": "100%", "height": "400px"}

        super().__init__(
            [
                self.header,
                ipw.HBox(
                    [self.input_field, self.validate_button],
                    layout={"align_items": "flex-end"},
                ),
                ipw.HBox([self.element_selector, self.site_selector]),
                self.status,
                self.summary,
                self.viewer,
            ]
        )

        self.model.observe(self._on_structure_change, names="structure")
        self.model.observe(self._on_structures_change, names="structures")
        self._reference = None
        self._silence_site_update = False

    def _reference_structure(self) -> StructureData | None:
        """Return the structure to use for absorber selection."""
        if self.model.structure is not None:
            return self.model.structure  # type: ignore[return-value]
        structures = self.model.get_structures()
        if structures:
            return next(iter(structures.values()))  # type: ignore[return-value]
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

    def _refresh(self, structure: StructureData):
        self._reference = structure
        self.input_field.value = ""
        self.model.absorbing_atoms = []
        symbols = get_symbols(structure)
        elements = sorted(set(symbols))
        self.element_selector.options = [("All", "")] + [(e, e) for e in elements]
        self.element_selector.value = ""
        self._populate_site_selector()
        self.viewer.from_aiida(structure)
        self._update_highlight()

    def _clear(self):
        self._reference = None
        self.element_selector.options = []
        self.site_selector.options = []
        self.input_field.value = ""
        self.status.value = ""
        self.summary.value = ""
        self._reset_viewer()

    def _populate_site_selector(self, element_filter: str = ""):
        if self._reference is None:
            return
        symbols = get_symbols(self._reference)
        options = []
        for i, sym in enumerate(symbols):
            if element_filter and sym != element_filter:
                continue
            options.append((f"{i}: {sym}", i))
        self.site_selector.options = options

    def _on_element_change(self, change):
        self._populate_site_selector(change["new"])

    def _on_site_change(self, change):
        if self._silence_site_update or self._reference is None:
            return
        selected = list(change["new"])
        if not selected:
            self.input_field.value = ""
            return
        # Prefer element-relative syntax if all selected atoms share one element.
        symbols = get_symbols(self._reference)
        elements = {symbols[i] for i in selected}
        if len(elements) == 1:
            element = next(iter(elements))
            element_indices = [j for j, s in enumerate(symbols) if s == element]
            relative = [element_indices.index(i) for i in selected]
            self.input_field.value = f"{element}:{','.join(str(r) for r in relative)}"
        else:
            self.input_field.value = ",".join(str(i) for i in selected)
        self._apply_indices(selected)

    def _on_input_change(self, change):
        self.status.value = ""
        if not change["new"].strip():
            self.model.absorbing_atoms = []
            self._update_highlight()
            return
        self._validate_and_apply()

    def _validate_and_apply(self, _=None):
        text = self.input_field.value.strip()
        if not text:
            self.model.absorbing_atoms = []
            self.status.value = ""
            self._update_highlight()
            return
        ref = self._reference_structure()
        if ref is None:
            self.status.value = (
                "<span style='color: red'>&#10007; Upload a structure first.</span>"
            )
            return
        try:
            indices = _resolve_absorber_sites(ref, text)
        except ValueError as exc:
            self.status.value = f"<span style='color: red'>&#10007; {exc}</span>"
            self.model.absorbing_atoms = []
            self._update_highlight()
            return
        self._apply_indices(indices)
        self._sync_site_selector(indices)
        self.status.value = (
            f"<span style='color: green'>&#10003; {len(indices)} site(s) selected: "
            f"{', '.join(str(i) for i in indices)}</span>"
        )

    def _apply_indices(self, indices: list[int]):
        self.model.absorbing_atoms = indices
        ref = self._reference_structure()
        symbols = get_symbols(ref) if ref is not None else []
        element = symbols[indices[0]] if indices and symbols else None
        self.summary.value = (
            f"<b>Selected:</b> {len(indices)} {element} site(s) &mdash; "
            f"indices {', '.join(str(i) for i in indices)}"
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
        self.input_field.value = ""
        self.element_selector.options = []
        self.site_selector.options = []
        self.status.value = ""
        self.summary.value = ""
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
