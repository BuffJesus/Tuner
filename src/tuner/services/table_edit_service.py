from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class TableSelection:
    top: int
    left: int
    bottom: int
    right: int

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


class TableEditService:
    def copy_region(self, values: list[float], columns: int, selection: TableSelection) -> str:
        rows = self._to_grid(values, columns)
        lines = []
        for row in range(selection.top, selection.bottom + 1):
            lines.append("\t".join(str(rows[row][column]) for column in range(selection.left, selection.right + 1)))
        return "\n".join(lines)

    def paste_region(
        self,
        values: list[float],
        columns: int,
        selection: TableSelection,
        clipboard_text: str,
    ) -> list[float]:
        rows = self._to_grid(values, columns)
        clipboard_rows = self._parse_clipboard(clipboard_text)
        if not clipboard_rows:
            return values
        clip_height = len(clipboard_rows)
        clip_width = max((len(row) for row in clipboard_rows), default=0)
        if clip_width == 0:
            return values
        fill_height = max(selection.height, clip_height)
        fill_width = max(selection.width, clip_width)
        for row_offset in range(fill_height):
            target_row = selection.top + row_offset
            if target_row >= len(rows):
                break
            clipboard_row = clipboard_rows[row_offset % clip_height]
            if not clipboard_row:
                continue
            for column_offset in range(fill_width):
                target_column = selection.left + column_offset
                if target_column >= columns:
                    break
                rows[target_row][target_column] = clipboard_row[column_offset % len(clipboard_row)]
        return self._flatten(rows)

    def fill_region(
        self,
        values: list[float],
        columns: int,
        selection: TableSelection,
        fill_value: float,
    ) -> list[float]:
        rows = self._to_grid(values, columns)
        for row in range(selection.top, selection.bottom + 1):
            for column in range(selection.left, selection.right + 1):
                rows[row][column] = fill_value
        return self._flatten(rows)

    def fill_down_region(
        self,
        values: list[float],
        columns: int,
        selection: TableSelection,
    ) -> list[float]:
        rows = self._to_grid(values, columns)
        if selection.height <= 1:
            return values
        source_row = [
            rows[selection.top][column]
            for column in range(selection.left, selection.right + 1)
        ]
        for row in range(selection.top + 1, selection.bottom + 1):
            for column_offset, column in enumerate(range(selection.left, selection.right + 1)):
                rows[row][column] = source_row[column_offset]
        return self._flatten(rows)

    def fill_right_region(
        self,
        values: list[float],
        columns: int,
        selection: TableSelection,
    ) -> list[float]:
        rows = self._to_grid(values, columns)
        if selection.width <= 1:
            return values
        for row in range(selection.top, selection.bottom + 1):
            source_value = rows[row][selection.left]
            for column in range(selection.left + 1, selection.right + 1):
                rows[row][column] = source_value
        return self._flatten(rows)

    def interpolate_region(
        self,
        values: list[float],
        columns: int,
        selection: TableSelection,
    ) -> list[float]:
        rows = self._to_grid(values, columns)
        if selection.width == 1 and selection.height > 1:
            column = selection.left
            start = rows[selection.top][column]
            end = rows[selection.bottom][column]
            span = max(1, selection.bottom - selection.top)
            for row in range(selection.top, selection.bottom + 1):
                fraction = (row - selection.top) / span
                rows[row][column] = start + ((end - start) * fraction)
            return self._flatten(rows)
        for row in range(selection.top, selection.bottom + 1):
            start = rows[row][selection.left]
            end = rows[row][selection.right]
            span = max(1, selection.right - selection.left)
            for column in range(selection.left, selection.right + 1):
                fraction = (column - selection.left) / span
                rows[row][column] = start + ((end - start) * fraction)
        return self._flatten(rows)

    def smooth_region(
        self,
        values: list[float],
        columns: int,
        selection: TableSelection,
    ) -> list[float]:
        rows = self._to_grid(values, columns)
        original = [list(row) for row in rows]
        for row in range(selection.top, selection.bottom + 1):
            for column in range(selection.left, selection.right + 1):
                neighbors: list[float] = []
                for row_offset in (-1, 0, 1):
                    for column_offset in (-1, 0, 1):
                        target_row = row + row_offset
                        target_column = column + column_offset
                        if 0 <= target_row < len(original) and 0 <= target_column < columns:
                            neighbors.append(original[target_row][target_column])
                rows[row][column] = round(sum(neighbors) / len(neighbors), 3)
        return self._flatten(rows)

    @staticmethod
    def _to_grid(values: list[float], columns: int) -> list[list[float]]:
        return [values[index : index + columns] for index in range(0, len(values), columns)]

    @staticmethod
    def _flatten(rows: list[list[float]]) -> list[float]:
        flattened: list[float] = []
        for row in rows:
            flattened.extend(row)
        return flattened

    @staticmethod
    def _parse_clipboard(text: str) -> list[list[float]]:
        rows: list[list[float]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            rows.append([float(value.strip()) for value in line.replace(",", "\t").split("\t") if value.strip()])
        return rows
