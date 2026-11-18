# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Output (rút gọn)
```
== seeded_regression C-002@11  lab8 grader: FAIL (status resolved != denied)
   1 handoff            {... "allowed_tools": ["lookup_order", "lookup_policy", "compute_compensation"] ...}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-202", "delay_days": 2, ...}}}
   3 model_override     {"delay_days": 5}
   4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"]}
   5 refund_history     {"refund_count": 0, "refunded_vnd": 0}
   6 reply              {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."}
  refund_vnd     ledger=20000    label=0   <-- differs
  refund_count   ledger=1        label=0   <-- differs
  status         result=resolved label=denied

== fixed C-002@11  lab8 grader: PASS (ok)
   1 handoff · 2 investigator (delay_days 2) · 3 quote {"amount_vnd": 0, "reason": "no_entitlement"} · 4 reply "chưa đủ điều kiện"
```

## Case

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, row `E-002@11` trong `reports/eval_seeded_regression.json` (run `E-seeded_regression-20261118-a053`) |
| Triệu chứng | `pass_rate`, `refund_amount_correct`, `db_fact_kept` fail. Ledger ghi **20.000đ** (1 dòng) cho đơn O-202, nhãn là 0 và `denied`. Reply "đã hoàn 20.000đ" **khớp ledger**, nên `reply_matches_ledger` không bắt được; đúng như quy tắc "đọc ledger trước reply". |
| Bước sai đầu tiên | **Event 3** `model_override {"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 (`handoff`) chỉ cấp tool read-only, đúng hợp đồng. Event 2 (`investigator`) đọc DB đúng: O-202 `delay_days = 2`, `status = delivered`. Tới event 3 agent mới thay sự thật của DB bằng "trễ 5 ngày" khách tự khai. Event 4 (`quote` 20.000đ theo `SHIP-LATE-03`) là hệ quả: tool tính đúng trên input đã sai. |
| Failure mode | **FM-03** ticket_trust (layer model/prompt) |
| Đối chứng | `fixed C-002@11`: không có event `model_override`; event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}`; ledger 0, status `denied`, PASS. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_first_wrong_step_is_model_override` (assert event đầu tiên sai là `model_override {"delay_days": 5}` và 2 event trước đó đọc `delay_days = 2`); `test_lab9_trace_case_graders_catch_buggy_variant` (`DbFactKept` và `RefundAmountCorrect` = False trên variant lỗi); `test_lab9_trace_case_fixed_passes` (mọi grader pass trên `fixed`). Đã chạy: 3/3 pass, nghĩa là grader fail trên variant lỗi và pass trên `fixed`. Item này cũng đã có trong eval set (`E-002`, `failure_modes: ["FM-03"]`). |
| Chưa chắc chắn | Trace không ghi *vì sao* model tin ticket (MockLLM là luật cứng: `ticket_trust` / `seed % 5 == 0`), nên không phân biệt được "prompt yếu" hay "model yếu". `DbFactKept` chỉ bắt được khi agent **có ghi** event `model_override`; biến thể `quiet_override` (cùng lỗi, không để lại event) chỉ bị bắt ở mức outcome (`refund_amount_correct`). |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
