"""Utility functions for the AiiDAlab FEFF app."""

from __future__ import annotations

from aiida.orm import ProcessNode, StructureData, TrajectoryData


def get_trajectory_size_mb(trajectory: TrajectoryData) -> float:
    """Return the largest object size in a TrajectoryData node, in MB."""
    object_names = trajectory.base.repository.list_object_names()
    if not object_names:
        return 0.0
    sizes = [
        len(trajectory.base.repository.get_object_content(name, mode="rb"))
        for name in object_names
    ]
    return max(sizes) / (1024 * 1024)


def validate_trajectory_size(trajectory: TrajectoryData, max_size_mb: float = 2048.0) -> None:
    """Raise if the trajectory file exceeds a safe in-process size."""
    size_mb = get_trajectory_size_mb(trajectory)
    if size_mb > max_size_mb:
        msg = (
            f"Trajectory object is {size_mb:.0f} MB, exceeding the "
            f"{max_size_mb:.0f} MB limit. Pre-sample your trajectory externally "
            f"or use a smaller subset."
        )
        raise ValueError(msg)


def get_symbols(structure: StructureData) -> list[str]:
    """Return the list of chemical symbols for all atoms in a StructureData node."""
    return [site.kind_name for site in structure.sites]


def is_valid_structure_element(structure: StructureData, supported_elements: set[str]) -> bool:
    """Return True if all elements in the structure are supported by FEFF."""
    symbols = set(get_symbols(structure))
    return symbols.issubset(supported_elements)


def get_incoming_structure_labels(process_node: ProcessNode) -> dict[str, StructureData]:
    """Return the {label: StructureData} mapping from the structures namespace.

    This is used by the results page to build convergence plots from the
    provenance graph rather than a dedicated output namespace.
    """
    from aiida.common.links import LinkType

    structures: dict[str, StructureData] = {}
    for link_triple in process_node.base.links.get_incoming(link_type=LinkType.INPUT_CALC):
        if link_triple.link_label.startswith("structures."):
            label = link_triple.link_label.split(".", 1)[1]
            node = link_triple.node
            if isinstance(node, StructureData):
                structures[label] = node
    return structures


SUPPORTED_ELEMENTS = {
    "H",
    "He",
    "Li",
    "Be",
    "B",
    "C",
    "N",
    "O",
    "F",
    "Ne",
    "Na",
    "Mg",
    "Al",
    "Si",
    "P",
    "S",
    "Cl",
    "Ar",
    "K",
    "Ca",
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Ga",
    "Ge",
    "As",
    "Se",
    "Br",
    "Kr",
    "Rb",
    "Sr",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "In",
    "Sn",
    "Sb",
    "Te",
    "I",
    "Xe",
    "Cs",
    "Ba",
    "La",
    "Hf",
    "Ta",
    "W",
    "Re",
    "Os",
    "Ir",
    "Pt",
    "Au",
    "Hg",
    "Tl",
    "Pb",
    "Bi",
    "Po",
    "At",
    "Rn",
}
