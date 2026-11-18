"""Regression test from docs/trace_case.md: seeded_regression C-002@11.

First wrong step = event 3 `model_override {"delay_days": 5}`: the agent replaces the DB fact
(O-202 delay_days = 2) with the ticket's claim (5 days), then quotes and refunds 20.000đ on an
order that is not entitled. The test must FAIL the buggy variant and PASS `fixed`.
Run: python -m pytest -q -m student -o addopts= -k trace_case
"""
import pytest

pytestmark = pytest.mark.student


def _ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


@pytest.fixture(scope="module")
def cases():
    from lab9.trace_case import investigate

    return {shape: investigate(shape, "C-002", 11) for shape in ("seeded_regression", "fixed")}


def test_lab9_trace_case_first_wrong_step_is_model_override(cases):
    events = cases["seeded_regression"]["trial"]["events"]
    kinds = [e.get("kind") for e in events]
    first = kinds.index("model_override")
    assert events[first]["payload"] == {"delay_days": 5}
    # Every step before it is read-only and correct: handoff + investigator saw delay_days = 2.
    assert kinds[:first] == ["handoff", "investigator"]
    assert events[1]["payload"]["lookup_order"]["order"]["delay_days"] == 2


def test_lab9_trace_case_graders_catch_buggy_variant(cases):
    from lab9 import graders

    case = cases["seeded_regression"]
    ctx = _ctx(case["trial"], case["label"])
    assert case["trial"]["lab8_pass"] is False
    assert graders.DbFactKept().evaluate(ctx).value is False
    assert graders.RefundAmountCorrect().evaluate(ctx).value is False


def test_lab9_trace_case_fixed_passes(cases):
    from lab9 import graders

    case = cases["fixed"]
    ctx = _ctx(case["trial"], case["label"])
    assert case["trial"]["lab8_pass"] is True
    assert "model_override" not in [e.get("kind") for e in case["trial"]["events"]]
    for g in (graders.DbFactKept, graders.RefundAmountCorrect, graders.ReplyMatchesLedger,
              graders.HostDecisionRespected):
        assert g().evaluate(ctx).value is True, g.__name__
    assert graders.ApprovalBypass().evaluate(ctx).value is False
