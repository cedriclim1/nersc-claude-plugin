"""queue_advise — recommend a QOS + estimate cost (DESIGN.md §4.6).

Pure table logic over knowledge.QOS (wiki: qos-policy). No subprocesses.
All limits/factors come from the knowledge table — never hardcoded here.
"""

from __future__ import annotations

from .. import knowledge
from ..util import err, result

# Big-job regular-QOS discount thresholds (wiki: qos-policy).
DISCOUNT_NODES = {"gpu": 128, "cpu": 256}


def queue_advise(nodes: int, time_minutes: int, gpus: int = 0,
                 interactive: bool = False) -> dict:
    nodes = int(nodes)
    time_minutes = int(time_minutes)
    if nodes < 1 or time_minutes < 1:
        return err("bad_args", "nodes and time_minutes must be >= 1")

    warnings, hints = [], []
    partition = "gpu" if gpus > 0 else "cpu"
    debug_q = knowledge.QOS["debug"]
    inter_q = knowledge.QOS["interactive"]
    preempt_q = knowledge.QOS["preempt"]

    if interactive:
        qos = "interactive"
        if nodes > inter_q["max_nodes"]:
            return err("no_fit", f"interactive QOS caps at {inter_q['max_nodes']} nodes; "
                                 f"submit a batch job instead")
        if time_minutes > inter_q["max_minutes"]:
            warnings.append(f"interactive caps at {inter_q['max_minutes'] // 60} h — time clipped")
            time_minutes = inter_q["max_minutes"]
        hints.append("interactive allocations are granted quickly; prefer this over "
                     f"debug for test sessions ({debug_q['max_minutes']} min cap there)")
    elif time_minutes <= debug_q["max_minutes"] and nodes <= debug_q["max_nodes"]:
        qos = "debug"
        hints.append(f"debug fits (<= {debug_q['max_nodes']} nodes, "
                     f"<= {debug_q['max_minutes']} min) but allows only "
                     f"{debug_q['run_limit']} running jobs; for repeated test sessions "
                     f"consider interactive ({inter_q['max_minutes'] // 60} h, granted quickly)")
    else:
        qos = "regular"
        if time_minutes > knowledge.QOS[qos]["max_minutes"]:
            return err("no_fit", "no QOS allows more than "
                                 f"{knowledge.QOS[qos]['max_minutes'] // 60} h — "
                                 "checkpoint and chain jobs")
        threshold = DISCOUNT_NODES[partition]
        if nodes >= threshold:
            hints.append(f"big-job discount: >= {threshold} {partition} nodes in regular "
                         f"QOS is charged at 50%")
        if time_minutes >= preempt_q["min_minutes"]:
            hints.append("preempt QOS charges factor 0.25 (GPU) / 0.5 (CPU) after the "
                         "first 2 h if your job tolerates preemption")
        if nodes == 1:
            hints.append("if you need less than a full node, shared QOS charges only "
                         "the fraction used")
        hints.append(f"premium QOS exists for urgent work but costs factor "
                     f"{knowledge.QOS['premium']['charge_factor']:.0f}x, escalating to "
                     f"4x after 20% of the allocation is spent on premium")

    factor = knowledge.QOS[qos]["charge_factor"]
    node_hours = nodes * time_minutes / 60.0
    return result(True, {
        "qos": qos, "partition": partition,
        "estimated_charge_node_hours": round(node_hours * factor, 2),
        "charge_factor": factor,
        "qos_note": knowledge.QOS[qos]["note"],
    }, warnings, hints)
