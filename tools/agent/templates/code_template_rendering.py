# @dependency-start
# contract tool
# responsibility Owns the package-safe canonical renderer for materializable code templates.
# upstream design ../../templates/code/README.md code-template source and readback contract.
# downstream implementation ../../templates/code/python/docstring_template.py parse-valid source.
# @dependency-end

"""Code template を canonical source root から安全に materialize します."""

from __future__ import annotations

from pathlib import Path

if __package__:
    from .agent_canon_source_root import resolve_agent_canon_source_root
else:
    from agent_canon_source_root import resolve_agent_canon_source_root


def render_code_template(template_name: str) -> str:
    """
    Canonical source root 内の code template を読み戻します.

    Args:
        template_name: `templates/code/` からの英語相対 path。

    Returns:
        destination materialization に使う UTF-8 source。

    Raises:
        RuntimeError: template path が owner root 外へ escape する場合。
        FileNotFoundError: template が存在しない場合。

    Side effects:
        source file を読むだけで、source または destination を変更しません。
    """
    source_root = resolve_agent_canon_source_root(Path.cwd()).source_root
    template_root = (source_root / "templates" / "code").resolve()
    template_path = (template_root / template_name).resolve()
    try:
        template_path.relative_to(template_root)
    except ValueError as error:
        raise RuntimeError(f"code template escapes owner: {template_name}") from error
    if not template_path.is_file():
        raise FileNotFoundError(f"code template not found: {template_name}")
    return template_path.read_text(encoding="utf-8")
