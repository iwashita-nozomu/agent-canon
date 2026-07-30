from jax_util.base import algorithm_module_protocol as amp
from . import child

class InitializeConfig(amp.InitializeConfig):
    pass

class SolveConfig(amp.SolveConfig):
    pass

class Problem(amp.Problem):
    pass

class State(amp.State):
    pass

class Answer(amp.Answer):
    pass

class Info(amp.Info):
    pass

class Algorithm(amp.Algorithm):
    child_algorithm: child.Algorithm

    def __call__(self, problem: Problem, state: State, config: SolveConfig) -> Answer:
        return Answer()

def initialize(config: InitializeConfig) -> tuple[Algorithm, State]:
    child.initialize(child.InitializeConfig())
    return Algorithm(), State()

__all__ = [
    "InitializeConfig",
    "SolveConfig",
    "Problem",
    "State",
    "Answer",
    "Info",
    "Algorithm",
    "initialize",
]
