"""Marimo notebook for MD Debye-Waller & FEFF Analysis with AiiDA Integration.

Computes Debye-Waller factors and MSRD for EXAFS/FEFF from MD trajectories,
supporting both AiiDA database TrajectoryData nodes and direct file uploads.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "aiida-core>=2.3,<3",
#     "altair>=5.0",
#     "ase>=3.22",
#     "marimo>=0.16.4",
#     "md-exafs>=0.3.0,<0.4",
#     "numpy>=1.21",
#     "pandas>=2.0",
#     "weas-widget>=0.1.26",
# ]
# ///

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium", app_title="MD Debye-Waller & FEFF Analysis")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(r"""
    # MD Debye-Waller & FEFF Analysis

    This notebook computes **Debye-Waller factors** (B-factors / ADP tensors) and
    **Mean Square Relative Displacements (MSRD)** for EXAFS/FEFF analysis from
    molecular dynamics trajectories.

    ### Workflow
    1. Select an MD trajectory from the **AiiDA database** or **upload a file**
    2. Unwrap PBC positions and optionally Kabsch-align frames
    3. Compute per-atom U tensors and B-factors → export CIF with ADP
    4. Select absorber site(s) to compute 2-body and 3-body MSRD paths
    """)
    return


@app.cell
def _(mo):
    mo.callout(
        mo.md(
            "**Scope** — MSRDs here are classical: they carry no zero-point "
            "contribution, so they are least reliable for light scatterers and "
            "for temperatures well below the Debye temperature. Shell "
            "assignment depends on distance and angle grouping tolerances; "
            "check the resolved path list before using the values."
        ),
        kind="info",
    )
    return


@app.cell
def _():
    import logging
    import tempfile
    from pathlib import Path

    import altair as alt
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

    guiConfig = {"controls": {"enabled": False}}

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("dw_notebook")

    try:
        from aiida import load_profile, orm
    except ImportError:
        load_profile, orm = None, None

    return (
        ASEAdapter,
        Atoms,
        AtomsViewer,
        BaseWidget,
        Path,
        alt,
        ase_read,
        atomic_numbers,
        find_mic,
        guiConfig,
        jmol_colors,
        load_profile,
        logger,
        np,
        orm,
        pd,
        tempfile,
    )


@app.cell
def _(mo):
    mo.md("""
    ## 1 · Trajectory Source & Parameters
    """)
    return


@app.cell
def _(mo):
    source_selector = mo.ui.radio(
        options=["AiiDA Database", "Upload File"],
        value="AiiDA Database",
        label="Trajectory Source:",
    )
    return (source_selector,)


@app.cell
def _(load_profile, orm):
    trajectories_map = {}
    if load_profile is not None and orm is not None:
        try:
            load_profile()
            _qb = orm.QueryBuilder()
            _qb.append(
                orm.TrajectoryData,
                project=["id", "label", "ctime", "attributes"],
                tag="traj",
            )
            _qb.order_by({orm.TrajectoryData: {"ctime": "desc"}})
            for pk, label, ctime, raw_attrs in _qb.all():
                attrs = raw_attrs or {}
                stepids = attrs.get("stepids") or attrs.get("step_ids")
                num_frames = len(stepids) if stepids else attrs.get("num_frames")
                frame_str = f" ({num_frames} frames)" if num_frames else ""
                ctime_str = (
                    ctime.strftime("%Y-%m-%d %H:%M") if hasattr(ctime, "strftime") else str(ctime)
                )
                display_label = f"PK {pk}: {label or 'unlabeled'}{frame_str} - {ctime_str}"
                trajectories_map[display_label] = pk
        except Exception as exc:  # noqa: BLE001
            trajectories_map[f"Could not connect to AiiDA: {exc}"] = None
    else:
        trajectories_map["AiiDA not available in environment"] = None

    return (trajectories_map,)


@app.cell
def _(mo, trajectories_map):
    default_label = next((k for k, v in trajectories_map.items() if v is not None), None)
    aiida_dropdown = mo.ui.dropdown(
        options=trajectories_map,
        value=default_label,
        label="Select AiiDA Trajectory:",
    )
    custom_pk = mo.ui.text(
        placeholder="e.g. 123 (overrides dropdown)",
        label="Or enter PK directly:",
    )
    trajectory_file = mo.ui.file(
        label="Upload trajectory file (.xyz, .cif, etc.):",
        filetypes=[
            ".xyz",
            ".traj",
            ".extxyz",
            ".vasp",
            ".POSCAR",
            ".cif",
            ".lammps",
            ".dump",
            ".nc",
            ".h5",
        ],
        multiple=False,
    )
    return aiida_dropdown, custom_pk, trajectory_file


@app.cell
def _(aiida_dropdown, custom_pk, mo, source_selector, trajectory_file):
    if source_selector.value == "AiiDA Database":
        source_ui = mo.vstack(
            [
                source_selector,
                mo.hstack([aiida_dropdown, custom_pk], gap=2),
            ]
        )
    else:
        source_ui = mo.vstack(
            [
                source_selector,
                trajectory_file,
            ]
        )
    source_ui
    return (source_ui,)


@app.cell
def _(Path, aiida_dropdown, custom_pk, mo, source_selector, trajectory_file):
    skip_frames = mo.ui.number(
        value=0,
        start=0,
        stop=100_000,
        step=1,
        label="Frames to skip at start:",
    )
    stride_frames = mo.ui.number(
        value=1,
        start=1,
        stop=10_000,
        step=1,
        label="Stride (subsample every N frames):",
    )
    no_align = mo.ui.switch(label="Skip Kabsch alignment", value=False)

    if source_selector.value == "AiiDA Database":
        _raw_val = custom_pk.value.strip() or aiida_dropdown.value
        _sel_pk = str(_raw_val).strip() if _raw_val is not None else ""
        _default_prefix = f"aiida_traj_{_sel_pk}" if _sel_pk else "aiida_traj"
    else:
        _default_prefix = (
            Path(trajectory_file.value[0].name).stem if trajectory_file.value else "output"
        )
    output_prefix = mo.ui.text(value=_default_prefix, label="Output file prefix:")

    mo.hstack(
        [
            mo.vstack([skip_frames, stride_frames, output_prefix]),
            mo.vstack([no_align]),
        ],
        gap=2,
    )
    return no_align, output_prefix, skip_frames, stride_frames


@app.cell
def _(mo):
    mo.md("""
    ## 2 · Core Functions (from md_exafs)
    """)
    return


@app.cell
def _(ASEAdapter, AtomsViewer, BaseWidget, guiConfig):
    def view_atoms(atoms, model_style=1):
        v = AtomsViewer(BaseWidget(guiConfig=guiConfig))
        v.atoms = ASEAdapter.to_weas(atoms)
        v.model_style = model_style
        return v._widget

    return (view_atoms,)


@app.cell
def _():
    from md_exafs.debye_waller import (
        _max_safe_mic_cutoff as max_safe_mic_cutoff,
    )
    from md_exafs.debye_waller import (
        calculate_grouped_msrd,
        compute_adp_results,
        kabsch_align,
        parse_site_specification,
        save_cif_with_adp,
        unwrap_positions_pbc,
    )

    return (
        calculate_grouped_msrd,
        compute_adp_results,
        kabsch_align,
        max_safe_mic_cutoff,
        parse_site_specification,
        save_cif_with_adp,
        unwrap_positions_pbc,
    )


@app.cell
def _(mo):
    mo.md("""
    ## 3 · Load Trajectory
    """)
    return


@app.cell
def _(
    Atoms,
    Path,
    aiida_dropdown,
    ase_read,
    custom_pk,
    load_profile,
    mo,
    orm,
    skip_frames,
    source_selector,
    stride_frames,
    tempfile,
    trajectory_file,
):
    structures = None
    _load_status = mo.callout(
        mo.md("⬆️  Select an AiiDA trajectory or upload a trajectory file above to begin."),
        kind="info",
    )

    if source_selector.value == "AiiDA Database":
        _raw_pk = custom_pk.value.strip() or aiida_dropdown.value
        _selected_pk = str(_raw_pk).strip() if _raw_pk is not None else ""
        if _selected_pk:
            if orm is None or load_profile is None:
                _load_status = mo.callout(
                    mo.md("❌ AiiDA is not available in the current Python environment."),
                    kind="danger",
                )
            else:
                try:
                    load_profile()
                    node = orm.load_node(int(_selected_pk))
                    if not isinstance(node, orm.TrajectoryData):
                        _load_status = mo.callout(
                            mo.md(
                                f"❌ Node PK {_selected_pk} is a `{type(node).__name__}`, not a `TrajectoryData`."
                            ),
                            kind="danger",
                        )
                    else:
                        symbols = node.symbols
                        pos_array = node.get_array("positions")
                        has_cells = "cells" in node.get_arraynames()
                        cell_array = node.get_array("cells") if has_cells else None
                        pbc = getattr(node, "pbc", (True, True, True)) if has_cells else False

                        n_total = len(pos_array)
                        start_idx = min(skip_frames.value, n_total)
                        stride = max(1, stride_frames.value)
                        frame_indices = list(range(start_idx, n_total, stride))

                        if len(frame_indices) < 2:
                            _load_status = mo.callout(
                                mo.md(
                                    f"❌ Selected trajectory has only **{len(frame_indices)} frame(s)** "
                                    f"after applying skip ({skip_frames.value}) and stride ({stride}). "
                                    "At least 2 frames are required."
                                ),
                                kind="danger",
                            )
                        else:
                            _raw = [
                                Atoms(
                                    symbols=symbols,
                                    positions=pos_array[i],
                                    cell=cell_array[i] if has_cells else None,
                                    pbc=pbc,
                                )
                                for i in frame_indices
                            ]
                            structures = _raw
                            elements_str = ", ".join(sorted(set(symbols)))
                            _load_status = mo.callout(
                                mo.md(
                                    f"✅ Loaded **{len(structures)} frames** from AiiDA TrajectoryData "
                                    f"(PK {_selected_pk}, label: `{node.label or 'unlabeled'}`) · "
                                    f"**{len(symbols)} atoms** per frame · "
                                    f"Elements: `{elements_str}`"
                                ),
                                kind="success",
                            )
                except Exception as _e:  # noqa: BLE001
                    _load_status = mo.callout(
                        mo.md(f"❌ Failed to load AiiDA trajectory PK {_selected_pk}: `{_e}`"),
                        kind="danger",
                    )
    else:
        if trajectory_file.value:
            _tf = trajectory_file.value[0]
            _suffix = Path(_tf.name).suffix or ".xyz"
            _tmp = tempfile.NamedTemporaryFile(suffix=_suffix, delete=False)
            _tmp.write(_tf.contents)
            _tmp.close()
            try:
                stride = max(1, stride_frames.value)
                _raw = ase_read(_tmp.name, index=f"{skip_frames.value}::{stride}")
                if not isinstance(_raw, list):
                    _raw = [_raw]

                if len(_raw) < 2:
                    _load_status = mo.callout(
                        mo.md(
                            f"❌ Trajectory has only **{len(_raw)} frame(s)** after skipping. "
                            "At least 2 frames are required."
                        ),
                        kind="danger",
                    )
                else:
                    structures = _raw
                    _syms_0 = _raw[0].get_chemical_symbols()
                    elements_str = ", ".join(sorted(set(_syms_0)))
                    _load_status = mo.callout(
                        mo.md(
                            f"✅ Loaded **{len(structures)} frames** · "
                            f"**{len(_syms_0)} atoms** per frame · "
                            f"Elements: `{elements_str}`"
                        ),
                        kind="success",
                    )
            except Exception as _e:  # noqa: BLE001
                _load_status = mo.callout(
                    mo.md(f"❌ Failed to load trajectory: `{_e}`"),
                    kind="danger",
                )
            finally:
                Path(_tmp.name).unlink(missing_ok=True)

    _load_status
    return (structures,)


@app.cell
def _(mo):
    mo.md("""
    ## 4 · Unwrap & Align
    """)
    return


@app.cell
def _(kabsch_align, logger, mo, no_align, structures, unwrap_positions_pbc):
    unwrapped = None
    _status = mo.md("")

    if structures is not None:
        with mo.status.spinner("Unwrapping PBC positions..."):
            unwrapped = unwrap_positions_pbc(structures)

        if not no_align.value:
            with mo.status.spinner("Kabsch alignment – pass 1…"):
                _rough = kabsch_align(unwrapped)
                _avg = __import__("numpy").mean(_rough, axis=0)
            with mo.status.spinner("Kabsch alignment – pass 2…"):
                unwrapped = kabsch_align(unwrapped, reference_pos=_avg)
            logger.info("Two-pass Kabsch alignment complete.")
        else:
            logger.info("Kabsch alignment skipped.")

        _status = mo.callout(
            mo.md(f"✅ Trajectory processed · Shape: `{unwrapped.shape}` (frames × atoms × xyz)"),
            kind="success",
        )

    _status
    return (unwrapped,)


@app.cell
def _(mo, structures, view_atoms):
    if structures is not None:
        mo.output.append(view_atoms(structures[0]))
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5 · B-factors & ADP Tensor
    """)
    return


@app.cell
def _(
    compute_adp_results,
    mo,
    np,
    output_prefix,
    save_cif_with_adp,
    structures,
    unwrapped,
):
    results = None
    _b_status = mo.md("")

    if unwrapped is not None and structures is not None:
        results = compute_adp_results(structures, unwrapped)
        _b_factors = results["b_factors"]

        # Per-element summary table
        _names = results["atom_names"]
        _unique = sorted(set(_names))
        _rows = []
        for _el in _unique:
            _mask = np.array([n == _el for n in _names])
            _bvals = _b_factors[_mask]
            _rows.append(
                {
                    "Element": _el,
                    "N atoms": int(_mask.sum()),
                    "Mean B (Å²)": f"{np.mean(_bvals):.3f}",
                    "Std B (Å²)": f"{np.std(_bvals):.3f}",
                    "Min B (Å²)": f"{np.min(_bvals):.3f}",
                    "Max B (Å²)": f"{np.max(_bvals):.3f}",
                }
            )
        _overall = f"{np.mean(_b_factors):.3f}"

        # CIF download button
        _cif_content = save_cif_with_adp(results)
        _cif_filename = f"{output_prefix.value}_with_adp.cif"
        _download_btn = mo.download(
            data=_cif_content.encode(),
            filename=_cif_filename,
            label="⬇ Download CIF with ADP",
        )

        _b_status = mo.vstack(
            [
                mo.md(
                    f"**Mean isotropic B-factor (all atoms):** `{_overall} Å²` "
                    f"({len(_names)} atoms, {len(structures)} frames)"
                ),
                mo.ui.table(_rows),
                _download_btn,
            ]
        )

    _b_status
    return (results,)


@app.cell
def _(Atoms, structures):
    avg_atoms = None
    if structures is not None:
        avg_atoms = structures[0].copy()
        avg_atoms.wrap()
    return (avg_atoms,)


@app.cell
def _(mo):
    mo.md("""
    ## 6 · B-factor Plot
    """)
    return


@app.cell
def _(alt, atomic_numbers, jmol_colors, mo, np, pd, results):
    _plot = mo.md("_Run steps above first._")

    if results is not None:
        _b = results["b_factors"]
        _names = results["atom_names"]
        _df_b = pd.DataFrame(
            {
                "Atom index": np.arange(len(_b)),
                "Element": _names,
                "B-factor (Å²)": _b,
            }
        )

        def _jmol_hex(sym):
            z = atomic_numbers.get(sym, 0)
            r, g, b = jmol_colors[z]
            return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

        _unique_els = sorted(set(_names))
        _el_color_scale = alt.Scale(
            domain=_unique_els,
            range=[_jmol_hex(el) for el in _unique_els],
        )

        _hover_b = alt.selection_point(on="mouseover", nearest=True, empty=False)

        _pts = (
            alt.Chart(_df_b)
            .mark_point(filled=True)
            .encode(
                x=alt.X("Atom index:Q", title="Atom index"),
                y=alt.Y("B-factor (Å²):Q", title="B-factor (Å²)"),
                color=alt.Color("Element:N", title="Element", scale=_el_color_scale),
                size=alt.condition(_hover_b, alt.value(120), alt.value(25)),
                opacity=alt.condition(_hover_b, alt.value(1.0), alt.value(0.6)),
                tooltip=[
                    alt.Tooltip("Atom index:Q", title="Atom index"),
                    alt.Tooltip("Element:N", title="Element"),
                    alt.Tooltip("B-factor (Å²):Q", format=".4f", title="B (Å²)"),
                ],
            )
            .add_params(_hover_b)
        )

        _mean_lines = (
            alt.Chart(_df_b)
            .mark_rule(strokeDash=[4, 4], strokeWidth=1, opacity=0.6)
            .encode(
                y=alt.Y("mean(B-factor (Å²)):Q"),
                color=alt.Color("Element:N", scale=_el_color_scale),
                tooltip=[
                    alt.Tooltip("Element:N", title="Element"),
                    alt.Tooltip("mean(B-factor (Å²)):Q", format=".4f", title="Mean B (Å²)"),
                ],
            )
        )

        _plot = (
            alt.layer(_mean_lines, _pts)
            .properties(height=300, width="container", title="Debye-Waller factors per atom")
            .interactive()
        )

    _plot
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 7 · MSRD Path Analysis

    Specify an **absorber site** to calculate mean square relative displacements
    for EXAFS/FEFF.

    | Format | Meaning |
    |--------|----------|
    | `K` | All K atoms |
    | `K.0` | First K atom (0-based within element) |
    | `K.0-2` | First three K atoms (inclusive range) |
    | `11` | Atom with global index 11 (0-based, any element) |
    | `11-20` | Atoms 11–20 (0-based, inclusive) |

    Indices are 0-based, matching the pipeline absorber convention.
    """)
    return


@app.cell
def _(mo):
    element_spec = mo.ui.text(
        placeholder="e.g.  K  or  Cu.0  or  11-20",
        label="Absorber site specification:",
    )
    cutoff = mo.ui.number(
        value=3.5,
        start=0.5,
        stop=20.0,
        step=0.1,
        label="Neighbor cutoff (Å):",
    )
    tol_dist = mo.ui.number(
        value=0.1,
        start=0.01,
        stop=2.0,
        step=0.01,
        label="Distance grouping tolerance (Å):",
    )
    tol_angle = mo.ui.number(
        value=5.0,
        start=0.1,
        stop=45.0,
        step=0.5,
        label="Angle grouping tolerance (°):",
    )
    cutoff_3body = mo.ui.number(
        value=0.0,
        start=0.0,
        stop=20.0,
        step=0.1,
        label="3-body neighbor cutoff (Å) (0 = skip):",
    )
    exclude_hydrogen_cb = mo.ui.checkbox(
        label="Exclude hydrogen from neighbor search",
        value=True,
    )
    run_msrd = mo.ui.run_button(label="▶  Run MSRD Analysis")

    mo.vstack(
        [
            mo.hstack(
                [
                    mo.vstack([element_spec, cutoff, tol_dist]),
                    mo.vstack([cutoff_3body, tol_angle, exclude_hydrogen_cb]),
                ],
                gap=2,
            ),
            run_msrd,
        ]
    )
    return (
        cutoff,
        cutoff_3body,
        element_spec,
        exclude_hydrogen_cb,
        run_msrd,
        tol_angle,
        tol_dist,
    )


@app.cell
def _(
    calculate_grouped_msrd,
    cutoff,
    cutoff_3body,
    element_spec,
    exclude_hydrogen_cb,
    max_safe_mic_cutoff,
    mo,
    output_prefix,
    parse_site_specification,
    pd,
    results,
    run_msrd,
    structures,
    tol_angle,
    tol_dist,
    unwrapped,
):
    _msrd_ui = mo.md("_Configure absorber site and click **Run MSRD Analysis**._")
    msrd_df = None
    msrd_path_indices = None

    if run_msrd.value and structures is not None and unwrapped is not None and results is not None:
        _spec = element_spec.value.strip()
        if not _spec:
            _msrd_ui = mo.callout(mo.md("⚠️ Please enter a site specification."), kind="warn")
        else:
            _symbols = structures[0].get_chemical_symbols()
            try:
                _indices = parse_site_specification(_spec, _symbols)
            except ValueError as _err:
                _msrd_ui = mo.callout(mo.md(f"❌ {_err}"), kind="danger")
                _indices = None

            if _indices is not None:
                _c3b = cutoff_3body.value if cutoff_3body.value != 0 else 0

                _warnings = []
                _max_safe = max_safe_mic_cutoff(structures[0].get_cell().complete())
                if _max_safe is not None:
                    if cutoff.value > _max_safe:
                        _warnings.append(
                            f"**cutoff** = {cutoff.value:.3f} Å exceeds the "
                            f"maximum safe MIC cutoff **{_max_safe:.3f} Å**. "
                            f"Distances may be ambiguous; reduce cutoff to ≤ {_max_safe:.3f} Å "
                            f"or use a supercell."
                        )
                    if _c3b > 0 and _c3b > _max_safe:
                        _warnings.append(
                            f"**cutoff_3body** = {_c3b:.3f} Å exceeds the "
                            f"maximum safe MIC cutoff **{_max_safe:.3f} Å**. "
                            f"Angles/path lengths may be ambiguous; reduce cutoff_3body to "
                            f"≤ {_max_safe:.3f} Å or use a supercell."
                        )

                with mo.status.spinner("Computing MSRD paths…"):
                    _res2b, _res3b = calculate_grouped_msrd(
                        structures,
                        _indices,
                        _spec,
                        cutoff=cutoff.value,
                        tol_dist=tol_dist.value,
                        tol_angle=tol_angle.value,
                        cutoff_3body=_c3b,
                        exclude_hydrogen=exclude_hydrogen_cb.value,
                    )

                _rows2b = [
                    {
                        "Path type": r["type"],
                        "Reff (Å)": f"{r['reff']:.4f}",
                        "σ² (Å²)": f"{r['sigma2']:.6f}",
                        "Count": r["count"],
                        "Degeneracy": f"{r['count'] / len(_indices):.1f}",
                    }
                    for r in _res2b
                ]
                _rows3b = [
                    {
                        "Path type": r["type"],
                        "Reff (Å)": f"{r['reff']:.4f}",
                        "σ² (Å²)": f"{r['sigma2']:.6f}",
                        "Angle (°)": f"{r['angle']:.1f}",
                        "Count": r["count"],
                        "Degeneracy": f"{2 * r['count'] / len(_indices):.1f}",
                    }
                    for r in _res3b
                ]

                _df_rows = [
                    {
                        "_row_id": i,
                        "Body": "2-body",
                        "Path type": r["type"],
                        "Reff (Å)": r["reff"],
                        "σ² (Å²)": r["sigma2"],
                        "Angle (°)": float("nan"),
                        "Count": r["count"],
                        "Degeneracy": r["count"] / len(_indices),
                    }
                    for i, r in enumerate(_res2b)
                ] + [
                    {
                        "_row_id": len(_res2b) + i,
                        "Body": "3-body",
                        "Path type": r["type"],
                        "Reff (Å)": r["reff"],
                        "σ² (Å²)": r["sigma2"],
                        "Angle (°)": r["angle"],
                        "Count": r["count"],
                        "Degeneracy": 2 * r["count"] / len(_indices),
                    }
                    for i, r in enumerate(_res3b)
                ]
                msrd_df = pd.DataFrame(_df_rows)
                msrd_path_indices = [r["atom_indices"] for r in _res2b] + [
                    r["atom_indices"] for r in _res3b
                ]
                _msrd_ui = mo.vstack(
                    [
                        mo.md(
                            f"**Site:** `{_spec}` · "
                            f"**{len(_indices)} absorber(s)** · "
                            f"**{len(_res2b)} two-body** and "
                            f"**{len(_res3b)} three-body** paths found"
                        ),
                        mo.callout(
                            mo.md("\n\n".join(_warnings)),
                            kind="warn",
                        )
                        if _warnings
                        else mo.md(""),
                        mo.md("### 2-Body Paths"),
                        mo.ui.table(_rows2b) if _rows2b else mo.md("_No 2-body paths found._"),
                        mo.md("### 3-Body Paths"),
                        mo.ui.table(_rows3b)
                        if _rows3b
                        else mo.md("_No 3-body paths (cutoff = 0 or no triangles)._"),
                        mo.download(
                            data=msrd_df.to_csv(index=False).encode(),
                            filename=f"{output_prefix.value}_msrd_paths_{_spec.replace(' ', '_')}.csv",
                            label="⬇ Download MSRD paths as CSV",
                        ),
                    ]
                )

    _msrd_ui
    return msrd_df, msrd_path_indices


@app.cell
def _(alt, atomic_numbers, jmol_colors, mo, msrd_df):
    msrd_chart = None

    if msrd_df is not None:

        def _jmol_hex(sym):
            z = atomic_numbers.get(sym, 0)
            r, g, b = jmol_colors[z]
            return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

        _pt_domain = list(msrd_df["Path type"].unique())
        _pt_range = [_jmol_hex(pt.split("-")[1]) for pt in _pt_domain]
        _pt_color_scale = alt.Scale(domain=_pt_domain, range=_pt_range)

        _base = alt.Chart(msrd_df)

        _points = _base.mark_point(filled=True).encode(
            x=alt.X("Reff (Å):Q", title="Reff (Å)"),
            y=alt.Y("σ² (Å²):Q", title="σ² (Å²)"),
            color=alt.Color("Path type:N", title="Path type", scale=_pt_color_scale),
            shape=alt.Shape(
                "Body:N",
                title="Body",
                scale=alt.Scale(domain=["2-body", "3-body"], range=["circle", "triangle-up"]),
            ),
            size=alt.value(60),
            opacity=alt.value(0.75),
            tooltip=[
                alt.Tooltip("Body:N", title="Body"),
                alt.Tooltip("Path type:N", title="Path type"),
                alt.Tooltip("Reff (Å):Q", format=".4f", title="Reff (Å)"),
                alt.Tooltip("σ² (Å²):Q", format=".6f", title="σ² (Å²)"),
                alt.Tooltip("Angle (°):Q", format=".1f", title="Angle (°)"),
                alt.Tooltip("Degeneracy:Q", format=".2f", title="Degeneracy"),
                alt.Tooltip("Count:Q", title="Count"),
            ],
        )

        _chart = alt.layer(_points).properties(height=340, width="container")
        msrd_chart = mo.ui.altair_chart(_chart, label="Click a point to inspect it")

    msrd_chart if msrd_chart is not None else mo.md(
        "_Run MSRD analysis above to see the path plot._"
    )
    return (msrd_chart,)


@app.cell
def _(mo, path_index_slider, path_view, selected_path_info, show_all_paths):
    mo.vstack(
        [
            mo.hstack([show_all_paths, path_index_slider], justify="start")
            if selected_path_info is not None
            else mo.md("_Select a path first._"),
            path_view,
        ]
    )
    return


@app.cell
def _(avg_atoms, find_mic, mo, msrd_chart, msrd_path_indices, np, results):
    _sel = msrd_chart.value if msrd_chart is not None else None
    selected_path_info = None

    if _sel is not None and len(_sel) > 0:
        _r = _sel.iloc[0]
        _body = _r["Body"]
        _row_id = int(_r["_row_id"])
        _path_pairs = msrd_path_indices[_row_id]

        _syms = results["atom_names"]
        _pos = results["avg_positions"]
        _cell = results["avg_cell"]
        _pbc = avg_atoms.get_pbc() if avg_atoms is not None else [True, True, True]

        _atom_rows = []
        _all_vectors = []
        _path_instances = []
        for _pair in _path_pairs:
            _c = _pair[0]
            _neighbors = list(_pair[1:])
            _row = {"Absorber idx": _c, "Absorber element": _syms[_c]}
            _instance_vecs = []

            if _body == "3-body" and len(_neighbors) == 2:
                _n1, _n2 = _neighbors
                _v1_raw = _pos[_n1] - _pos[_c]
                _v1_mic, _ = find_mic([_v1_raw], _cell, _pbc)
                _v1 = _v1_mic[0]
                _d1 = float(np.linalg.norm(_v1))
                _orig_c = _pos[_c]
                _v12_raw = _pos[_n2] - _pos[_n1]
                _v12_mic, _ = find_mic([_v12_raw], _cell, _pbc)
                _v12 = _v12_mic[0]
                _d12 = float(np.linalg.norm(_v12))
                _orig_n1 = _orig_c + _v1
                _v_ret = -(_v1 + _v12)
                _d_ret = float(np.linalg.norm(_v_ret))
                _orig_n2 = _orig_n1 + _v12

                _row["n1 idx"] = _n1
                _row["n1 element"] = _syms[_n1]
                _row["n1 dist (Å)"] = f"{_d1:.4f}"
                _row["n1 vector (Å)"] = f"({_v1[0]:.3f}, {_v1[1]:.3f}, {_v1[2]:.3f})"
                _row["n2 idx"] = _n2
                _row["n2 element"] = _syms[_n2]
                _row["n2 dist (Å)"] = f"{_d_ret:.4f}"
                _row["n1→n2 dist (Å)"] = f"{_d12:.4f}"
                _row["n1→n2 vector (Å)"] = f"({_v12[0]:.3f}, {_v12[1]:.3f}, {_v12[2]:.3f})"

                _e1 = {
                    "from_idx": _c,
                    "to_idx": _n1,
                    "leg": "n1",
                    "vector": _v1,
                    "dist": _d1,
                    "origin": _orig_c,
                }
                _e12e = {
                    "from_idx": _n1,
                    "to_idx": _n2,
                    "leg": "n1→n2",
                    "vector": _v12,
                    "dist": _d12,
                    "origin": _orig_n1,
                }
                _e2 = {
                    "from_idx": _n2,
                    "to_idx": _c,
                    "leg": "n2",
                    "vector": _v_ret,
                    "dist": _d_ret,
                    "origin": _orig_n2,
                }
                for _e in (_e1, _e12e, _e2):
                    _all_vectors.append(_e)
                    _instance_vecs.append(_e)
            else:
                for _k, _n in enumerate(_neighbors):
                    _v_raw = _pos[_n] - _pos[_c]
                    _v_mic, _ = find_mic([_v_raw], _cell, _pbc)
                    _v = _v_mic[0]
                    _d = float(np.linalg.norm(_v))
                    _label = "n1" if _k == 0 else "n2"
                    _row[f"{_label} idx"] = _n
                    _row[f"{_label} element"] = _syms[_n]
                    _row[f"{_label} dist (Å)"] = f"{_d:.4f}"
                    _row[f"{_label} vector (Å)"] = f"({_v[0]:.3f}, {_v[1]:.3f}, {_v[2]:.3f})"
                    _entry = {
                        "from_idx": _c,
                        "to_idx": _n,
                        "leg": _label,
                        "vector": _v,
                        "dist": _d,
                    }
                    _all_vectors.append(_entry)
                    _instance_vecs.append(_entry)

            _atom_rows.append(_row)
            _path_instances.append(_instance_vecs)

        selected_path_info = {
            "body": _body,
            "path_type": _r["Path type"],
            "reff": _r["Reff (Å)"],
            "sigma2": _r["σ² (Å²)"],
            "path_pairs": _path_pairs,
            "path_instances": _path_instances,
            "vectors": _all_vectors,
            "avg_atoms": avg_atoms,
        }

        _angle_str = f" · Angle: {_r['Angle (°)']:.1f}°" if _body == "3-body" else ""
        _summary = mo.vstack(
            [
                mo.md(
                    f"### Selected path: **{_r['Path type']}** ({_body}){_angle_str}\n"
                    f"**Reff** = {_r['Reff (Å)']:.4f} Å · "
                    f"**σ²** = {_r['σ² (Å²)']:.6f} Å² · "
                    f"**Degeneracy** = {_r['Degeneracy']:.2f} · "
                    f"**Count** = {int(_r['Count'])}"
                ),
                mo.md("#### Atom indices and bond vectors (average structure)"),
                mo.ui.table(_atom_rows),
            ]
        )
    else:
        _summary = mo.callout(
            mo.md("Click a point in the chart above to see its details here."),
            kind="info",
        )

    _summary
    return (selected_path_info,)


@app.cell
def _(mo, selected_path_info):
    _n = len(selected_path_info["path_instances"]) if selected_path_info is not None else 1
    show_all_paths = mo.ui.checkbox(label="Show all equivalent paths", value=False)
    path_index_slider = mo.ui.slider(
        start=0,
        stop=max(_n - 1, 0),
        step=1,
        value=0,
        label=f"Path instance (0–{max(_n - 1, 0)}):",
        show_value=True,
    )
    return path_index_slider, show_all_paths


@app.cell
def _(
    ASEAdapter,
    AtomsViewer,
    BaseWidget,
    guiConfig,
    mo,
    np,
    path_index_slider,
    selected_path_info,
    show_all_paths,
):
    path_view = mo.md("_Select a path above to visualise it._")
    if selected_path_info is not None:
        _avg_atoms = selected_path_info["avg_atoms"]
        _instances = selected_path_info["path_instances"]
        _n_total = len(_instances)
        _pos = _avg_atoms.get_positions()

        if show_all_paths.value:
            _active_instances = list(range(_n_total))
        else:
            _idx = path_index_slider.value
            _active_instances = [_idx]

        _leg_colors = {
            "n1": "#e05c2e",
            "n2": "#2e94e0",
            "n1→n2": "#2eac50",
        }

        _vf_groups: dict = {}
        _highlight = set()
        for _i in _active_instances:
            for _v in _instances[_i]:
                _leg = _v["leg"]
                _color = _leg_colors.get(_leg, "#aaaaaa")
                _key = f"leg_{_leg}_i{_i}"
                if _key not in _vf_groups:
                    _vf_groups[_key] = {
                        "origins": [],
                        "vectors": [],
                        "color": _color,
                        "radius": 0.12,
                    }
                _vf_groups[_key]["origins"].append(
                    _v["origin"].tolist() if "origin" in _v else _pos[_v["from_idx"]].tolist()
                )
                _vf_groups[_key]["vectors"].append(np.array(_v["vector"]).tolist())
                _highlight.add(_v["from_idx"])
                _highlight.add(_v["to_idx"])

        _viewer = AtomsViewer(BaseWidget(guiConfig=guiConfig))
        _viewer.atoms = ASEAdapter.to_weas(_avg_atoms)
        _viewer.model_style = 1
        _viewer.boundary = [[-0.15, 1.15], [-0.15, 1.15], [-0.15, 1.15]]
        _viewer.highlight = list(_highlight)
        _viewer.vf.settings = _vf_groups
        _viewer.vf.show = True
        path_view = _viewer._widget
    return (path_view,)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ### References
    - Rehr & Albers, *Rev. Mod. Phys.* **72**, 621 (2000) – EXAFS path definitions
    - Kabsch, *Acta Cryst. A* **32**, 922 (1976) – Optimal rotation algorithm
    - Debye-Waller factor: B = 8π²⟨u²⟩
    """)
    return


if __name__ == "__main__":
    app.run()
