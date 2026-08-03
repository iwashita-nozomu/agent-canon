# @dependency-start
# contract reference
# responsibility Holds template experiment case definitions after copying.
# upstream design ../../../documents/experiments/experiment-registry.md defines managed experiment expectations.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses and sparse Python projection traces.
# downstream implementation run.py consumes topic-specific cases after the template is filled in.
# @dependency-end
"""Define topic-owned cases for the managed experiment entrypoint.

責務: topic-specific case と入力パラメータだけを定義する。
依存境界: worker-local domain imports は run.py の worker 内へ置く。
Docstring semantic trace: responsibility region、selected semantic delta、review evidence を
topic README/provenance から参照し、signature や型の固定 section を複製しない。
"""

# IMPLEMENT HERE: topic-owned report の domain case だけを定義する。
# managed route はこの module を実行 entrypoint として import せず、topic main() を
# 一つの ExperimentRunner task へ適応する。worker-only dependency は frozen child
# environment の後、run.py の run_case_worker() 内へ置く。
