import threading
from typing import List, Tuple, Dict, Set
from memory.syntactic.function import *
from memory.syntactic.value import *
from memory.report.bug_report import *
from memory.semantic.state import *
from tstool.analyzer.TS_analyzer import *


class DFBScanState(State):
    def __init__(self, src_values: List[Value], sink_values: List[Value]) -> None:
        self._src_values = src_values
        self._sink_values = sink_values

        # Data-flows per path in single functions
        self._reachable_values_per_path: Dict[
            Tuple[Value, CallContext], List[Set[Tuple[Value, CallContext]]]
        ] = {}

        # Match parameter/return value with argument/output value
        self._external_value_match: Dict[
            Tuple[Value, CallContext], Set[Tuple[Value, CallContext]]
        ] = {}

        # Potential buggy paths: src value -> {path_str -> path}
        self._potential_buggy_paths: Dict[Value, Dict[str, List[Value]]] = {}

        # Bug reports
        self._bug_reports: Dict[int, BugReport] = {}
        self._total_bug_count = 0

        # Create locks for each field
        self._reachable_values_lock = threading.Lock()
        self._external_value_match_lock = threading.Lock()
        self._potential_buggy_paths_lock = threading.Lock()
        self._bug_reports_lock = threading.Lock()

    def update_reachable_values_per_path(
        self, start: Tuple[Value, CallContext], ends: Set[Tuple[Value, CallContext]]
    ) -> None:
        """
        Update the reachable values per path
        """
        with self._reachable_values_lock:
            if start not in self._reachable_values_per_path:
                self._reachable_values_per_path[start] = []
            self._reachable_values_per_path[start].append(ends)

    def update_external_value_match(
        self,
        external_start: Tuple[Value, CallContext],
        external_ends: Set[Tuple[Value, CallContext]],
    ) -> None:
        """
        Update the external value match
        """
        with self._external_value_match_lock:
            if external_start not in self._external_value_match:
                self._external_value_match[external_start] = set()
            self._external_value_match[external_start].update(external_ends)

    def update_potential_buggy_paths(self, src_value: Value, path: List[Value]) -> None:
        """
        Update the buggy paths
        """
        with self._potential_buggy_paths_lock:
            if src_value not in self._potential_buggy_paths:
                self._potential_buggy_paths[src_value] = {}
            self._potential_buggy_paths[src_value][str(path)] = path

    def update_bug_report(self, bug_report: BugReport) -> None:
        """
        Update the bug scan state with the bug report, deduplicating based on equality
        :param bug_report: the bug report
        """
        with self._bug_reports_lock:
            if bug_report in self._bug_reports.values():
                return
            self._bug_reports[self._total_bug_count] = bug_report
            self._total_bug_count += 1

    @property
    def reachable_values_per_path(
        self,
    ) -> Dict[Tuple[Value, CallContext], List[Set[Tuple[Value, CallContext]]]]:
        """
        Get the reachable values per path
        """
        with self._reachable_values_lock:
            return self._reachable_values_per_path.copy()

    @property
    def external_value_match(
        self,
    ) -> Dict[Tuple[Value, CallContext], Set[Tuple[Value, CallContext]]]:
        """
        Get the external value match
        """
        with self._external_value_match_lock:
            return self._external_value_match.copy()

    @property
    def potential_buggy_paths(self) -> Dict[Value, Dict[str, List[Value]]]:
        """
        Get the potential buggy paths
        """
        with self._potential_buggy_paths_lock:
            return self._potential_buggy_paths.copy()

    @property
    def bug_reports(self) -> Dict[int, BugReport]:
        """
        Get the bug reports
        """
        with self._bug_reports_lock:
            return self._bug_reports.copy()

    @property
    def total_bug_count(self) -> int:
        """
        Get the total bug count
        """
        with self._bug_reports_lock:
            return self._total_bug_count

    def merge_from(self, other: "DFBScanState") -> None:
        for start, path_sets in other.reachable_values_per_path.items():
            for ends in path_sets:
                self.update_reachable_values_per_path(start, ends)

        for start, ends in other.external_value_match.items():
            self.update_external_value_match(start, ends)

        for src_value, paths in other.potential_buggy_paths.items():
            for path in paths.values():
                self.update_potential_buggy_paths(src_value, path)

        for bug_report in other.bug_reports.values():
            self.update_bug_report(bug_report)

    def check_existence(self, src: Value, relevant_functions: set[Function]) -> bool:
        """
        Check if the bug report with the same src and relevant functions already exists
        """
        with self._bug_reports_lock:
            relevant_functions_ids = [
                function.function_id for function in relevant_functions
            ]
            hash_value = hash((src, tuple(sorted(list(relevant_functions_ids)))))
            is_exist = False
            for report in self._bug_reports.values():
                if hash(report) == hash_value:
                    is_exist = True
                    break
            return is_exist

    def print_reachable_values_per_path(self) -> None:
        """
        Print the reachable values per path
        """
        print("=====================================")
        print("Reachable Values Per Path:")
        print("=====================================")
        with self._reachable_values_lock:
            for (
                start_value,
                start_context,
            ), ends in self._reachable_values_per_path.items():
                print("-------------------------------------")
                print(f"Start: {str(start_value)}, {str(start_context)}")
                for i in range(len(ends)):
                    print("--------------------------")
                    print(f"  Path {i + 1}:")
                    for value, ctx in ends[i]:
                        print(f"  End: {value}, {str(ctx)}")
                    print("--------------------------")
                print("-------------------------------------")
        print("=====================================\n")

    def print_external_value_match(self) -> None:
        """
        Print the external value match.
        """
        print("=====================================")
        print("External Value Match:")
        print("=====================================")
        with self._external_value_match_lock:
            for start, ends in self._external_value_match.items():
                print("-------------------------------------")
                print(f"Start: {start[0]}, {str(start[1])}")
                for end in ends:
                    # end is a tuple of (Value, CallContext)
                    print(f"  End: {end[0]}, {str(end[1])}")
                print("-------------------------------------")
        print("=====================================\n")

    def print_potential_buggy_paths(self) -> None:
        """
        Print the potential buggy paths
        """
        print("=====================================")
        print("Potential Buggy Paths:")
        print("=====================================")
        with self._potential_buggy_paths_lock:
            for src_value, paths in self._potential_buggy_paths.items():
                print("-------------------------------------")
                print(f"Source Value: {src_value}")
                for path_str, path in paths.items():
                    print(f"Path: {path_str}")
                    print(f"  Path: {path}")
                print("-------------------------------------")
        print("=====================================\n")
