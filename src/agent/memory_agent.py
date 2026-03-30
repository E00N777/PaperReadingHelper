import threading
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from memory.syntactic.function import Function
from memory.syntactic.value import Value


class MemoryAgent:
    def __init__(
        self,
        compact_function_threshold: int = 80,
        context_window: int = 3,
        max_notes_per_key: int = 3,
    ) -> None:
        self.compact_function_threshold = compact_function_threshold
        self.context_window = context_window
        self.max_notes_per_key = max_notes_per_key

        self._lock = threading.RLock()
        self._function_summaries: Dict[int, str] = {}
        self._function_observations: Dict[int, List[str]] = defaultdict(list)
        self._path_observations: Dict[Tuple[str, Tuple[int, ...]], List[str]] = (
            defaultdict(list)
        )

    def _remember(self, memory: Dict, key: object, note: str) -> None:
        note = note.strip()
        if not note:
            return
        with self._lock:
            notes = memory[key]
            if note in notes:
                return
            notes.append(note)
            if len(notes) > self.max_notes_per_key:
                del notes[:-self.max_notes_per_key]

    def _format_named_lines(self, values: Sequence[Tuple[str, int]]) -> str:
        if not values:
            return "none"
        return ", ".join(f"{name}@{line}" for name, line in values)

    def _build_function_summary(self, function: Function) -> str:
        with self._lock:
            if function.function_id in self._function_summaries:
                return self._function_summaries[function.function_id]

        paras = (
            ", ".join(
                f"{para.name}@{function.file_line2function_line(para.line_number)}"
                for para in sorted(function.paras or [], key=lambda value: value.index)
            )
            or "none"
        )
        retvals = (
            ", ".join(
                f"{retval.name}@{function.file_line2function_line(retval.line_number)}"
                for retval in sorted(
                    function.retvals or [], key=lambda value: (value.line_number, value.index)
                )
            )
            or "none"
        )
        line_count = max(1, len(function.function_code.splitlines()))
        summary = "\n".join(
            [
                f"Function: {function.function_name}",
                f"File: {function.file_path}",
                f"Line span: {function.start_line_number}-{function.end_line_number} ({line_count} lines)",
                f"Parameters: {paras}",
                f"Return values: {retvals}",
            ]
        )
        with self._lock:
            self._function_summaries[function.function_id] = summary
        return summary

    def _merge_windows(self, focus_lines: Iterable[int], total_lines: int) -> List[Tuple[int, int]]:
        intervals: List[Tuple[int, int]] = []
        valid_lines = sorted({line for line in focus_lines if 1 <= line <= total_lines})
        if not valid_lines:
            valid_lines = [1, total_lines]

        for line in valid_lines:
            start = max(1, line - self.context_window)
            end = min(total_lines, line + self.context_window)
            if intervals and start <= intervals[-1][1] + 1:
                intervals[-1] = (intervals[-1][0], max(intervals[-1][1], end))
            else:
                intervals.append((start, end))
        return intervals

    def _build_compact_context(
        self, function: Function, focus_lines: Iterable[int]
    ) -> str:
        code_lines = function.function_code.splitlines()
        total_lines = max(1, len(code_lines))
        if total_lines <= self.compact_function_threshold:
            return function.lined_code

        intervals = self._merge_windows(focus_lines, total_lines)
        compact_lines = [
            f"[MemoryAgent compact context: original function has {total_lines} lines; unrelated regions are omitted.]"
        ]
        last_end = 0
        for start, end in intervals:
            if start > last_end + 1:
                compact_lines.append(f"... lines {last_end + 1}-{start - 1} omitted ...")
            for line_number in range(start, end + 1):
                line_content = code_lines[line_number - 1] if line_number - 1 < len(code_lines) else ""
                compact_lines.append(f"{line_number}. {line_content}")
            last_end = end
        if last_end < total_lines:
            compact_lines.append(f"... lines {last_end + 1}-{total_lines} omitted ...")
        return "\n".join(compact_lines)

    def build_intra_function_context(
        self,
        function: Function,
        summary_start: Value,
        sink_values: Sequence[Tuple[str, int]],
        call_statements: Sequence[Tuple[str, int]],
        ret_values: Sequence[Tuple[str, int]],
    ) -> str:
        focus_lines = [function.file_line2function_line(summary_start.line_number)]
        focus_lines.extend(line for _, line in sink_values)
        focus_lines.extend(line for _, line in call_statements)
        focus_lines.extend(line for _, line in ret_values)
        return self._build_compact_context(function, focus_lines)

    def build_path_function_context(
        self, function: Function, values: Sequence[Value]
    ) -> str:
        focus_lines = [
            function.file_line2function_line(value.line_number)
            for value in values
            if function.start_line_number <= value.line_number <= function.end_line_number
        ]
        return self._build_compact_context(function, focus_lines)

    def get_intra_memory(
        self,
        function: Function,
        summary_start: Value,
        sink_values: Sequence[Tuple[str, int]],
        call_statements: Sequence[Tuple[str, int]],
        ret_values: Sequence[Tuple[str, int]],
    ) -> str:
        lines = [
            self._build_function_summary(function),
            f"Source focus: {summary_start.name}@{function.file_line2function_line(summary_start.line_number)}",
            f"Known sinks: {self._format_named_lines(sink_values)}",
            f"Call sites: {self._format_named_lines(call_statements)}",
            f"Return values: {self._format_named_lines(ret_values)}",
        ]
        with self._lock:
            notes = list(self._function_observations.get(function.function_id, []))
        if notes:
            lines.append("Past observations:")
            lines.extend(f"- {note}" for note in notes)
        return "\n".join(lines)

    def _path_key(
        self, bug_type: str, values_to_functions: Dict[Value, Optional[Function]]
    ) -> Tuple[str, Tuple[int, ...]]:
        function_ids = sorted(
            {
                function.function_id
                for function in values_to_functions.values()
                if function is not None
            }
        )
        return bug_type, tuple(function_ids)

    def get_path_memory(
        self, bug_type: str, values_to_functions: Dict[Value, Optional[Function]]
    ) -> str:
        seen = set()
        unique_functions: List[Function] = []
        for function in values_to_functions.values():
            if function is None or function.function_id in seen:
                continue
            seen.add(function.function_id)
            unique_functions.append(function)

        lines = [self._build_function_summary(function) for function in unique_functions]
        with self._lock:
            notes = list(self._path_observations.get(self._path_key(bug_type, values_to_functions), []))
        if notes:
            lines.append("Past validation notes:")
            lines.extend(f"- {note}" for note in notes)
        return "\n\n".join(lines)

    def record_intra_result(
        self,
        function: Function,
        summary_start: Value,
        reachable_values: Sequence[Sequence[Value]],
    ) -> None:
        src_line = function.file_line2function_line(summary_start.line_number)
        path_notes: List[str] = []
        for path_index, path_values in enumerate(reachable_values[:2], start=1):
            sorted_values = sorted(
                path_values,
                key=lambda value: (value.line_number, value.index, value.label.value, value.name),
            )
            if not sorted_values:
                path_notes.append(f"path {path_index}: empty")
                continue
            value_notes = []
            for value in sorted_values[:4]:
                relative_line = function.file_line2function_line(value.line_number)
                value_notes.append(f"{value.label.name}:{value.name}@{relative_line}")
            path_notes.append(f"path {path_index}: {', '.join(value_notes)}")
        note = f"{summary_start.name}@{src_line} -> {' | '.join(path_notes) if path_notes else 'no reachable values'}"
        self._remember(self._function_observations, function.function_id, note)

    def record_path_validation(
        self,
        bug_type: str,
        values_to_functions: Dict[Value, Optional[Function]],
        is_reachable: bool,
        explanation: str,
    ) -> None:
        first_line = explanation.strip().splitlines()[0] if explanation.strip() else "no explanation"
        verdict = "reachable" if is_reachable else "not reachable"
        note = f"{verdict}: {first_line}"
        self._remember(
            self._path_observations,
            self._path_key(bug_type, values_to_functions),
            note,
        )
