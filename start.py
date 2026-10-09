"""Defines the main AiiDAlab app's start banner."""

from __future__ import annotations

import ipywidgets as ipw

# NOTE: do not import aiidalab_exafs here. AiiDAlab's home page imports this
# module for every installed app, so a heavy (or failing) app import would slow
# down or break the whole home page rather than just this tile.


def get_start_widget(appbase: str, jupbase: str, notebase: str) -> ipw.Widget:
    """Return the AiiDAlab app's start banner widget."""
    logo = ipw.HTML(
        f"""
        <div style="margin: 16px auto; width: 600px; text-align: center;">
            <a href="{appbase}/main.ipynb" target="_blank" style="text-decoration: none;">
                <img src="{appbase}/logo.svg" alt="AiiDAlab EXAFS Logo"
                     style="height: 100px; width: 100px; border-radius: 15px; margin-bottom: 8px;" />
                <h2 style="margin: 0; color: #1F2933; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                    AiiDAlab EXAFS
                </h2>
                <p style="margin: 4px 0 16px 0; color: #52606D; font-size: 14px;">
                    FEFF-based EXAFS and MD-EXAFS calculations with AiiDA provenance
                </p>
            </a>
        </div>
        """
    )

    open_btn = ipw.HTML(
        f"""
        <div style="text-align: center; margin: 12px 0;">
            <a href="{appbase}/main.ipynb" target="_blank"
               style="display: inline-flex; align-items: center; justify-content: center;
                      height: 38px; padding: 0 24px; text-decoration: none;
                      background-color: #1B5E9B; color: white; font-weight: 600;
                      font-size: 14px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.12);">
                Launch EXAFS App ↗
            </a>
        </div>
        """
    )

    return ipw.VBox(
        [logo, open_btn],
        layout=ipw.Layout(align_items="center", margin="10px auto"),
    )


__all__ = ["get_start_widget"]
