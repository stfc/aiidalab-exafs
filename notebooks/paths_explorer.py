"""EXAFS paths: chi contributions · Debye-Waller σ² · 3-D structure.

Three complementary views per scattering path:
  • k-space and R-space chi contribution  (EXAFS pipeline HDF5)
  • σ² / Reff Debye-Waller scatter plot   (MD trajectory)
  • 3-D averaged structure with path arrows

Path matching notes
-------------------
FEFF paths (from averaged paths HDF5):
    scatterer : element symbol of the scattering atom
    nlegs     : number of path legs
                  2 → single-scattering (A→B→A);  r_eff = bond distance
                  4 → rattle / collinear MS (A→B→A→B→A);  r_eff ≈ 2×r_bond
                  3 → triangular path;  r_eff = half total path length
    r_eff_ref : effective path length = half total path length (Å)

DW/MSRD (from calculate_grouped_msrd):
    type  : "Absorber-Scatterer"  (2-body only)
    reff  : mean bond distance (Å)   ← equal to r_eff for nlegs=2 only
    σ²    : variance of bond distances = σ²_EXAFS for nlegs=2

Only nlegs=2 FEFF paths are matched to DW σ² directly.
For nlegs=4 collinear rattle paths: σ²_rattle ≈ 4 × σ²_single (approximate).
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "altair>=6.0.0",
#     "ase>=3.27.0",
#     "h5py",
#     "marimo>=0.21.1",
#     "md-exafs>=0.2.0",
#     "numpy>=2.0",
#     "pandas>=2.0",
#     "xraylarch>=0.9",
#     "weas-widget>=0.1.26",
# ]
# ///

import marimo

__generated_with = "0.23.9"
app = marimo.App(width="full", app_title="EXAFS Paths — chi + DW + Structure")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import logging
    from collections import defaultdict

    import altair as alt
    import h5py
    import numpy as np
    import pandas as pd
    from ase import Atoms
    from ase.data import atomic_numbers
    from ase.data.colors import jmol_colors
    from ase.geometry import find_mic
    from ase.io import read as ase_read
    from weas_widget.atoms_viewer import AtomsViewer
    from weas_widget.base_widget import BaseWidget
    from weas_widget.utils import ASEAdapter

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("paths_combined")
    guiConfig = {"controls": {"enabled": False}}
    try:
        from aiida import load_profile, orm

        aiida_available = True
    except ImportError:
        load_profile, orm = None, None
        aiida_available = False

    return (
        ASEAdapter,
        Atoms,
        AtomsViewer,
        BaseWidget,
        aiida_available,
        alt,
        ase_read,
        atomic_numbers,
        defaultdict,
        find_mic,
        guiConfig,
        h5py,
        jmol_colors,
        load_profile,
        logger,
        np,
        orm,
        pd,
    )


@app.cell
def _(np):
    from larch import Group
    from larch.xafs import xftf

    # k / R chart display limits — not FT window (those are UI sliders below)
    KMIN = 2.0
    KMAX = 14.0
    RMIN = 0.0

    def perform_FT(
        k,
        chi,
        kmin=3.0,
        kmax=12.0,
        kweight=2,
        dk=1.0,
        k_window="hanning",
        rmax=10.0,
    ):
        g = Group(k=k, chi=chi)
        xftf(
            g,
            kmin=kmin,
            kmax=kmax,
            dk=dk,
            kweight=kweight,
            window=k_window,
            rmax_out=rmax,
        )
        return g

    def compute_chi_from_params(k_grid, amp, pha, lam, rep, reff, degen, k_param, sigma2=0.0):
        """Recompute χ(k) from averaged FEFF raw parameters on an arbitrary grid.

        Uses the full complex-momentum EXAFS formula (matching larch's
        FeffPathGroup._calc_chi with default path parameters) by linearly
        interpolating amp/pha/lam/rep from the native coarse FEFF grid.
        """
        amp_i = np.interp(k_grid, k_param, amp)
        pha_i = np.interp(k_grid, k_param, pha)
        lam_i = np.interp(k_grid, k_param, lam)
        rep_i = np.interp(k_grid, k_param, rep)

        q = k_grid
        # complex momentum squared: (rep + i/λ)²
        pp = (rep_i + 1j / np.clip(lam_i, 1e-6, None)) ** 2
        p = np.sqrt(pp)

        # Full EXAFS equation with S0²=1, ΔE₀=0, ΔR=0 and optional Debye-Waller sigma^2
        cchi = np.exp(-2 * reff * p.imag - 2 * pp * float(sigma2) + 1j * (2 * q * reff + pha_i))
        with np.errstate(divide="ignore", invalid="ignore"):
            cchi = float(degen) * amp_i * cchi / (q * reff**2)
        chi = np.asarray(cchi.imag, dtype=np.float64)
        chi[~np.isfinite(chi)] = 0.0
        return chi

    return KMAX, KMIN, RMIN, compute_chi_from_params, perform_FT


@app.cell
def _():
    from md_exafs.debye_waller import (
        _max_safe_mic_cutoff as max_safe_mic_cutoff,
    )
    from md_exafs.debye_waller import (
        calculate_grouped_msrd,
        compute_adp_results,
        kabsch_align,
        unwrap_positions_pbc,
    )

    return (
        calculate_grouped_msrd,
        compute_adp_results,
        kabsch_align,
        max_safe_mic_cutoff,
        unwrap_positions_pbc,
    )


@app.cell
def _(load_profile, orm):
    calcs_map = {}
    if load_profile is not None and orm is not None:
        try:
            load_profile()
            qb = orm.QueryBuilder()
            qb.append(
                orm.WorkChainNode,
                filters={"attributes.exit_status": {"in": [0, 301]}},
                project=["id", "label", "ctime", "attributes.exit_status"],
                tag="wc",
            )
            qb.append(
                orm.Node,
                with_incoming="wc",
                filters={"node_type": {"ilike": "%feff%"}},
                edge_filters={"label": {"in": ["path_contributions", "archive"]}},
                tag="out",
            )
            qb.order_by({"wc": {"ctime": "desc"}})
            for pk, label, ctime, exit_status in qb.distinct().all():
                date_str = ctime.strftime("%Y-%m-%d %H:%M") if ctime else ""
                lbl_str = f" '{label}'" if label else ""
                status_str = " (warnings)" if exit_status == 301 else ""

                formula = ""
                try:
                    node = orm.load_node(pk)
                    if hasattr(node.inputs, "structure"):
                        formula = getattr(node.inputs.structure, "get_formula", lambda: "")()
                    elif hasattr(node.inputs, "trajectory"):
                        st0 = getattr(node.inputs.trajectory, "get_step_structure", lambda _: None)(
                            0
                        )
                        formula = st0.get_formula() if st0 else ""
                    elif hasattr(node.inputs, "structures"):
                        st = next(
                            (
                                getattr(node.inputs.structures, k)
                                for k in dir(node.inputs.structures)
                                if not k.startswith("_")
                            ),
                            None,
                        )
                        formula = st.get_formula() if st and hasattr(st, "get_formula") else ""
                except Exception:
                    formula = ""

                form_str = f"[{formula}]" if formula else ""
                display_label = f"PK {pk}: {form_str}{lbl_str}{status_str} — {date_str}"
                calcs_map[display_label] = pk
        except Exception as exc:
            calcs_map[f"Could not connect to AiiDA: {exc}"] = None

    return (calcs_map,)


@app.cell
def _(calcs_map, mo):
    default_calc = next((k for k, v in calcs_map.items() if v is not None), None)
    calc_dropdown = mo.ui.dropdown(
        options=calcs_map,
        value=default_calc,
        label="Select EXAFS WorkChain (with path contributions):",
    )
    custom_calc_pk = mo.ui.text(
        placeholder="e.g. 14420 (optional PK override)",
        label="Or enter PK directly:",
    )
    btn_load = mo.ui.run_button(label="▶ Load Calculation")
    return btn_load, calc_dropdown, custom_calc_pk


@app.cell
def _(btn_load, calc_dropdown, custom_calc_pk, mo):
    selector_bar = mo.vstack(
        [
            mo.md("### 📂 Select Calculation"),
            mo.hstack([calc_dropdown, custom_calc_pk, btn_load], gap=2, align="end"),
        ]
    )
    selector_bar
    return


@app.cell
def _(
    ASEAdapter,
    AtomsViewer,
    BaseWidget,
    btn_load,
    calc_dropdown,
    custom_calc_pk,
    guiConfig,
    load_profile,
    mo,
    orm,
):
    mo.stop(
        not btn_load.value,
        mo.callout(
            mo.md(
                "Select an EXAFS calculation above and click **▶ Load Calculation** to initialise."
            ),
            kind="info",
        ),
    )

    selected_node = None
    preview_structure = None
    preview_viewer = None
    preview_info = None

    pk_val = custom_calc_pk.value.strip() or str(calc_dropdown.value or "").strip()
    if pk_val and orm is not None and load_profile is not None:
        try:
            load_profile()
            selected_node = orm.load_node(int(pk_val))

            _curr = selected_node
            while _curr is not None and preview_structure is None:
                if hasattr(_curr, "inputs"):
                    if hasattr(_curr.inputs, "structures"):
                        for _key in sorted(dir(_curr.inputs.structures)):
                            if not _key.startswith("_"):
                                _struct = getattr(_curr.inputs.structures, _key)
                                if hasattr(_struct, "get_ase"):
                                    preview_structure = _struct.get_ase()
                                    break
                    elif hasattr(_curr.inputs, "structure"):
                        _struct = _curr.inputs.structure
                        if hasattr(_struct, "get_ase"):
                            preview_structure = _struct.get_ase()
                    elif hasattr(_curr.inputs, "trajectory"):
                        _struct = _curr.inputs.trajectory.get_step_structure(0)
                        if hasattr(_struct, "get_ase"):
                            preview_structure = _struct.get_ase()
                _curr = getattr(_curr, "caller", None)

            if preview_structure is not None:
                _v = AtomsViewer(BaseWidget(guiConfig=guiConfig))
                _v.atoms = ASEAdapter.to_weas(preview_structure)
                _v.model_style = 0
                _v.atom_scales = [0.333] * len(preview_structure)
                preview_viewer = _v._widget

                _formula = preview_structure.get_chemical_formula()
                _n_atoms = len(preview_structure)
                _cell_lengths = [f"{x:.2f}" for x in preview_structure.get_cell().lengths()]
                _cell_str = (
                    f"a={_cell_lengths[0]}Å, b={_cell_lengths[1]}Å, c={_cell_lengths[2]}Å"
                    if len(_cell_lengths) >= 3
                    else ""
                )

                preview_info = mo.md(
                    f"#### Structure Preview: **{_formula}** ({_n_atoms} atoms)\n\n"
                    f"**Unit Cell:** {_cell_str} · PBC: `{preview_structure.get_pbc().tolist()}`"
                )
        except Exception as exc:
            preview_info = mo.md(f"Could not load structure preview: {exc}")

    preview_box = (
        mo.hstack([preview_info, preview_viewer], widths=[40, 60], gap=2)
        if preview_viewer is not None
        else preview_info
    )
    preview_box
    return (selected_node,)


@app.cell
def _(mo):
    ft_kmin = mo.ui.slider(
        start=0.0,
        stop=6.0,
        value=3.0,
        step=0.1,
        label="k_min (Å⁻¹)",
        show_value=True,
    )
    ft_kmax = mo.ui.slider(
        start=5.0,
        stop=20.0,
        value=12.0,
        step=0.5,
        label="k_max (Å⁻¹)",
        show_value=True,
    )
    ft_kweight = mo.ui.dropdown(
        options=[1, 2, 3],
        value=2,
        label="k-weight",
    )
    ft_dk = mo.ui.slider(
        start=0.0,
        stop=4.0,
        value=1.0,
        step=0.1,
        label="dk (Å⁻¹)",
        show_value=True,
    )
    ft_window = mo.ui.dropdown(
        options=["hanning", "kaiser", "parzen", "welch", "sine"],
        value="hanning",
        label="Window",
    )
    ft_rmax = mo.ui.slider(
        start=2.0,
        stop=20.0,
        value=10.0,
        step=0.5,
        label="R_max (Å)",
        show_value=True,
    )
    residual_mode_box = mo.ui.switch(
        value=False,
        label="Residual = total − selected paths (off: total − all stored paths)",
    )
    show_paths_box = mo.ui.switch(value=True, label="Show individual path contributions")
    ft_controls = mo.vstack(
        [
            mo.md("### Fourier Transform"),
            mo.hstack([ft_kmin, ft_kmax, ft_dk], gap=2),
            mo.hstack([ft_kweight, ft_window, ft_rmax], gap=2),
            mo.hstack([residual_mode_box, show_paths_box], gap=4),
        ]
    )
    ft_controls
    return (
        ft_dk,
        ft_kmax,
        ft_kmin,
        ft_kweight,
        ft_rmax,
        ft_window,
        residual_mode_box,
        show_paths_box,
    )


@app.cell
def _(mo):
    equil_box = mo.ui.number(
        value=0, start=0, stop=10_000, step=1, label="Equilibration frames to skip"
    )
    n_paths_box = mo.ui.number(value=100, start=1, step=1, label="Max paths per site per frame")
    r_tol_box = mo.ui.number(value=0.25, start=0.01, stop=2.0, step=0.01, label="r_eff tolerance Å")
    skip_frames_box = mo.ui.number(
        value=0, start=0, stop=100_000, step=1, label="Traj skip frames (DW)"
    )
    cutoff_box = mo.ui.number(
        value=8.0, start=0.5, stop=20.0, step=0.1, label="Neighbor cutoff Å (DW)"
    )
    dw_tol_box = mo.ui.number(
        value=0.1, start=0.02, stop=1.0, step=0.01, label="DW shell grouping tol Å"
    )
    tol_angle_box = mo.ui.number(
        value=5.0, start=0.1, stop=45.0, step=0.5, label="Angle grouping tol (°)"
    )
    cutoff_3body_box = mo.ui.number(
        value=6.0, start=0.0, stop=20.0, step=0.1, label="3-body cutoff Å (0=skip)"
    )
    site_indices_box = mo.ui.text(
        value="",
        label="Site indices override (comma-separated, e.g. 125,126; blank=auto)",
        full_width=True,
    )
    k_step_box = mo.ui.number(
        value=0.05,
        start=0.01,
        stop=0.5,
        step=0.01,
        label="k-grid step Å⁻¹ (path recomputation)",
    )
    recompute_paths_box = mo.ui.checkbox(
        value=False,
        label="Recompute path χ from raw FEFF params",
    )
    advanced_controls = mo.vstack(
        [
            mo.hstack(
                [
                    mo.vstack([equil_box, n_paths_box, r_tol_box]),
                    mo.vstack([skip_frames_box, cutoff_box, dw_tol_box]),
                    mo.vstack([tol_angle_box, cutoff_3body_box]),
                ],
                gap=2,
            ),
            site_indices_box,
            mo.hstack([k_step_box, recompute_paths_box], gap=2),
        ]
    )
    advanced_controls
    return (
        cutoff_3body_box,
        cutoff_box,
        dw_tol_box,
        k_step_box,
        r_tol_box,
        recompute_paths_box,
        site_indices_box,
        skip_frames_box,
        tol_angle_box,
    )


@app.cell
def _(
    Atoms,
    btn_load,
    compute_chi_from_params,
    mo,
    np,
    orm,
    selected_node,
):
    merged_path_data = None
    total_chi_hdf5 = None
    kref_hdf5 = None
    absorber_el_h5 = None
    raw_aiida_structures = []
    feff_site_indices: list[int] = []

    mo.stop(
        not btn_load.value,
        mo.callout(
            mo.md("Select an AiiDA calculation above then click **▶ Load Calculation** to start."),
            kind="info",
        ),
    )
    mo.stop(
        selected_node is None,
        mo.callout(mo.md("No valid AiiDA calculation selected."), kind="warn"),
    )

    _node = selected_node
    # Resolve path contributions node from outputs or outgoing links
    pc = None
    if hasattr(_node, "outputs") and hasattr(_node.outputs, "path_contributions"):
        pc = _node.outputs.path_contributions
    elif hasattr(_node, "node_type") and "pathcontributions" in _node.node_type.lower():
        pc = _node
    elif hasattr(_node, "outputs") and hasattr(_node.outputs, "archive"):
        pc = _node.outputs.archive
    else:
        out_nodes = _node.base.links.get_outgoing().all_nodes()
        pc = next(
            (
                n
                for n in out_nodes
                if "pathcontributions" in n.node_type.lower() or "archive" in n.node_type.lower()
            ),
            None,
        )

    mo.stop(
        pc is None,
        mo.callout(
            mo.md(f"No path contributions found in calculation PK {_node.pk}."), kind="warn"
        ),
    )

    from md_exafs.viz import group_path_results

    paths = list(pc.iter_paths())
    mo.stop(
        not paths,
        mo.callout(mo.md(f"No individual paths stored in calculation PK {_node.pk}."), kind="warn"),
    )

    kref_hdf5 = np.arange(0.05, 20.0 + 0.05 / 2, 0.05)
    grouped = group_path_results(paths, r_bin_width=0.1)
    # Default sorting by contribution descending
    grouped.sort(key=lambda x: x.get("cw_ratio", 0.0), reverse=True)

    path_groups = []
    for p in grouped:
        fd = np.asarray(p["feff_data"])
        amp = fd[:, 1] * fd[:, 3]
        pha = fd[:, 0] + fd[:, 2]
        lam = fd[:, 4]
        rep = fd[:, 5]
        k_param = np.asarray(p.get("k", kref_hdf5))
        reff = float(p["r_eff"])
        degen = float(p.get("degeneracy", 1.0))
        sig2 = float(p.get("sig2", 0.0))

        chi_p = compute_chi_from_params(
            kref_hdf5, amp, pha, lam, rep, reff, degen, k_param, sigma2=sig2
        )
        n_samples = p.get("count", 1)
        cw = float(p.get("cw_ratio", 0.0))
        pg = {
            "path_key": p["path_key"],
            "scatterer": str(p.get("scatterer", "?")),
            "nlegs": int(p.get("nlegs", 2)),
            "r_eff_ref": reff,
            "r_effs": [reff],
            "chi_list": [chi_p],
            "chi_weights": [n_samples],
            "frame_set": {p["path_key"]},
            "kref": kref_hdf5,
            "sparse": False,
            "n_samples": n_samples,
            "contribution_pct": cw,
            "degeneracy": degen,
            "cw_ratio": cw,
            "amp": amp,
            "pha": pha,
            "lam": lam,
            "rep": rep,
            "k_param": k_param,
            "feff_data": fd,
        }
        path_groups.append(pg)

    total_spectra = max((pg["n_samples"] for pg in path_groups), default=1)
    feff_site_indices = sorted({p.site_idx for p in paths if p.site_idx is not None})
    n_sites = len(feff_site_indices) or 1

    total_chi_hdf5 = np.zeros_like(kref_hdf5)
    if hasattr(_node, "outputs"):
        xas = None
        if hasattr(_node.outputs, "averaged_xas"):
            xas = getattr(_node.outputs.averaged_xas, "all", None)
        if xas is None:
            xas = getattr(_node.outputs, "averaged_xas__all", None)
        if xas is not None and hasattr(xas, "get_array"):
            k_in = xas.get_array("k")
            chi_in = xas.get_array("chi_k")
            total_chi_hdf5 = np.interp(kref_hdf5, k_in, chi_in, left=0.0, right=0.0)

    if np.all(total_chi_hdf5 == 0.0):
        for pg in path_groups:
            total_chi_hdf5 += pg["chi_list"][0]

    _chi_sum_paths = np.zeros_like(total_chi_hdf5)
    for _pg in path_groups:
        _chi_sum_paths += _pg["chi_list"][0]
    _chi_residual = total_chi_hdf5 - _chi_sum_paths

    merged_path_data = {
        "merged_sites": {
            "path_groups": path_groups,
            "kref": kref_hdf5,
            "total_frames": total_spectra,
            "chi_residual": _chi_residual,
        }
    }
    absorber_el_h5 = getattr(pc, "absorber_element", None)

    # Extract structures / trajectory from node or caller
    _curr = _node
    if not isinstance(_curr, orm.ProcessNode):
        inc_procs = [
            n for n in _curr.base.links.get_incoming().all_nodes() if isinstance(n, orm.ProcessNode)
        ]
        if inc_procs:
            _curr = inc_procs[0]

    while _curr is not None and not raw_aiida_structures:
        if hasattr(_curr, "inputs"):
            if hasattr(_curr.inputs, "trajectory"):
                t_node = _curr.inputs.trajectory
                pos = t_node.get_array("positions")
                cells = t_node.get_array("cells") if "cells" in t_node.get_arraynames() else None
                pbc = getattr(t_node, "pbc", (True, True, True))
                syms = t_node.symbols
                raw_aiida_structures = [
                    Atoms(
                        symbols=syms,
                        positions=pos[i],
                        cell=cells[i] if cells is not None else None,
                        pbc=pbc,
                    )
                    for i in range(len(pos))
                ]
                break
            if hasattr(_curr.inputs, "structures"):
                try:
                    for _key in sorted(_curr.inputs.structures.keys()):
                        _struct = getattr(_curr.inputs.structures, _key)
                        if hasattr(_struct, "get_ase"):
                            raw_aiida_structures.append(_struct.get_ase())
                except Exception:
                    pass
                if raw_aiida_structures:
                    break
            if hasattr(_curr.inputs, "structure"):
                _struct = _curr.inputs.structure
                if hasattr(_struct, "get_ase"):
                    raw_aiida_structures = [_struct.get_ase()]
                    break

        for link in _curr.base.links.get_incoming().all():
            in_n = link.node
            if isinstance(in_n, orm.StructureData) and hasattr(in_n, "get_ase"):
                raw_aiida_structures.append(in_n.get_ase())
            elif isinstance(in_n, orm.TrajectoryData):
                pos = in_n.get_array("positions")
                cells = in_n.get_array("cells") if "cells" in in_n.get_arraynames() else None
                pbc = getattr(in_n, "pbc", (True, True, True))
                syms = in_n.symbols
                raw_aiida_structures = [
                    Atoms(
                        symbols=syms,
                        positions=pos[i],
                        cell=cells[i] if cells is not None else None,
                        pbc=pbc,
                    )
                    for i in range(len(pos))
                ]
                break
        _curr = getattr(_curr, "caller", None)

    _n_groups = len(path_groups)
    _site_idx_str = (
        ", ".join(str(s) for s in feff_site_indices[:5])
        + ("…" if len(feff_site_indices) > 5 else "")
        if feff_site_indices
        else "(unknown)"
    )
    mo.callout(
        mo.md(
            f"Loaded **{_n_groups} scattering path groups** · "
            f"**{n_sites} sites** · **{len(raw_aiida_structures)} structure frame(s)** · "
            f"Absorber: **{absorber_el_h5 or '(unknown)'}** · "
            f"FEFF sites: **{_site_idx_str}**"
        ),
        kind="success",
    )
    return (
        absorber_el_h5,
        feff_site_indices,
        kref_hdf5,
        merged_path_data,
        raw_aiida_structures,
        total_chi_hdf5,
    )


@app.cell
def _(
    ft_dk,
    ft_kmax,
    ft_kmin,
    ft_kweight,
    ft_rmax,
    ft_window,
    kref_hdf5,
    mo,
    perform_FT,
    total_chi_hdf5,
):
    g_total_hdf5 = None
    mo.stop(kref_hdf5 is None)
    g_total_hdf5 = perform_FT(
        kref_hdf5,
        total_chi_hdf5,
        kmin=ft_kmin.value,
        kmax=ft_kmax.value,
        kweight=ft_kweight.value,
        dk=ft_dk.value,
        k_window=ft_window.value,
        rmax=ft_rmax.value,
    )
    return (g_total_hdf5,)


@app.cell
def _(
    compute_chi_from_params,
    ft_dk,
    ft_kmax,
    ft_kmin,
    ft_kweight,
    ft_rmax,
    ft_window,
    g_total_hdf5,
    k_step_box,
    kref_hdf5,
    merged_path_data,
    np,
    perform_FT,
    recompute_paths_box,
    total_chi_hdf5,
):
    display_merged_data = merged_path_data
    display_kref = kref_hdf5
    display_total_chi = total_chi_hdf5
    display_g_total = g_total_hdf5

    if (
        recompute_paths_box.value
        and merged_path_data is not None
        and "amp" in merged_path_data["merged_sites"]["path_groups"][0]
    ):
        _k_step = float(k_step_box.value)
        _k_new = np.arange(0.05, 20.0 + _k_step / 2, _k_step)

        _new_pgs = []
        for _pg in merged_path_data["merged_sites"]["path_groups"]:
            if all(p in _pg for p in ("amp", "pha", "lam", "rep", "k_param")):
                _chi_r = compute_chi_from_params(
                    _k_new,
                    _pg["amp"],
                    _pg["pha"],
                    _pg["lam"],
                    _pg["rep"],
                    _pg["r_eff_ref"],
                    _pg["degeneracy"],
                    _pg["k_param"],
                    sigma2=_pg.get("sig2", 0.0),
                )
                _pg_new = dict(_pg)
                _pg_new["chi_list"] = [_chi_r]
                _pg_new["kref"] = _k_new
                _new_pgs.append(_pg_new)
            else:
                _new_pgs.append(_pg)

        _chi_sum = np.zeros_like(_k_new)
        _total_frames = merged_path_data["merged_sites"]["total_frames"]
        for _pg in _new_pgs:
            _w = _pg.get("chi_weights", [1])
            _n = _w[0] if _w else 1
            _chi_sum += _pg["chi_list"][0] * (_n / _total_frames)
        _chi_residual = np.interp(_k_new, kref_hdf5, total_chi_hdf5) - _chi_sum

        display_merged_data = {
            "merged_sites": {
                "path_groups": _new_pgs,
                "kref": _k_new,
                "total_frames": _total_frames,
                "chi_residual": _chi_residual,
            }
        }
        display_kref = _k_new
        display_total_chi = np.interp(_k_new, kref_hdf5, total_chi_hdf5)
        display_g_total = perform_FT(
            display_kref,
            display_total_chi,
            kmin=ft_kmin.value,
            kmax=ft_kmax.value,
            dk=ft_dk.value,
            kweight=ft_kweight.value,
            k_window=ft_window.value,
            rmax=ft_rmax.value,
        )
    return (
        display_g_total,
        display_kref,
        display_merged_data,
        display_total_chi,
    )


@app.cell
def _(
    Atoms,
    absorber_el_h5,
    btn_load,
    calculate_grouped_msrd,
    compute_adp_results,
    cutoff_3body_box,
    cutoff_box,
    dw_tol_box,
    feff_site_indices: list[int],
    kabsch_align,
    max_safe_mic_cutoff,
    mo,
    np,
    raw_aiida_structures,
    site_indices_box,
    skip_frames_box,
    tol_angle_box,
    unwrap_positions_pbc,
):
    avg_atoms = None
    msrd_2b = None
    msrd_3b = None
    dw_results = None

    mo.stop(not btn_load.value)

    _raw = None
    if raw_aiida_structures:
        _raw = raw_aiida_structures[skip_frames_box.value :]
        if not _raw:
            _raw = raw_aiida_structures

    if _raw:
        if len(_raw) > 1:
            with mo.status.spinner("Unwrapping PBC..."):
                _unwrapped = unwrap_positions_pbc(_raw)

            with mo.status.spinner("Kabsch alignment (2-pass)..."):
                _rough = kabsch_align(_unwrapped)
                _unwrapped = kabsch_align(_unwrapped, reference_pos=np.mean(_rough, axis=0))

            dw_results = compute_adp_results(_raw, _unwrapped)
        else:
            dw_results = {
                "b_factors": np.zeros(len(_raw[0])),
                "u_tensor": np.zeros((len(_raw[0]), 3, 3)),
                "avg_positions": _raw[0].get_positions(),
                "atom_names": _raw[0].get_chemical_symbols(),
                "avg_cell": _raw[0].get_cell().complete(),
            }

        avg_atoms = Atoms(
            symbols=dw_results["atom_names"],
            positions=dw_results["avg_positions"],
            cell=dw_results["avg_cell"],
            pbc=_raw[0].get_pbc(),
        )

        # Harmonise absorber selection with FEFF paths.
        _symbols = dw_results["atom_names"]
        _absorber_el = absorber_el_h5 or list(dict.fromkeys(_symbols))[0]

        _manual_override = site_indices_box.value.strip()
        if _manual_override:
            try:
                _central_indices = [
                    int(x.strip()) for x in _manual_override.split(",") if x.strip()
                ]
            except ValueError:
                _central_indices = []
                mo.callout(
                    mo.md("Invalid site indices override — must be comma-separated integers."),
                    kind="alert",
                )
        elif feff_site_indices:
            _central_indices = [i for i in feff_site_indices if i < len(_symbols)]
        else:
            _central_indices = [i for i, s in enumerate(_symbols) if s == _absorber_el]

        if not _central_indices:
            mo.callout(
                mo.md(
                    f"No valid central indices for absorber **{_absorber_el}**. "
                    "Check site-indices override or trajectory/HDF5 mismatch."
                ),
                kind="alert",
            )
            mo.stop()

        _site_source = (
            "manual" if _manual_override else ("HDF5" if feff_site_indices else "element match")
        )

        _cutoff = cutoff_box.value
        _cutoff_3b = cutoff_3body_box.value or None

        _warnings = []
        _max_safe = max_safe_mic_cutoff(_raw[0].get_cell().complete())
        if _max_safe is not None:
            if _cutoff > _max_safe:
                _warnings.append(
                    f"**cutoff** = {_cutoff:.3f} Å exceeds the maximum safe MIC "
                    f"cutoff **{_max_safe:.3f} Å**. Distances may be ambiguous; "
                    f"reduce cutoff to ≤ {_max_safe:.3f} Å or use a supercell."
                )
            if _cutoff_3b is not None and _cutoff_3b > _max_safe:
                _warnings.append(
                    f"**cutoff_3body** = {_cutoff_3b:.3f} Å exceeds the maximum safe "
                    f"MIC cutoff **{_max_safe:.3f} Å**. Angles/path lengths may be "
                    f"ambiguous; reduce cutoff_3body to ≤ {_max_safe:.3f} Å or use a "
                    f"supercell."
                )

        with mo.status.spinner(f"Computing MSRD paths for absorber={_absorber_el}..."):
            msrd_2b, msrd_3b = calculate_grouped_msrd(
                _raw,
                _central_indices,
                _absorber_el,
                cutoff=_cutoff,
                tol_dist=dw_tol_box.value,
                tol_angle=tol_angle_box.value,
                cutoff_3body=_cutoff_3b,
                exclude_hydrogen=True,
            )

        mo.callout(
            mo.md(
                f"Trajectory: **{len(_raw)} frames** · Absorber: **{_absorber_el}** "
                f"({len(_central_indices)} sites, source: {_site_source}) · "
                f"**{len(msrd_2b)} 2-body** + **{len(msrd_3b)} 3-body** MSRD groups"
            ),
            kind="success",
        )

        for _w in _warnings:
            mo.callout(mo.md(_w), kind="warn")

    return avg_atoms, dw_results, msrd_2b, msrd_3b


@app.cell
def _(display_merged_data, mo, msrd_2b, msrd_3b, pd, r_tol_box):
    mo.stop(display_merged_data is None)

    from md_exafs.debye_waller import match_msrd_paths_to_feff

    _pgs = display_merged_data["merged_sites"]["path_groups"]
    _tol = r_tol_box.value

    if msrd_2b is not None:
        _rows = match_msrd_paths_to_feff(
            res_2b=msrd_2b,
            res_3b=msrd_3b or [],
            path_groups=_pgs,
            r_tol=_tol,
        )
        for r in _rows:
            r["Reff_DW (Å)"] = r.get("reff_dw")
            r["σ² (Å²)"] = r.get("sigma2")
            r["N_pairs"] = r.get("count")
            r["Angle (°)"] = r.get("angle")
            r["Reff_EXAFS (Å)"] = r.get("reff_exafs")
            r["Nlegs_FEFF"] = r.get("nlegs_feff")
            r["FEFF match"] = r.get("feff_note")
    else:
        # Fallback when no trajectory is available: build table directly from FEFF path groups
        _rows = []
        for _gi, _pg in enumerate(_pgs):
            _rows.append(
                {
                    "dw_body": "2b" if _pg.get("nlegs", 2) == 2 else "3b",
                    "dw_idx": None,
                    "Body": f"{_pg.get('nlegs', 2)}-leg",
                    "Type": _pg.get("path_key", f"Path {_gi + 1}"),
                    "Scatterer": str(_pg.get("scatterer", "?")),
                    "Reff_DW (Å)": None,
                    "σ² (Å²)": float(_pg.get("sig2", 0.0)),
                    "N_pairs": int(_pg.get("degeneracy", 1)),
                    "Angle (°)": _pg.get("angle"),
                    "Reff_EXAFS (Å)": float(_pg.get("r_eff_ref", _pg.get("r_eff", 0.0))),
                    "Nlegs_FEFF": int(_pg.get("nlegs", 2)),
                    "group_idx": _gi,
                    "FEFF match": "FEFF path",
                    "contribution_pct": float(
                        _pg.get("contribution_pct", _pg.get("cw_ratio", 0.0))
                    ),
                }
            )

    path_table_df = pd.DataFrame(_rows)
    return (path_table_df,)


@app.cell
def _(contrib_range, path_table_df):
    filtered_path_table_df = path_table_df[
        (path_table_df["contribution_pct"] >= contrib_range.value[0])
        & (path_table_df["contribution_pct"] <= contrib_range.value[1])
    ]
    return (filtered_path_table_df,)


@app.cell
def _(filtered_path_table_df):
    display_path_table_df = filtered_path_table_df
    return (display_path_table_df,)


@app.cell
def _(display_path_table_df, mo):
    path_selector = None
    mo.stop(display_path_table_df is None)

    _display_cols = [
        "Body",
        "Type",
        "Reff_DW (Å)",
        "σ² (Å²)",
        "Angle (°)",
        "N_pairs",
        "Reff_EXAFS (Å)",
        "Nlegs_FEFF",
        "FEFF match",
        "contribution_pct",
    ]
    path_selector = mo.ui.table(
        display_path_table_df[_display_cols],
        selection="multi",
        label="Select one or more path groups",
    )
    path_selector
    return (path_selector,)


@app.cell
def _(merged_path_data, mo):
    mo.stop(merged_path_data is None)
    contrib_range = mo.ui.range_slider(
        start=0.0,
        stop=100.0,
        value=[0.0, 100.0],
        step=0.5,
        label="Contribution filter (% of total χ)",
        show_value=True,
        full_width=True,
    )
    mo.vstack(
        [
            mo.md("### Path contribution filter"),
            mo.md(
                "Only paths whose `contribution_pct` falls within this range "
                "appear in the selection table."
            ),
            contrib_range,
        ]
    )
    return (contrib_range,)


@app.cell
def _(display_merged_data, dw_scatter, mo, path_selector, path_table_df, pd):
    selected_pgs = []
    selected_rows = []
    mo.stop(display_merged_data is None)

    _pgs = display_merged_data["merged_sites"]["path_groups"]

    # Union selections from the table and the scatter chart.
    # Default to top 3 paths so the charts and 3D viewer immediately display on load!
    _sel_indices = set()
    if path_selector is not None and len(path_selector.value) > 0:
        _sel_indices.update(path_selector.value.index.tolist())
    elif dw_scatter is not None and len(dw_scatter.value) > 0:
        _sel_indices.update(dw_scatter.value.index.tolist())
    elif path_table_df is not None and len(path_table_df) > 0:
        _sel_indices.update(range(min(3, len(path_table_df))))

    for _row_idx in sorted(_sel_indices):
        _row = path_table_df.iloc[_row_idx]
        selected_rows.append(_row)
        _gi = _row["group_idx"]
        selected_pgs.append(_pgs[int(_gi)] if pd.notna(_gi) else None)
    return selected_pgs, selected_rows


@app.cell
def _(
    KMAX,
    KMIN,
    RMIN,
    alt,
    atomic_numbers,
    display_g_total,
    display_kref,
    display_merged_data,
    display_total_chi,
    ft_dk,
    ft_kmax,
    ft_kmin,
    ft_kweight,
    ft_rmax,
    ft_window,
    jmol_colors,
    mo,
    np,
    pd,
    perform_FT,
    residual_mode_box,
    selected_pgs,
    selected_rows,
    show_paths_box,
):
    mo.stop(not selected_pgs)

    _ft_kw = {
        "kmin": ft_kmin.value,
        "kmax": ft_kmax.value,
        "kweight": ft_kweight.value,
        "dk": ft_dk.value,
        "k_window": ft_window.value,
        "rmax": ft_rmax.value,
    }
    _kref = display_merged_data["merged_sites"]["kref"]
    _total_sites = display_merged_data["merged_sites"]["total_frames"]
    _k_mask = (_kref >= KMIN) & (_kref <= KMAX)

    def _jmol_hex(sym):
        _z = atomic_numbers.get(sym.split("-")[0], 0)
        _r, _g, _b = jmol_colors[_z]
        return f"#{int(_r * 255):02x}{int(_g * 255):02x}{int(_b * 255):02x}"

    # dash patterns for differentiating same-element paths
    _DASHES = [[1, 0], [8, 3], [4, 3], [2, 3], [6, 2, 2, 2]]

    # ── Build per-path labels, chi arrays, and Jmol colors ───────────────
    # DW groups without a matching FEFF path (selected_pgs entry is None) are skipped.
    # Multiple DW rows can map to the same FEFF path group (group_idx).  For the
    # chi sum we count each unique FEFF group once; the per-panel plot still shows
    # one curve per DW row so users can inspect individual DW entries.
    _path_labels = []
    _path_chis = []
    _path_colors = []
    _path_dashes = []
    _color_count: dict = {}  # jmol_hex → count (for dash cycling)
    _seen_group_indices: set[int] = set()  # FEFF groups already added to sum
    _chi_sum_sel = np.zeros_like(_kref)
    for _pg, _row in zip(selected_pgs, selected_rows, strict=False):
        if _pg is None:
            continue  # DW group with no FEFF match — skip chi
        _angle_str = (
            f"  θ={_row['Angle (°)']:.1f}°"
            if _row["Body"] == "3-body" and _row["Angle (°)"] is not None
            else ""
        )
        _lbl = f"{_row['Type']}  R={_row['Reff_DW (Å)']:.2f}Å  σ²={_row['σ² (Å²)']:.5f}{_angle_str}"
        _path_labels.append(_lbl)
        _col = _jmol_hex(_row["Scatterer"])
        _cnt = _color_count.get(_col, 0)
        _path_colors.append(_col)
        _path_dashes.append(_DASHES[_cnt % len(_DASHES)])
        _color_count[_col] = _cnt + 1
        _w = _pg.get("chi_weights", [])
        if _w:
            _chi_p = np.dot(np.array(_w), np.array(_pg["chi_list"])) / _total_sites
        else:
            _chi_p = np.mean(_pg["chi_list"], axis=0) * (len(_pg["frame_set"]) / _total_sites)
        _path_chis.append(_chi_p)
        # Only add to the sum once per unique FEFF path group.
        _gi_val = _row.get("group_idx")
        if pd.notna(_gi_val):
            _gi_int = int(_gi_val)
            if _gi_int not in _seen_group_indices:
                _seen_group_indices.add(_gi_int)
                _chi_sum_sel += _chi_p

    mo.stop(
        not _path_labels,
        mo.callout(mo.md("No selected DW groups have matching FEFF paths."), kind="info"),
    )

    # ── Color / dash scales (Jmol, dash-differentiated per element) ───────
    _n = len(_path_labels)
    _SUM_COL = "#cc3300"
    _HDF5_COL = "#111111"
    _RESID_COL = "#888888"

    _COMBINED = "── Combined"
    _panel_order = [_COMBINED] + _path_labels
    _trace_domain = _path_labels + [
        "Sum of selected",
        "HDF5 total",
        "FEFF residual",
        "Selection residual",
    ]
    _color_scale = alt.Scale(
        domain=_trace_domain,
        range=_path_colors + [_SUM_COL, _HDF5_COL, _RESID_COL, _RESID_COL],
    )
    _dash_scale = alt.Scale(
        domain=_trace_domain, range=_path_dashes + [[6, 3], [1, 0], [3, 3], [2, 2]]
    )
    _sw_scale = alt.Scale(domain=_trace_domain, range=[1.8] * _n + [2.5, 2.0, 1.5, 1.5])

    _kw = int(ft_kweight.value)
    _kw_label = f"k^{_kw}χ(k)" if _kw > 0 else "χ(k)"

    # ── k-space long-form table ───────────────────────────────────────────
    _rows_k = []
    for _lbl, _chi_p in zip(_path_labels, _path_chis, strict=False):
        for _k_val, _y_val in zip(_kref[_k_mask], (_chi_p * _kref**_kw)[_k_mask], strict=False):
            _rows_k.append({"k": _k_val, "k_chi": _y_val, "panel": _lbl, "trace": _lbl})

    _g_sum = perform_FT(_kref, _chi_sum_sel, **_ft_kw)
    # Sum of selected: native path k-grid
    for _k_val, _y_s in zip(_kref[_k_mask], (_chi_sum_sel * _kref**_kw)[_k_mask], strict=False):
        _rows_k.append(
            {
                "k": _k_val,
                "k_chi": _y_s,
                "panel": _COMBINED,
                "trace": "Sum of selected",
            }
        )
    # HDF5 total: its own native k-grid
    _k_mask_h5 = (display_kref >= KMIN) & (display_kref <= KMAX)
    for _k_val, _y_h in zip(
        display_kref[_k_mask_h5],
        (display_total_chi * display_kref**_kw)[_k_mask_h5],
        strict=False,
    ):
        _rows_k.append({"k": _k_val, "k_chi": _y_h, "panel": _COMBINED, "trace": "HDF5 total"})

    # Residual k-space in Combined panel
    _use_sel_residual = residual_mode_box.value
    _resid_label = "Selection residual" if _use_sel_residual else "FEFF residual"
    if _use_sel_residual:
        # total − sum of selected paths; interpolate path sum onto display_kref grid
        _chi_residual_k = display_total_chi - np.interp(display_kref, _kref, _chi_sum_sel)
        _resid_kref = display_kref
    else:
        _chi_residual_k = display_merged_data["merged_sites"].get("chi_residual")
        _resid_kref = display_kref
    if _chi_residual_k is not None:
        _k_mask_res_k = (_resid_kref >= KMIN) & (_resid_kref <= KMAX)
        for _k_val, _y_r in zip(
            _resid_kref[_k_mask_res_k],
            (_chi_residual_k * _resid_kref**_kw)[_k_mask_res_k],
            strict=False,
        ):
            _rows_k.append({"k": _k_val, "k_chi": _y_r, "panel": _COMBINED, "trace": _resid_label})

    # ── R-space long-form table ───────────────────────────────────────────
    _rows_r = []
    for _i, (_lbl, _chi_p, _pg) in enumerate(
        zip(_path_labels, _path_chis, selected_pgs, strict=False)
    ):
        _g_p = perform_FT(_kref, _chi_p, **_ft_kw)
        _r_mask = (_g_p.r >= RMIN) & (_g_p.r <= ft_rmax.value)
        for _r_val, _mag in zip(_g_p.r[_r_mask], _g_p.chir_mag[_r_mask], strict=False):
            _rows_r.append({"R": _r_val, "|χ(R)|": _mag, "panel": _lbl, "trace": _lbl})

    _r_mask_g = (display_g_total.r >= RMIN) & (display_g_total.r <= ft_rmax.value)
    _r_mask_s = (_g_sum.r >= RMIN) & (_g_sum.r <= ft_rmax.value)
    # Each trace uses its own R-grid as x
    for _r_val, _mag_s in zip(_g_sum.r[_r_mask_s], _g_sum.chir_mag[_r_mask_s], strict=False):
        _rows_r.append(
            {
                "R": _r_val,
                "|χ(R)|": _mag_s,
                "panel": _COMBINED,
                "trace": "Sum of selected",
            }
        )
    for _r_val, _mag_h in zip(
        display_g_total.r[_r_mask_g], display_g_total.chir_mag[_r_mask_g], strict=False
    ):
        _rows_r.append({"R": _r_val, "|χ(R)|": _mag_h, "panel": _COMBINED, "trace": "HDF5 total"})

    # Residual R-space in Combined panel
    if _chi_residual_k is not None:
        _g_res = perform_FT(_resid_kref, _chi_residual_k, **_ft_kw)
        _r_mask_res = (_g_res.r >= RMIN) & (_g_res.r <= ft_rmax.value)
        for _r_val, _mag_r in zip(
            _g_res.r[_r_mask_res], _g_res.chir_mag[_r_mask_res], strict=False
        ):
            _rows_r.append(
                {
                    "R": _r_val,
                    "|χ(R)|": _mag_r,
                    "panel": _COMBINED,
                    "trace": _resid_label,
                }
            )

    _df_k = pd.DataFrame(_rows_k)
    _df_r = pd.DataFrame(_rows_r)

    if not show_paths_box.value:
        _df_k = _df_k[_df_k["panel"] == _COMBINED]
        _df_r = _df_r[_df_r["panel"] == _COMBINED]
        _panel_order = [_COMBINED]

    # ── Chart builder ─────────────────────────────────────────────────────
    _row_enc = alt.Row(
        "panel:N",
        sort=_panel_order,
        header=alt.Header(labelFontSize=10, labelLimit=450, labelOrient="left", title=None),
    )

    # param-bound interval controls scale domain only — no mark greying.
    _zoom = alt.param(bind="scales", select={"type": "interval"})

    def _stacked(df, x_col, y_col, x_title, y_title):
        return (
            alt.Chart(df)
            .mark_line()
            .encode(
                x=alt.X(f"{x_col}:Q", title=x_title),
                y=alt.Y(f"{y_col}:Q", title=y_title),
                color=alt.Color(
                    "trace:N",
                    scale=_color_scale,
                    legend=alt.Legend(title="Trace", orient="right"),
                ),
                strokeDash=alt.StrokeDash("trace:N", scale=_dash_scale, legend=None),
                strokeWidth=alt.StrokeWidth("trace:N", scale=_sw_scale, legend=None),
                row=_row_enc,
                tooltip=[
                    alt.Tooltip(f"{x_col}:Q", format=".3f"),
                    alt.Tooltip(f"{y_col}:Q", format=".5f"),
                    alt.Tooltip("trace:N"),
                ],
            )
            .properties(width=500, height=120)
            .add_params(_zoom)
            .resolve_scale(y="independent")
        )

    _chart_k = _stacked(_df_k, "k", "k_chi", "k (Å⁻¹)", _kw_label)
    _chart_r = _stacked(_df_r, "R", "|χ(R)|", "R (Å)", "|χ(R)|")

    stacked_k_chart = mo.ui.altair_chart(_chart_k)
    stacked_r_chart = mo.ui.altair_chart(_chart_r)
    return stacked_k_chart, stacked_r_chart


@app.cell
def _(mo):
    dw_show_all = mo.ui.switch(
        value=True,
        label="DW plot: show all paths (off = filtered paths only)",
    )
    return (dw_show_all,)


@app.cell
def _(
    alt,
    atomic_numbers,
    dw_show_all,
    filtered_path_table_df,
    jmol_colors,
    mo,
    path_table_df,
    pd,
):
    dw_scatter = None
    mo.stop(path_table_df is None)

    _df_dw = (path_table_df if dw_show_all.value else filtered_path_table_df).copy()
    mo.stop(
        len(_df_dw) == 0,
        mo.callout(mo.md("No DW groups found — load a trajectory file above."), kind="info"),
    )

    _df_dw["label"] = _df_dw["Type"] + "  R_DW=" + _df_dw["Reff_DW (Å)"].round(3).astype(str) + "Å"
    _df_dw["FEFF match filled"] = _df_dw["FEFF match"].fillna("")
    _df_dw["Angle str"] = _df_dw["Angle (°)"].apply(
        lambda x: f"{x:.1f}°" if x is not None and not pd.isna(x) else ""
    )

    def _jmol_hex(sym):
        _z = atomic_numbers.get(sym.split("-")[0], 0)
        _r, _g, _b = jmol_colors[_z]
        return f"#{int(_r * 255):02x}{int(_g * 255):02x}{int(_b * 255):02x}"

    _scat_els = sorted(_df_dw["Scatterer"].unique())
    _jmol_scale = alt.Scale(
        domain=_scat_els,
        range=[_jmol_hex(s) for s in _scat_els],
    )

    _pts = (
        alt.Chart(_df_dw)
        .mark_point(filled=True)
        .encode(
            x=alt.X("Reff_DW (Å):Q", title="Reff_DW (Å)"),
            y=alt.Y("σ² (Å²):Q", title="σ² (Å²)"),
            color=alt.Color("Scatterer:N", scale=_jmol_scale),
            size=alt.Size(
                "contribution_pct:Q",
                title="Contrib. %",
                scale=alt.Scale(domain=[0, 30], range=[30, 300], clamp=True),
                legend=alt.Legend(orient="bottom", titleLimit=100),
            ),
            shape=alt.Shape(
                "Body:N",
                scale=alt.Scale(domain=["2-body", "3-body"], range=["circle", "triangle-up"]),
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Path"),
                alt.Tooltip("Reff_DW (Å):Q", format=".4f"),
                alt.Tooltip("σ² (Å²):Q", format=".6f"),
                alt.Tooltip("Angle str:N", title="Angle"),
                alt.Tooltip("FEFF match filled:N", title="FEFF match"),
                alt.Tooltip("contribution_pct:Q", format=".2f", title="Contrib. %"),
            ],
        )
        .properties(height=320, width="container", title="σ² vs Reff_DW — click to select")
        .interactive()
    )

    dw_scatter = mo.ui.altair_chart(_pts)
    return (dw_scatter,)


@app.cell
def _(dw_scatter, dw_show_all, mo, viewer):
    _dw_panel = mo.vstack([dw_show_all, dw_scatter]) if dw_scatter is not None else None
    _display = mo.hstack([viewer, _dw_panel], widths=[30, 70]) if _dw_panel is not None else viewer
    _display
    return


@app.cell
def _(mo, selected_rows):
    show_all_instances_cb = mo.ui.checkbox(
        label="Show all equivalent site instances",
        value=True,
    )
    _n = len(selected_rows) if selected_rows else 0
    mo.vstack([mo.md(f"_{_n} path group(s) selected._"), show_all_instances_cb])
    return (show_all_instances_cb,)


@app.cell
def _(mo, selected_rows, stacked_k_chart, stacked_r_chart):
    mo.stop(not selected_rows or stacked_k_chart is None)
    mo.hstack([stacked_k_chart, stacked_r_chart], widths="equal")
    return


@app.cell
def _(
    ASEAdapter,
    AtomsViewer,
    BaseWidget,
    atomic_numbers,
    avg_atoms,
    dw_results,
    find_mic,
    guiConfig,
    jmol_colors,
    mo,
    msrd_2b,
    msrd_3b,
    selected_rows,
    show_all_instances_cb,
):
    viewer = mo.callout(mo.md("Load a trajectory to enable 3-D visualisation."), kind="info")
    mo.stop(avg_atoms is None)

    _pos = dw_results["avg_positions"]
    _cell = avg_atoms.get_cell()
    _pbc = avg_atoms.get_pbc()

    def _jmol_hex3d(sym):
        _z = atomic_numbers.get(sym.split("-")[0], 0)
        _r, _g, _b = jmol_colors[_z]
        return f"#{int(_r * 255):02x}{int(_g * 255):02x}{int(_b * 255):02x}"

    _vf_groups = {}
    _highlight = set()

    if selected_rows:
        # One color per selected path, keyed on scatterer element.
        # If two paths share the same scatterer element, lighten the second by blending with white.
        _color_use: dict = {}  # scatterer_sym → count
        _arrow_colors = []
        for _row3d in selected_rows:
            _scat_sym = _row3d["Scatterer"].split("-")[0]
            _base = _jmol_hex3d(_scat_sym)
            _cnt = _color_use.get(_scat_sym, 0)
            if _cnt == 0:
                _arrow_colors.append(_base)
            else:
                # blend toward white by 30% per repeat
                _bv = int(_base[1:3], 16), int(_base[3:5], 16), int(_base[5:7], 16)
                _f = min(0.30 * _cnt, 0.70)
                _rv = tuple(int(_c + (_f * (255 - _c))) for _c in _bv)
                _arrow_colors.append("#{:02x}{:02x}{:02x}".format(*_rv))
            _color_use[_scat_sym] = _cnt + 1

        for _pi, (_row3d, _color3d) in enumerate(zip(selected_rows, _arrow_colors, strict=False)):
            _body = _row3d["dw_body"]
            _dw_i = int(_row3d["dw_idx"])
            _m = msrd_2b[_dw_i] if _body == "2b" else (msrd_3b or [])[_dw_i]
            _all_indices = _m["atom_indices"]
            _active = _all_indices if show_all_instances_cb.value else _all_indices[:1]

            if _body == "2b":
                # 2-body: draw go (absorber→scatterer) and return arrows
                _orig_go, _vec_go, _orig_ret, _vec_ret = [], [], [], []
                for _pair in _active:
                    _abs_i, _scat_i = _pair
                    _v_raw = _pos[_scat_i] - _pos[_abs_i]
                    _v_mic, _ = find_mic([_v_raw], _cell, _pbc)
                    _v = _v_mic[0]
                    _orig_go.append(_pos[_abs_i].tolist())
                    _vec_go.append(_v.tolist())
                    _orig_ret.append((_pos[_abs_i] + _v).tolist())
                    _vec_ret.append((-_v).tolist())
                    _highlight.add(_abs_i)
                    _highlight.add(_scat_i)
                _vf_groups[f"go_{_pi}"] = {
                    "origins": _orig_go,
                    "vectors": _vec_go,
                    "color": _color3d,
                    "radius": 0.12,
                }
                _vf_groups[f"ret_{_pi}"] = {
                    "origins": _orig_ret,
                    "vectors": _vec_ret,
                    "color": _color3d,
                    "radius": 0.07,
                }

            else:
                # 3-body: draw triangular path c→n1→n2→c using chained MIC origins
                _leg1_origs, _leg1_vecs = [], []
                _leg2_origs, _leg2_vecs = [], []
                _leg3_origs, _leg3_vecs = [], []
                for _triple in _active:
                    _c, _n1, _n2 = _triple
                    # leg c→n1
                    _v1_mic, _ = find_mic([_pos[_n1] - _pos[_c]], _cell, _pbc)
                    _v1 = _v1_mic[0]
                    _orig_c = _pos[_c]
                    # leg n1→n2 (chained origin so the triangle closes properly)
                    _v12_mic, _ = find_mic([_pos[_n2] - _pos[_n1]], _cell, _pbc)
                    _v12 = _v12_mic[0]
                    _orig_n1 = _orig_c + _v1
                    # leg n2→c closes the triangle
                    _orig_n2 = _orig_n1 + _v12
                    _v_ret = -(_v1 + _v12)
                    _leg1_origs.append(_orig_c.tolist())
                    _leg1_vecs.append(_v1.tolist())
                    _leg2_origs.append(_orig_n1.tolist())
                    _leg2_vecs.append(_v12.tolist())
                    _leg3_origs.append(_orig_n2.tolist())
                    _leg3_vecs.append(_v_ret.tolist())
                    _highlight.update([_c, _n1, _n2])
                _vf_groups[f"leg1_{_pi}"] = {
                    "origins": _leg1_origs,
                    "vectors": _leg1_vecs,
                    "color": _color3d,
                    "radius": 0.12,
                }
                _vf_groups[f"leg2_{_pi}"] = {
                    "origins": _leg2_origs,
                    "vectors": _leg2_vecs,
                    "color": _color3d,
                    "radius": 0.09,
                }
                _vf_groups[f"leg3_{_pi}"] = {
                    "origins": _leg3_origs,
                    "vectors": _leg3_vecs,
                    "color": _color3d,
                    "radius": 0.07,
                }

    _viewer = AtomsViewer(BaseWidget(guiConfig=guiConfig))
    _viewer.atoms = ASEAdapter.to_weas(avg_atoms)
    _viewer.model_style = 0
    _viewer.atom_scales = [0.333] * len(avg_atoms)
    _viewer.boundary = [[-0.2, 1.2], [-0.2, 1.2], [-0.2, 1.2]]
    _viewer.show_bonded_atoms = True
    if _highlight:
        _viewer.highlight = list(_highlight)
    if _vf_groups:
        _viewer.vf.settings = _vf_groups
        _viewer.vf.show = True
    viewer = _viewer._widget
    return (viewer,)


@app.cell
def _(mo, path_table_df):
    mo.stop(path_table_df is None)
    mo.ui.table(path_table_df, label="All path groups")
    return


if __name__ == "__main__":
    app.run()
