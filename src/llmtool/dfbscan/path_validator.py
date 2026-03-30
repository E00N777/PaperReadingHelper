from os import path
import json
from typing import List, Dict
from llmtool.LLM_utils import *
from llmtool.LLM_tool import *
from memory.syntactic.function import *
from memory.syntactic.value import *
from memory.syntactic.api import *
from agent.memory_agent import MemoryAgent
from llmtool.dfbscan.uaf_semantic_summaries import build_uaf_semantic_summary

BASE_PATH = Path(__file__).resolve().parent.parent.parent


class PathValidatorInput(LLMToolInput):
    def __init__(
        self,
        bug_type: str,
        values: List[Value],
        values_to_functions: Dict[Value, Optional[Function]],
    ) -> None:
        self.bug_type = bug_type
        self.values = values
        self.values_to_functions = values_to_functions
        return

    def __hash__(self) -> int:
        return hash(str([str(value) for value in self.values]))


class PathValidatorOutput(LLMToolOutput):
    def __init__(self, is_reachable: bool, explanation_str: str) -> None:
        self.is_reachable = is_reachable
        self.explanation_str = explanation_str
        return

    def __str__(self):
        return (
            f"Is reachable: {self.is_reachable} \nExplanation: {self.explanation_str}"
        )


class PathValidator(LLMTool):
    def __init__(
        self,
        model_name: str,
        temperature: float,
        language: str,
        max_query_num: int,
        logger: Logger,
        memory_agent: Optional[MemoryAgent] = None,
    ) -> None:
        """
        :param model_name: the model name
        :param temperature: the temperature
        :param language: the programming language
        :param max_query_num: the maximum number of queries if the model fails
        :param logger: the logger
        """
        super().__init__(model_name, temperature, language, max_query_num, logger)
        self.prompt_file = f"{BASE_PATH}/prompt/{language}/dfbscan/path_validator.json"
        self.memory_agent = memory_agent
        return

    def _bug_type_specific_guidance(self, bug_type: str) -> str:
        if bug_type != "UAF":
            return ""
        return "\n".join(
            [
                "UAF-specific rules:",
                "- The source denotes the released object expression, not the whole free/delete statement.",
                "- Answer Yes only if the sink is a later use of the same released object or one of its aliases.",
                "- If the sink dereferences an unrelated pointer/object/field, answer No even if the overall path is otherwise reachable.",
                "- If the object is replaced, deep-copied, detached, or the code exits/returns on the cleanup branch before the reported sink, answer No.",
                "- Normal container cleanup, holder cleanup, and error-path free-then-return patterns are not UAF.",
            ]
        )

    def _get_prompt(self, input: LLMToolInput) -> str:
        if not isinstance(input, PathValidatorInput):
            raise TypeError("expect PathValidatorInput")
        with open(self.prompt_file, "r") as f:
            prompt_template_dict = json.load(f)
        prompt = prompt_template_dict["task"]
        prompt += "\n" + "\n".join(prompt_template_dict["analysis_rules"])
        specific_guidance = self._bug_type_specific_guidance(input.bug_type)
        if specific_guidance:
            prompt += "\n" + specific_guidance
        prompt += "\n" + "\n".join(prompt_template_dict["analysis_examples"])
        prompt += "\n" + "".join(prompt_template_dict["meta_prompts"])
        prompt = prompt.replace(
            "<ANSWER>", "\n".join(prompt_template_dict["answer_format"])
        ).replace("<QUESTION>", "\n".join(prompt_template_dict["question_template"]))

        value_lines = []
        for value in input.values:
            value_line = " - " + str(value)
            function = input.values_to_functions.get(value)
            if function is None:
                continue
            value_line += (
                " in the function "
                + function.function_name
                + " at the line "
                + str(value.line_number - function.start_line_number + 1)
            )
            value_lines.append(value_line)
        prompt = prompt.replace("<PATH>", "\n".join(value_lines))
        prompt = prompt.replace("<BUG_TYPE>", input.bug_type)

        function_values: Dict[int, List[Value]] = {}
        unique_functions: List[Function] = []
        seen_function_ids = set()
        for value, function in input.values_to_functions.items():
            if function is None:
                continue
            function_values.setdefault(function.function_id, []).append(value)
            if function.function_id in seen_function_ids:
                continue
            seen_function_ids.add(function.function_id)
            unique_functions.append(function)

        program_blocks = []
        for function in unique_functions:
            function_context = function.lined_code
            if self.memory_agent is not None:
                function_context = self.memory_agent.build_path_function_context(
                    function, function_values.get(function.function_id, [])
                )
            program_blocks.append("```\n" + function_context + "\n```\n")
        program = "\n".join(program_blocks)
        prompt = prompt.replace("<PROGRAM>", program)

        if input.bug_type == "UAF":
            summary_str = build_uaf_semantic_summary(unique_functions)
            if summary_str:
                prompt += "\n" + summary_str

        if self.memory_agent is not None:
            memory_str = self.memory_agent.get_path_memory(
                input.bug_type, input.values_to_functions
            )
            prompt += "\nRelevant memory:\n" + memory_str
        return prompt

    def _parse_response(
        self, response: str, input: Optional[LLMToolInput] = None
    ) -> Optional[LLMToolOutput]:
        answer_match = re.search(r"Answer:\s*(\w+)", response)
        if answer_match:
            answer = answer_match.group(1).strip()
            output = PathValidatorOutput(answer == "Yes", response)
            if self.memory_agent is not None and isinstance(input, PathValidatorInput):
                self.memory_agent.record_path_validation(
                    input.bug_type,
                    input.values_to_functions,
                    output.is_reachable,
                    output.explanation_str,
                )
            self.logger.print_log("Output of path_validator:\n", str(output))
        else:
            self.logger.print_log(f"Answer not found in output")
            output = None
        return output
