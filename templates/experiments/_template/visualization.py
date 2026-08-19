# @dependency-start
# contract template
# responsibility Owns the experiment topic visualization status and renderer extension point.
# upstream design ../../../documents/design/experiment-topic-template.md defines the single visualization owner.
# downstream implementation run.py aggregates the status into the run summary.
# @dependency-end

"""実験 topic の可視化状態と renderer 拡張点を所有します.

既定 scaffold は notebook や共通の描画実装を生成しません。topic が可視化を必要とする
場合だけ、この module の ``render`` を topic 固有の HTML/画像生成処理に置き換えます。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import NoReturn


VISUALIZATION_STATUS_NAME = "visualization-status.json"


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """JSON status を同一 directory の一時 file 経由で atomic に公開します."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def write_visualization_not_requested_status(run_dir: Path) -> str:
    """可視化を要求していない run の明示的な status を保存します."""
    _atomic_write_json(
        run_dir / VISUALIZATION_STATUS_NAME,
        {
            "state": "not_requested",
            "requested": False,
            "consumer": "visualization.py",
            "readback": "visualization was not requested for this run",
        },
    )
    return "not_requested"


def render(run_dir: Path, template_dir: Path) -> NoReturn:
    """topic が実装する renderer の拡張点です."""
    del run_dir, template_dir
    raise NotImplementedError("implement render in this experiment topic")


def execute_visualization(run_dir: Path, template_dir: Path) -> str:
    """要求された可視化を実行し、未実装なら blocked として保持します."""
    requested = os.environ.get("EXPERIMENT_RUN_VISUALIZATION", "0") == "1"
    if not requested:
        return write_visualization_not_requested_status(run_dir)
    try:
        render(run_dir, template_dir)
    except NotImplementedError as error:
        _atomic_write_json(
            run_dir / VISUALIZATION_STATUS_NAME,
            {
                "state": "blocked",
                "requested": True,
                "consumer": "visualization.py",
                "failure_class": "expected_contract",
                "failure_message": str(error),
            },
        )
        raise RuntimeError("visualization_requested_but_renderer_unimplemented") from error
    _atomic_write_json(
        run_dir / VISUALIZATION_STATUS_NAME,
        {
            "state": "success",
            "requested": True,
            "consumer": "visualization.py",
            "readback": "topic renderer completed",
        },
    )
    return "success"
