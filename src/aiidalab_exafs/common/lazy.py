"""Deferred construction for widgets that query the database when they are built."""

from __future__ import annotations

from collections.abc import Callable

import ipywidgets as ipw


class LazyWidget(ipw.Box):
    """Placeholder that builds its real child the first time it is needed.

    Several database selectors run a full AiiDA query from their constructor.
    Built eagerly they dominated app startup, because each one sat in a
    collapsed accordion or an unselected tab that nobody had opened: on a
    modest profile the experimental-spectrum selector alone cost 42 s of a 59 s
    startup. Wrapping them defers that query to the point where the user asks
    to see the widget.

    The wrapper is a ``Box`` so it can stand in for the real widget inside an
    accordion or tab; call :meth:`build` from whatever reveals it.
    """

    def __init__(self, factory: Callable[[], ipw.Widget], placeholder: str = "", **kwargs):
        """Wrap ``factory``, showing ``placeholder`` until the widget is built."""
        self._factory = factory
        self._widget: ipw.Widget | None = None
        super().__init__([ipw.HTML(placeholder)] if placeholder else [], **kwargs)

    @property
    def built(self) -> bool:
        """Whether the wrapped widget has been constructed yet."""
        return self._widget is not None

    def build(self) -> ipw.Widget:
        """Construct the wrapped widget if needed and return it."""
        if self._widget is None:
            self._widget = self._factory()
            self.children = [self._widget]
        return self._widget

    def reset(self) -> None:
        """Reset the wrapped widget, but never build one just to reset it."""
        if self._widget is not None and hasattr(self._widget, "reset"):
            self._widget.reset()
