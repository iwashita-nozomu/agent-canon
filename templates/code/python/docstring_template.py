# @dependency-start
# contract template
# responsibility Provides a parse-valid module/class/function Docstring and type-boundary example.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring contract and D213 route.
# upstream design ../README.md code-template owner and materialization contract.
# downstream implementation ../../../tools/agent_tools/manifest_rendering.py renders this source.
# @dependency-end

"""
適応可能な Python Docstring と型境界の具体例を提供します。.

この module は、owner、state invariant、units/shapes、returns、raises、side effects、
ownership を明示する materializable scaffold です。値と domain logic は利用 repo が置換します。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExampleState:
    """
    例示する責務の、検証済み immutable vector state を所有します。.

    Invariant:
        `values` は空でなく、各値は有限で、`unit` は空白ではありません。
        tuple の shape は `(n,)` であり、この class は batch dimension を所有しません。

    Args:
        values: 宣言した unit を持つ一次元の numeric value。
        unit: この state boundary が所有する人間向けの unit label。

    Raises:
        ValueError: vector が空、非有限値を含む、または unit が空白の場合。

    Side effects:
        construction は immutable tuple だけを確保し、file 書き込み、device access、
        caller-owned input の mutation を行いません。

    Ownership:
        この class は validation と state lifetime を所有します。orchestration、persistence、
        metric、external resource allocation は caller-owned unit に属します。
    """

    values: tuple[float, ...]
    unit: str

    def __post_init__(self) -> None:
        """
        型境界で vector と unit の invariant を強制します。.

        Raises:
            ValueError: state が有効な一次元 vector を表せない場合。
        """
        if not self.values:
            raise ValueError("values must contain at least one element")
        if not all(value == value and abs(value) != float("inf") for value in self.values):
            raise ValueError("values must be finite")
        if not self.unit.strip():
            raise ValueError("unit must not be blank")


def build_example_state(values: tuple[float, ...], *, unit: str) -> ExampleState:
    """
    caller-owned の一次元 input から検証済み vector state を構築します。.

    Args:
        values: shape `(n,)` の numeric vector。全 value が `unit` を使います。
        unit: `unitless` または domain-specific physical unit などの unit label。

    Returns:
        検証済み tuple と unit label を所有する immutable `ExampleState`。

    Raises:
        ValueError: values または unit が state invariant に反する場合。

    Side effects:
        external side effect はありません。返却 object は新しい immutable value であり、
        caller の container への mutable alias を保持しません。

    Ownership:
        この function は input validation と construction を所有します。caller は input
        acquisition、algorithm selection、result persistence、test oracle choice を所有します。
    """
    return ExampleState(values=tuple(values), unit=unit)


__all__ = ["ExampleState", "build_example_state"]
