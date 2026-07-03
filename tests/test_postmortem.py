"""ACs for job_postmortem (DESIGN.md §4.4) — classifier fixtures per category."""

import pytest

from nersc_mcp.tools.postmortem import CATEGORIES, classify


def rows(state, exitcode="0:0", reason="None"):
    return [{"jobid": "1", "state": state, "exitcode": exitcode, "reason": reason}]


@pytest.mark.parametrize("state,exitcode,reason,expected", [
    ("OUT_OF_MEMORY", "0:125", "None", "oom"),
    ("FAILED", "0:125", "None", "oom"),
    ("TIMEOUT", "0:0", "None", "time_limit"),
    ("NODE_FAIL", "0:0", "None", "node_fail"),
    ("CANCELLED by 12345", "0:0", "None", "cancelled"),
    ("FAILED", "1:0", "Disk quota exceeded", "quota"),
    ("FAILED", "2:0", "None", "script_error"),
    ("COMPLETED", "0:0", "None", "unknown"),
])
def test_classifier(state, exitcode, reason, expected):
    assert classify(rows(state, exitcode, reason)) == expected


def test_all_categories_have_hints():
    from nersc_mcp.tools.postmortem import _HINTS
    assert set(_HINTS) == set(CATEGORIES)
