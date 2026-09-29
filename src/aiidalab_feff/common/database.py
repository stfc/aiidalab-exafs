"""A projected-query replacement for the shared AiiDA database selector."""

from __future__ import annotations

import datetime

from aiida.orm import CalcJobNode, Node, QueryBuilder, WorkChainNode
from alc_aiidalab_widgets.widgets.database import AiiDADatabaseQueryWidget


class ProjectedQueryWidget(AiiDADatabaseQueryWidget):
    """Database selector that builds its option labels from one query.

    ``AiiDADatabaseQueryWidget.search`` fetches whole nodes and then reads
    ``ctime``, ``extras``, ``node_type``, ``label`` and ``description`` off each
    one to build its dropdown label. Every one of those is an expired-attribute
    load, so the search costs a query per field per node: 75k queries and 42 s
    for the experimental-spectrum selector on a modest profile. Projecting the
    same fields in the original query gives identical labels for one query.

    Subclasses can narrow the search in SQL with :attr:`extra_filters` rather
    than filtering ``results.options`` afterwards, which otherwise pays the full
    scan to keep a handful of rows.
    """

    #: Extra filters ANDed into the node query by subclasses.
    extra_filters: dict = {}

    _PROJECTIONS = ("*", "ctime", "extras.formula", "node_type", "label", "description")

    def _date_range(self) -> tuple[datetime.datetime, datetime.datetime]:
        """Return the selected range, falling back to the last 7 days."""
        try:
            start = datetime.datetime.strptime(self.start_date_widget.value, "%Y-%m-%d")
            end = datetime.datetime.strptime(
                self.end_date_widget.value, "%Y-%m-%d"
            ) + datetime.timedelta(hours=24)
        except ValueError:
            start = datetime.datetime.now() - datetime.timedelta(days=7)
            end = datetime.datetime.now() + datetime.timedelta(hours=24)
            self.start_date_widget.value = start.strftime("%Y-%m-%d")
            self.end_date_widget.value = end.strftime("%Y-%m-%d")
        return start, end

    def _build_query(self) -> QueryBuilder:
        """Mirror the base widget's mode handling, but project the label fields."""
        start, end = self._date_range()
        filters: dict = {"ctime": {"and": [{">": start}, {"<=": end}]}}
        if self.extra_filters:
            filters.update(self.extra_filters)

        query = QueryBuilder()
        if self.mode.value == "uploaded":
            processed = QueryBuilder()
            processed.append(self.query_type, project=["id"], tag="structures")
            processed.append(Node, with_outgoing="structures")
            processed_ids = [row[0] for row in processed.all()]
            if processed_ids:
                filters["id"] = {"!in": processed_ids}
            query.append(self.query_type, filters=filters, project=list(self._PROJECTIONS))
        elif self.mode.value == "calculated":
            if self.drop_down.value == "All":
                query.append((CalcJobNode, WorkChainNode), tag="parent")
            else:
                query.append(
                    (CalcJobNode, WorkChainNode),
                    filters={"label": self.drop_down.value},
                    tag="parent",
                )
            query.append(
                self.query_type,
                with_incoming="parent",
                filters=filters,
                project=list(self._PROJECTIONS),
            )
        else:
            query.append(self.query_type, filters=filters, project=list(self._PROJECTIONS))

        query.order_by({self.query_type: {"ctime": "desc"}})
        return query

    def search(self, _=None) -> None:
        """Populate the results dropdown from a single projected query."""
        rows = self._build_query().all()

        options = [(f"Select a Node ({len(rows)} found)", False)]
        for node, ctime, formula, node_type, label, description in rows:
            stamp = ctime.strftime("%Y-%m-%d %H:%M") if ctime else ""
            kind = node_type.split(".")[-2] if node_type else ""
            options.append(
                (
                    " | ".join(
                        [
                            f"PK: {node.pk}",
                            stamp,
                            formula or "",
                            kind,
                            label or "",
                            description or "",
                        ]
                    ),
                    node,
                )
            )
        self.results.options = options
