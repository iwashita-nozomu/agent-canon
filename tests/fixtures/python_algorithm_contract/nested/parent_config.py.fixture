from jax_util.base import algorithm_module_protocol as amp
from . import child

class InitializeConfig(amp.InitializeConfig):
    child_initialize: child.InitializeConfig

class SolveConfig(amp.SolveConfig):
    child_solve: child.SolveConfig

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
    child.initialize(config.child_initialize)
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
