# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend REPLAY, verdict judge lưu sẵn trong CSV). Lớp dương = `FAIL` (việc của judge là *tìm* lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** | **dùng** (chỉ cho giọng văn, không cho tiền) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (κ, R) | **loại** |

Ma trận nhầm lẫn:
- tone_ok: `tp=24 fp=4 fn=6 tn=66`. Tỉ lệ fail quan sát 0.28, sau hiệu chỉnh Rogan-Gladen là **0.30** (sens 0.8, spec 66/70 ≈ 0.943).
- helpful: `tp=9 fp=0 fn=21 tn=70`. Tỉ lệ fail quan sát 0.09, sau hiệu chỉnh Rogan-Gladen là **0.30**. Judge bỏ sót 21/30 reply hỏng, nên tỉ lệ lỗi thật cao gấp ~3 lần con số judge báo.

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | **Người** | Xưng "em", "nha" quá suồng sã. Rubric thêm: *xưng hô chuẩn CS là "LogiX" + "anh/chị"; "em/bạn/nha/nhé" là FAIL*. |
| 2 | tone H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | **Người** | Cùng lỗi xưng hô ("bạn ơi"). Thêm 2 ví dụ few-shot FAIL có "bạn". |
| 3 | tone H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | **Người** | Judge chỉ bắt từ lịch sự ("Dạ", "vui lòng") mà bỏ qua giọng ra lệnh. Rubric: *câu mệnh lệnh cấm khách liên hệ là FAIL dù có kính ngữ*. |
| 4 | tone H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Judge phạt vì "thiếu xin lỗi". Rubric ghi rõ: *xin lỗi không bắt buộc khi đã giải quyết xong; ngắn gọn đủ ý là PASS*. |
| 5 | tone H-051 "LogiX đã refund 90.000đ…" | FAIL | PASS | **Người** | Style guide LogiX cho phép "refund". Thêm whitelist thuật ngữ tiếng Anh được phép. |
| 6 | tone H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | **Người** | Rubric: *emoji cười trong ngữ cảnh khiếu nại là FAIL*. |
| 7 | tone H-081 "Dạ, đơn O-107 chưa đủ điều kiện…" | FAIL | PASS | **Judge** | Người đọc nhầm ticket. **Sửa nhãn người**, không sửa rubric. Đây là lý do mỗi bất đồng phải được audit, không mặc định người đúng. |
| 8 | tone H-094 "Da, LogiX da hoan 40.000đ…" (mất dấu) | PASS | FAIL | **Người** | Rubric: *tiếng Việt không dấu / dịch máy là FAIL*. |
| 9 | helpful HL-015 "LogiX đã hoàn 55.000đ cho đơn O-112" (ledger 40.000đ) | PASS | FAIL | **Người** | Judge không thấy ledger nên không thể biết số tiền sai. **Không sửa được bằng rubric**: số tiền phải chấm bằng code (`reply_matches_ledger`). |
| 10 | helpful HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | **Người** | Không nói kết quả và số tiền, sai xưng hô. Rubric helpful: *reply phải nêu trạng thái + số tiền (nếu có) + bước tiếp theo*. |

## Kết luận
- **tone_ok dùng được** làm metric phụ (non-blocking) cho giọng văn: κ=0.757, P=0.857, R=0.8 đều trên sàn. Vẫn còn 6 FN, chủ yếu về xưng hô và emoji (case 1, 2, 6), đã đưa vào rubric v2.
- **helpful bị loại, không được dùng làm gate.** R=0.30: judge bỏ sót 21/30 reply hỏng. 18/21 lần bỏ sót là **sai số tiền** (HL-015, -016, -020, -028, …; cột `human_failure = sai tiền`), loại lỗi judge không thể thấy vì nó không đọc ledger. P=1.0 chỉ có nghĩa là khi judge nói FAIL thì đúng, chứ không có nghĩa là judge bắt được lỗi. κ=0.375 < 0.6. Nếu dùng làm gate, PR làm hỏng số tiền trong reply vẫn sẽ xanh. Thay vào đó, FM-08 được chấm bằng code (`ReplyMatchesLedger`), đúng quy tắc *tiền luôn chấm bằng code*.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí, cùng phân phối với dữ liệu calibrate). Cần nhãn người mới để có held-out thật trước khi tin κ trên traffic thật. Sau khi sửa rubric phải calibrate lại (κ, P, R) trên tập mới.
