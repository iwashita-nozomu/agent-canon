# @dependency-start
# contract reference
# responsibility Holds topic-owned case definitions for the managed experiment entrypoint.
# upstream design ../../../documents/experiments/experiment-registry.md defines managed experiment expectations.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses and sparse Python projection traces.
# @dependency-end

"""
managed experiment entrypoint の topic-owned case を定義します.

責務は case identity と JSON-serializable な入力だけを定義することです。domain import、
resource admission、artifact I/O は `run.py` の owning boundary に置きます。
"""

from __future__ import annotations

from case_model import CaseSpec

CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="example",
        parameters={
            "values": [1.0, 2.0, 3.0],
            "unit": "unitless",
            "shape": [3],
        },
    ),
)
