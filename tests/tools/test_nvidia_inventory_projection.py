#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Exercises preservation of full-inventory uncertainty across candidate-scoped NVIDIA observation.
# upstream implementation ../../tools/experiments/execution/execution_resource_plan.py NVIDIA inventory and process occupancy owners
# upstream design ../../documents/experiments/gpu-admission-r5-nvidia-visibility.md local namespace and full-inventory evidence boundary
# @dependency-end
"""Synthetic #877 regressions; these do not claim WSL hardware validation."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import patch

from tools.experiments.execution.execution_resource_plan import (
    EvidenceFd,
    GpuProcessOccupancyProbe,
    NvidiaInventoryProbe,
    NvidiaStructuredObservation,
    ProcAncestryEvidence,
    ProcAncestryProbe,
    ProcessOccupancyEvidence,
    ProcessRoot,
    TypedPreflightFailure,
    parse_nvidia_smi_xml,
)


GPU_A = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
GPU_B = "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
INVENTORY = frozenset({GPU_A, GPU_B})
NAMESPACE_INODE = 42
PID = 25


def _xml(*kinds: str | None) -> bytes:
    """Keep live graphics/compute rows distinct from explicit empty tables."""
    units = []
    for uuid, kind in zip((GPU_A, GPU_B), kinds, strict=True):
        process = ""
        if kind is not None:
            name = "/Xwayland" if kind == "G" else "compute-fixture"
            process = (
                f"<process_info><pid>{PID}</pid><type>{kind}</type>"
                f"<process_name>{name}</process_name>"
                "<used_memory>N/A</used_memory></process_info>"
            )
        units.append(
            f"<gpu><uuid>{uuid}</uuid><fb_memory_usage>"
            "<total>8192 MiB</total><free>4096 MiB</free>"
            f"</fb_memory_usage><processes>{process}</processes></gpu>"
        )
    return ("<nvidia_smi_log>" + "".join(units) + "</nvidia_smi_log>\n").encode()


@contextmanager
def _evidence(payload: bytes, source_name: str) -> Iterator[EvidenceFd]:
    """Retain ordinary file descriptors through the real strict XML parser."""
    with tempfile.TemporaryFile() as handle:
        handle.write(payload)
        handle.flush()
        identity = os.fstat(handle.fileno())
        yield EvidenceFd(
            fd=handle.fileno(),
            source_name=source_name,
            st_dev=identity.st_dev,
            st_ino=identity.st_ino,
            byte_count=identity.st_size,
            sha256=hashlib.sha256(payload).hexdigest(),
        )


def _observe(
    xml: bytes, allocated: frozenset[str]
) -> tuple[NvidiaStructuredObservation, ProcessOccupancyEvidence]:
    listing = (
        f"GPU 0: Synthetic A (UUID: {GPU_A})\n"
        f"GPU 1: Synthetic B (UUID: {GPU_B})\n"
    ).encode()
    with _evidence(listing, "synthetic-list") as list_fd, _evidence(
        xml, "synthetic-wslg-xml"
    ) as xml_fd:
        disposition = parse_nvidia_smi_xml(xml_fd).process_inventory_disposition
        observation = NvidiaInventoryProbe(list_fd, xml_fd).observe_structured(
            allocated
        )
    occupancy = GpuProcessOccupancyProbe(
        inventory=observation.inventory,
        namespace_inode=NAMESPACE_INODE,
        processes=observation.processes,
        process_inventory_disposition=disposition,
        unknown_gpu_ids=tuple(observation.unknown_gpu_ids),
        xml_binding_unknown=observation.xml_binding_unknown,
    ).observe()
    return observation, occupancy


class NvidiaInventoryProjectionTest(unittest.TestCase):
    def test_unresolved_wslg_holder_on_both_gpus_survives_one_candidate(self) -> None:
        """Absence of a local proc identity must not make the other GPU FREE."""
        for candidate in (GPU_A, GPU_B):
            with self.subTest(candidate=candidate), patch.object(
                ProcAncestryProbe,
                "observe",
                side_effect=TypedPreflightFailure(
                    "gpu_process_identity_unproven",
                    "synthetic holder has no identity in the local proc namespace",
                    pid=PID,
                ),
            ) as ancestry:
                observation, occupancy = _observe(
                    _xml("G", "G"), frozenset({candidate})
                )
                self.assertEqual(ancestry.call_count, 2)
                self.assertEqual(observation.processes, ())
                self.assertEqual(observation.unknown_gpu_ids, INVENTORY)
                self.assertEqual(dict(observation.unit_states), {candidate: "UNKNOWN"})
                self.assertEqual(
                    observation.process_inventory_visibility["allocated_ids"],
                    (candidate,),
                )
                self.assertEqual(set(occupancy.unknown_uuids), INVENTORY)
                self.assertEqual(
                    dict(occupancy.unit_states), {GPU_A: "UNKNOWN", GPU_B: "UNKNOWN"}
                )
                self.assertEqual(occupancy.occupied_uuids, ())

    def test_unselected_unknown_is_not_free_or_added_to_caller_allocation(self) -> None:
        """A free candidate and an unresolved different GPU remain distinct."""
        with patch.object(
            ProcAncestryProbe,
            "observe",
            side_effect=TypedPreflightFailure(
                "gpu_process_identity_unproven", "synthetic missing proc", pid=PID
            ),
        ):
            observation, occupancy = _observe(
                _xml(None, "G"), frozenset({GPU_A})
            )
        self.assertEqual(observation.unknown_gpu_ids, frozenset({GPU_B}))
        self.assertEqual(dict(observation.unit_states), {GPU_A: "FREE"})
        self.assertEqual(
            observation.process_inventory_visibility["allocated_ids"], (GPU_A,)
        )
        self.assertEqual(
            dict(occupancy.unit_states), {GPU_A: "FREE", GPU_B: "UNKNOWN"}
        )

    def test_resolved_compute_and_graphics_holders_remain_busy(self) -> None:
        """Recognizing a graphics identity is not a graphics-sharing policy."""
        holder = ProcessRoot(
            pid=PID,
            starttime="100",
            pid_namespace=f"pid:[{NAMESPACE_INODE}]",
            cgroup="0::/synthetic-test",
        )
        ancestry = ProcAncestryEvidence(
            holder=holder,
            root=holder,
            chain=(holder,),
            pstree_available=False,
            pstree_path="",
        )
        for kind, expected_kind in (("C", "compute"), ("G", "graphics")):
            with self.subTest(kind=kind), patch.object(
                ProcAncestryProbe, "observe", return_value=ancestry
            ):
                observation, occupancy = _observe(
                    _xml(kind, None), frozenset({GPU_B})
                )
                self.assertEqual(observation.unknown_gpu_ids, frozenset())
                self.assertEqual(observation.processes[0].kind, expected_kind)
                self.assertEqual(occupancy.occupied_uuids, (GPU_A,))
                self.assertEqual(
                    dict(occupancy.unit_states), {GPU_A: "BUSY", GPU_B: "FREE"}
                )
                self.assertEqual(dict(observation.unit_states), {GPU_B: "FREE"})


if __name__ == "__main__":
    unittest.main()
