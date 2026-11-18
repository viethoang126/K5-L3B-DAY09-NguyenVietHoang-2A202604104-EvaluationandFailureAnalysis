# Lab 9: Evaluation & Failure Analysis (M0–M7)

Core M0–M4 + Advanced M5–M6 + Expert M7. Mọi report sinh bằng `python -m lab9.eval`, không sửa tay. Chi tiết: `docs/eval_card.md`.

- M1: taxonomy FM-01…FM-09 có trace evidence, `evalset --check` = 0 problem
- M2: tone κ=0.757 P=0.857 R=0.8 (dùng), helpful κ=0.375 R=0.30 (loại), audit 10 bất đồng
- M3: `ApprovalBypass`, `RefundAmountCorrect` + metric FM-08 `reply_matches_ledger` + `host_decision_respected`; detection 100%, false alarm 0%
- M4: paired bootstrap khớp tham chiếu; `fixed` exit 0, `seeded_regression` exit 1
- M5–M7: slice gate, `pass_hat_5`, `integrity_check` + ratchet; scorecard 3/3, 0 báo nhầm; 4/4 trap bị chặn

## Gate: seeded_regression (exit 1)
```
$ python -m lab9.gate --pr reports/eval_seeded_regression.json --baseline reports/baseline_v1.json
gate: PR E-seeded_regression-20261118-a053 vs main E-swarm-20261118-a053 · eval set a053c1d54b65
  approval_bypass        0        {"max": 0}                                                            ok
  secret_leak            0        {"max": 0}                                                            ok
  db_fact_kept           0.9286   {"min": 0.95}                                                         warn
  refund_amount_correct  0.8571   {"min": 0.95, "no_significant_drop": true} Δ -0.129 CI [-0.315, +0.000] BLOCK
  pass_rate              0.7143   {"min": 0.85, "no_significant_drop": true} Δ -0.271 CI [-0.500, -0.057] BLOCK
  pass_5                 0.7143   {"min": 0.8}                                                          warn
  cost_per_success       81.202   {"max_increase": 0.1}                                                 warn
  reply_matches_ledger   0.7857   {"min": 1.0, "no_significant_drop": true} Δ -0.214 CI [-0.429, +0.000] BLOCK
  host_decision_respected 0.8571   {"min": 0.95, "no_significant_drop": true} Δ -0.143 CI [-0.357, +0.000] BLOCK
exit 1 — blocked: refund_amount_correct, pass_rate, reply_matches_ledger, host_decision_respected
```

## lab9.mutation: detect, A/A, scorecard
```
detection 100.00% (target >=80%) · false alarms 0.00% (target <=10%)
metric                 spec seeds  alt seeds    delta
approval_bypass                 0          0  +0.0000
secret_leak                     0          0  +0.0000
db_fact_kept               0.9786     0.9786  +0.0000
refund_amount_correct      0.9786     0.9786  +0.0000
pass_rate                  0.9786     0.9786  +0.0000
reply_matches_ledger          1.0        1.0  +0.0000
host_decision_respected        1.0        1.0  +0.0000
pass_5                     0.8929     0.8929  +0.0000
pass_at_1                  0.9786     0.9786  +0.0000
pass_hat_1                 0.9786     0.9786  +0.0000
pass_at_3                     1.0        1.0  +0.0000
pass_hat_3                 0.9357     0.9357  +0.0000
pass_at_5                     1.0        1.0  +0.0000
pass_hat_5                 0.8929     0.8929  +0.0000
cost_per_success          50.8077    50.8077  +0.0000
  fixed                expect merge got merge ok          
  honest_refactor      expect merge got merge ok          
  seeded_regression    expect block got block ok          refund_amount_correct, pass_rate, pass_hat_5, reply_matches_ledger, host_decision_respected, slice:money_movement/pass_rate, slice:money_movement/refund_amount_correct, slice:adversarial/pass_rate, slice:adversarial/refund_amount_correct, slice:denial/pass_rate
  slice_regression     expect block got block ok          slice:money_movement/pass_rate, slice:money_movement/refund_amount_correct, slice:adversarial/refund_amount_correct
  flaky_regression     expect block got block ok          pass_rate, pass_hat_5, slice:money_movement/pass_rate, slice:money_movement/refund_amount_correct
mutation score 3/3 · false alarms 0
mutation exit=0
```

## Traps: gate trên từng file (4 × exit 1)
```
$ python -m lab9.gate --pr reports/traps/evaluator_errors_as_nan.json --baseline reports/baseline_v2.json --spec config/metric_spec_v2.yaml
  INTEGRITY 9 row(s) have no value for graded metric refund_amount_correct (missing / crashed grader)
  INTEGRITY 9 row(s) have no value for graded metric pass_rate (missing / crashed grader)
exit 1 — blocked: integrity
$ python -m lab9.gate --pr reports/traps/dropped_failing_rows.json --baseline reports/baseline_v2.json --spec config/metric_spec_v2.yaml
  INTEGRITY 131 rows, manifest promises 28 items x 5 seeds = 140
  INTEGRITY (item_id, seed) set differs from baseline: 9 missing, 0 extra
exit 1 — blocked: integrity
$ python -m lab9.gate --pr reports/traps/cherry_picked_seeds.json --baseline reports/baseline_v2.json --spec config/metric_spec_v2.yaml
  INTEGRITY (item_id, seed) set differs from baseline: 84 missing, 0 extra
  INTEGRITY manifest seeds [22, 44] != baseline [11, 22, 33, 44, 55]
exit 1 — blocked: integrity
$ python -m lab9.gate --pr reports/traps/loosened_spec.json --baseline reports/baseline_v2.json --spec reports/traps/loosened_spec.spec.yaml --base-spec config/metric_spec_v2.yaml
  INTEGRITY ratchet: slice adversarial/pass_rate removed
  INTEGRITY ratchet: slice adversarial/refund_amount_correct removed
  INTEGRITY ratchet: slice denial/pass_rate removed
exit 1 — blocked: integrity
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
