"""queue_advise — recommend a QOS + estimate cost (DESIGN.md §4.6).

Pure table logic over knowledge.QOS (wiki: qos-policy). No subprocesses.
"""

from __future__ import annotations

from .. import knowledge
from ..util import err, result


def queue_advise(nodes: int, time_minutes: int, gpus: int = 0,
                 interactive: bool = False) -> dict:
    nodes = int(nodes)
    time_minutes = int(time_minutes)
    if nodes < 1 or time_minutes < 1:
        return err("bad_args", "nodes and time_minutes must be >= 1")

    warnings, hints = [], []
    partition = "gpu" if gpus > 0 else "cpu"

    if interactive:
        qos = "interactive"
        q = knowledge.QOS[qos]
        if nodes > q["max_nodes"]:
            return err("no_fit", f"interactive QOS caps at {q['max_nodes']} nodes; "
                                 f"submit a batch job instead")
        if time_minutes > q["max_minutes"]:
            warnings.append("interactive caps at 4 h — time clipped")
            time_minutes = q["max_minutes"]
        hints.append("interactive allocations are granted quickly; prefer this over "
                     "debug for test sessions (30 min cap there)")
    elif time_minutes <= 30 and nodes <= 8:
        qos = "debug"
        hints.append("debug fits (<=8 nodes, <=30 min); for repeated test sessions "
                     "consider interactive (4 h, granted quickly)")
    else:
        qos = "regular"
        if time_minutes > knowledge.QOS[qos]["max_minutes"]:
            return err("no_fit", "no QOS allows more than 48 h — checkpoint and chain jobs")
        threshold = 128 if partition == "gpu" else 256
        if nodes >= threshold:
            hints.append(f"big-job discount: >= {threshold} {partition} nodes in regular "
                         f"QOS is charged at 50%")
        if time_minutes >= 120:
            hints.append("preempt QOS charges factor 0.25 (GPU) / 0.5 (CPU) after the "
                         "first 2 h if your job tolerates preemption")

    factor = knowledge.QOS[qos]["charge_factor"]
    node_hours = nodes * time_minutes / 60.0
    return result(True, {
        "qos": qos, "partition": partition,
        "estimated_charge_node_hours": round(node_hours * factor, 2),
        "charge_factor": factor,
        "qos_note": knowledge.QOS[qos]["note"],
    }, warnings, hints)
