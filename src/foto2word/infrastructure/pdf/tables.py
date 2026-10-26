"""Tables found in the lines drawn on a page: lines that cross or touch make one table; where
its vertical lines stand are the column edges, where its horizontal ones stand the row edges; two
neighbouring slots with no line between them are one merged cell.
"""

from dataclasses import dataclass, field

from foto2word.domain.document import BorderLine, CellBorders

_TOUCH = 2.0
"""Points of play when two lines count as meeting."""
_SAME = 1.0
"""Edges closer than this many points are one edge."""


@dataclass(slots=True)
class Rule:
    """A straight line drawn on the page: horizontal (y0 == y1) or vertical (x0 == x1), in
    points from the page's top left corner."""

    x0: float
    y0: float
    x1: float
    y1: float
    width: float
    color: str | None

    @property
    def horizontal(self) -> bool:
        return self.y0 == self.y1


@dataclass(slots=True)
class GridCell:
    row: int
    col: int
    row_span: int
    col_span: int
    x0: float
    y0: float
    x1: float
    y1: float
    borders: CellBorders


@dataclass(slots=True)
class Grid:
    xs: list[float]
    ys: list[float]
    cells: list[GridCell]
    rules: list[Rule] = field(default_factory=list)

    @property
    def x0(self) -> float:
        return self.xs[0]

    @property
    def x1(self) -> float:
        return self.xs[-1]

    @property
    def y0(self) -> float:
        return self.ys[0]

    @property
    def y1(self) -> float:
        return self.ys[-1]

    def cell_at(self, x: float, y: float) -> GridCell | None:
        return next((c for c in self.cells if c.x0 <= x < c.x1 and c.y0 <= y < c.y1), None)


def find_grids(rules: list[Rule]) -> list[Grid]:
    """The tables the lines make: groups of crossing lines with at least two of each kind."""
    groups = _connected(rules)
    grids = []
    for group in groups:
        across = [r for r in group if r.horizontal]
        down = [r for r in group if not r.horizontal]
        if len(across) < 2 or len(down) < 2:  # noqa: PLR2004 - a box needs two of each
            continue
        grid = _grid(group, across, down)
        if grid is not None:
            grids.append(grid)
    return grids


def _meet(a: Rule, b: Rule) -> bool:
    if a.horizontal == b.horizontal:
        return False
    across, down = (a, b) if a.horizontal else (b, a)
    return (
        across.x0 - _TOUCH <= down.x0 <= across.x1 + _TOUCH
        and down.y0 - _TOUCH <= across.y0 <= down.y1 + _TOUCH
    )


def _connected(rules: list[Rule]) -> list[list[Rule]]:
    parent = list(range(len(rules)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(rules):
        for j in range(i + 1, len(rules)):
            if _meet(a, rules[j]):
                parent[root(i)] = root(j)
    groups: dict[int, list[Rule]] = {}
    for i, rule in enumerate(rules):
        groups.setdefault(root(i), []).append(rule)
    return list(groups.values())


def _edges(values: list[float]) -> list[float]:
    edges: list[float] = []
    for value in sorted(values):
        if edges and value - edges[-1] <= _SAME:
            continue
        edges.append(value)
    return edges


def _grid(group: list[Rule], across: list[Rule], down: list[Rule]) -> Grid | None:
    xs = _edges([r.x0 for r in down])
    ys = _edges([r.y0 for r in across])
    if len(xs) < 2 or len(ys) < 2:  # noqa: PLR2004
        return None

    def vertical_at(x: float, y: float) -> Rule | None:
        return next(
            (r for r in down if abs(r.x0 - x) <= _SAME and r.y0 - _SAME <= y <= r.y1 + _SAME),
            None,
        )

    def horizontal_at(y: float, x: float) -> Rule | None:
        return next(
            (r for r in across if abs(r.y0 - y) <= _SAME and r.x0 - _SAME <= x <= r.x1 + _SAME),
            None,
        )

    taken: set[tuple[int, int]] = set()
    cells = []
    for row in range(len(ys) - 1):
        for col in range(len(xs) - 1):
            if (row, col) in taken:
                continue
            middle_y = (ys[row] + ys[row + 1]) / 2
            right = col + 1  # a merged cell grows over free slots only: it stays a rectangle
            while (
                right < len(xs) - 1
                and (row, right) not in taken
                and vertical_at(xs[right], middle_y) is None
            ):
                right += 1
            bottom = row + 1
            while bottom < len(ys) - 1 and all(
                (bottom, c) not in taken
                and horizontal_at(ys[bottom], (xs[c] + xs[c + 1]) / 2) is None
                for c in range(col, right)
            ):
                bottom += 1
            for r in range(row, bottom):
                for c in range(col, right):
                    taken.add((r, c))
            mid_x = (xs[col] + xs[right]) / 2
            mid_y = (ys[row] + ys[bottom]) / 2
            sides = {
                "top": horizontal_at(ys[row], mid_x),
                "bottom": horizontal_at(ys[bottom], mid_x),
                "left": vertical_at(xs[col], mid_y),
                "right": vertical_at(xs[right], mid_y),
            }
            cells.append(
                GridCell(
                    row=row,
                    col=col,
                    row_span=bottom - row,
                    col_span=right - col,
                    x0=xs[col],
                    y0=ys[row],
                    x1=xs[right],
                    y1=ys[bottom],
                    borders=CellBorders(
                        top=sides["top"] is not None,
                        bottom=sides["bottom"] is not None,
                        left=sides["left"] is not None,
                        right=sides["right"] is not None,
                        lines=tuple(
                            (name, _look(rule))
                            for name, rule in sides.items()
                            if rule is not None and _look(rule) != BorderLine()
                        ),
                    ),
                )
            )
    return Grid(xs=xs, ys=ys, cells=cells, rules=group)


def _look(rule: Rule) -> BorderLine:
    return BorderLine(size=max(2, min(96, round(rule.width * 8))), color=rule.color)
