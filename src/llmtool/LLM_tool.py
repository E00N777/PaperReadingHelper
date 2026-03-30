from llmtool.LLM_utils import *
from abc import ABC, abstractmethod
from typing import Dict, Optional, Type, TypeVar, cast
import threading
from ui.logger import Logger


class LLMToolInput(ABC):
    def __init__(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def __hash__(self) -> int:
        raise NotImplementedError

    def __eq__(self, value) -> bool:
        return self.__hash__() == value.__hash__()


class LLMToolOutput(ABC):
    def __init__(self):
        pass


T = TypeVar("T", bound=LLMToolOutput)


class LLMTool(ABC):
    def __init__(
        self,
        model_name: str,
        temperature: float,
        language: str,
        max_query_num: int,
        logger: Logger,
    ) -> None:
        self.language = language
        self.model_name = model_name
        self.temperature = temperature
        self.language = language
        self.max_query_num = max_query_num
        self.logger = logger

        self.model = LLM(model_name, self.logger, temperature)
        self.cache: Dict[LLMToolInput, LLMToolOutput] = {}
        self._cache_lock = threading.Lock()
        self._stats_lock = threading.Lock()

        self.input_token_cost = 0
        self.output_token_cost = 0
        self.total_query_num = 0

    def invoke(self, input: LLMToolInput, cls: Type[T]) -> Optional[T]:
        """
        Invoke the LLM tool with the given input.
        :param input: the input of the LLM tool
        :param cls: the class of the output
        :return: the output of the LLM tool
        """
        output = self._invoke(input)
        if output is None:
            return None

        if not isinstance(output, cls):
            raise TypeError(f"Expected output of type {cls}, but got {type(output)}")

        return cast(T, output)

    def _invoke(self, input: LLMToolInput) -> Optional[LLMToolOutput]:
        class_name = type(self).__name__
        self.logger.print_console(f"The LLM Tool {class_name} is invoked.")
        with self._cache_lock:
            cached_output = self.cache.get(input)
        if cached_output is not None:
            self.logger.print_log("Cache hit.")
            return cached_output

        prompt = self._get_prompt(input)
        self.logger.print_log("Prompt:", "\n", prompt)

        single_query_num = 0
        output = None
        while True:
            if single_query_num > self.max_query_num:
                break
            single_query_num += 1
            response, input_token_cost, output_token_cost = self.model.infer(
                prompt, True
            )
            self.logger.print_log("Response:", "\n", response)
            with self._stats_lock:
                self.input_token_cost += input_token_cost
                self.output_token_cost += output_token_cost
            output = self._parse_response(response, input)

            if output is not None:
                break

        with self._stats_lock:
            self.total_query_num += single_query_num
        if output is not None:
            with self._cache_lock:
                self.cache[input] = output
        return output

    @abstractmethod
    def _get_prompt(self, input: LLMToolInput) -> str:
        pass

    @abstractmethod
    def _parse_response(
        self, response: str, input: Optional[LLMToolInput] = None
    ) -> Optional[LLMToolOutput]:
        pass
