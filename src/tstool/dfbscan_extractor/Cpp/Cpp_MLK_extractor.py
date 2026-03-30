from tstool.analyzer.TS_analyzer import *
from tstool.analyzer.Cpp_TS_analyzer import *
from ..dfbscan_extractor import *


class Cpp_MLK_Extractor(DFBScanExtractor):
    def extract_sources(self, function: Function) -> List[Value]:
        """
        Extract the sources that can cause the memory leak bugs from C/C++ programs.
        :param: function: Function object.
        :return: List of source values
        """
        root_node = function.parse_tree_root_node
        source_code = self.ts_analyzer.code_in_files[function.file_path]
        source_bytes = to_source_bytes(source_code)
        file_path = function.file_path

        """
        Extract the sources for Memory Leak Detection from the source code.
        1. malloc, realloc, calloc
        2. strdup, strndup
        3. asprintf, vasprintf
        4. new
        5. getline
        """
        nodes = find_nodes_by_type(root_node, "call_expression")
        nodes.extend(find_nodes_by_type(root_node, "new_expression"))
        mem_allocations = {
            "malloc",
            "calloc",
            "realloc",
            "strdup",
            "strndup",
            "asprintf",
            "vasprintf",
            "getline",
        }
        # spec_apis = {}  # specific user-defined APIs that allocate memory
        sources = []
        for node in nodes:
            is_seed_node = False
            if node.type == "new_expression":
                is_seed_node = True
            if node.type == "call_expression":
                for child in node.children:
                    if child.type == "identifier":
                        name = get_node_text(source_bytes, child)
                        if name in mem_allocations:  # or name in spec_apis:
                            is_seed_node = True

            if is_seed_node:
                line_number = get_node_start_line(node)
                name = get_node_text(source_bytes, node)
                sources.append(Value(name, line_number, ValueLabel.SRC, file_path))
        return sources

    def extract_sinks(self, function: Function) -> List[Value]:
        """
        Extract the sinks that can cause the memory leak bugs from C/C++ programs.
        :param: function: Function object.
        :return: List of sink values
        """
        root_node = function.parse_tree_root_node
        source_code = self.ts_analyzer.code_in_files[function.file_path]
        source_bytes = to_source_bytes(source_code)
        file_path = function.file_path

        """
        Extract the sinks for Memory Leak Detection from the source code.
        1. free
        """
        nodes = find_nodes_by_type(root_node, "call_expression")
        mem_deallocations = {"free"}
        # spec_apis = {}  # specific user-defined APIs that deallocate memory
        sinks = []
        for node in nodes:
            is_sink_node = False
            self.ts_analyzer.get_arguments_at_callsite
            find_nodes_by_type(node, "argument")
            for child in node.children:
                if child.type == "identifier":
                    name = get_node_text(source_bytes, child)
                    if name in mem_deallocations:  # or name in spec_apis:
                        is_sink_node = True

            if is_sink_node:
                line_number = get_node_start_line(node)
                name = get_node_text(source_bytes, node)
                sinks.append(Value(name, line_number, ValueLabel.SINK, file_path))
        return sinks
