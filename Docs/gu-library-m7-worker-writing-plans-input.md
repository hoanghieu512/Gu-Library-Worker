# Gú's Library — M7 Worker: đầu vào cho `writing-plans`

> **Mục đích file này:** đầu vào cho `writing-plans` chạy *trong Claude Code*, tại **repo worker riêng** (`gu-library-worker`, KHÔNG phải repo app). Mô tả mục tiêu + ràng buộc + nghiệm thu; CC tự bung thành plan chi tiết (TDD, exact path) theo codebase thật.
> **Đọc kèm:** `gu-library-sidecar-schema.md` (hợp đồng output — BẮT BUỘC theo) · `gu-library-design-spec.md` mục 5.4 (thiết kế worker) · 4.2 (sidecar) · 4.4 (trạng thái ⏳).

---

## Worker là gì

Script **Python** chạy trên **mini PC Windows 24/7**, biến file gốc trong `_inbox/` thành cặp `PDF + sidecar JSON` đặt đúng folder môn. **KHÔNG nằm trong app.** Repo riêng, toolchain Python (venv), không lẫn app TS/Android.

Thư viện chốt: **PyMuPDF** (PDF + toạ độ text), **python-docx** (Word), **python-pptx** (PPTX), **LibreOffice headless** (convert mọi thứ → PDF, gọi qua subprocess).

---

## Luồng một vòng quét (polling, stateless)

Scheduled Task gọi worker **mỗi vài phút**. Mỗi lần: quét `_inbox/` một vòng → xử file đủ điều kiện → thoát. KHÔNG thường trú, KHÔNG fs-event. Không giữ sổ "đã xử" — trạng thái derive từ filesystem (file gốc còn trong `_inbox/` = chưa xong).

**Cổng lọc đầu vào (làm TRƯỚC mọi việc):**
1. Chỉ nhận đuôi ∈ {pdf, doc, docx, ppt, pptx}.
2. **Stability check:** đọc size 2 lần cách nhau vài giây; chỉ xử khi size đứng yên (chống đụng file Syncthing/trình duyệt đang ghi dở).
3. Bỏ thẳng đuôi tạm: `.tmp`, `.crdownload`, `.syncthing.*`; lờ đuôi lạ + file ẩn/hệ thống.
4. File không hợp lệ **để yên, KHÔNG xóa** (app hiện ⏳ làm tín hiệu dọn tay).

**Với mỗi file hợp lệ:**
0. Đọc tiền tố môn `[<môn>]` từ tên file. `[Chưa phân loại]` → khu chưa phân loại.
1. Convert → PDF (LibreOffice headless). **PDF gốc giữ nguyên, không convert lại.**
2. Extract sidecar theo `gu-library-sidecar-schema.md`. Word/PPTX extract từ *file gốc*; **PDF gốc extract thẳng trên PDF** (ca khó nhất — degrade sạch về `paragraph` nếu hụt cấu trúc, KHÔNG BAO GIỜ mất text).
3. Đặt cặp `.pdf` + `.json` vào folder môn, bỏ tiền tố khỏi tên, **bỏ file gốc**.
4. (Syncthing tự rải — ngoài phạm vi worker.)

**Trùng tên đích trong cùng môn:** tên đã tồn tại → auto-suffix `(1)` cho **cả cặp** (`tên (1).pdf` + `tên (1).json`). KHÔNG ghi đè, KHÔNG để kẹt. Kiểm trùng tính cả file xử trong cùng vòng quét.

---

## Ràng buộc cứng (không được vi phạm)

- **Output đúng schema:** sidecar phải khớp `gu-library-sidecar-schema.md` (schemaVersion 1). Đây là hợp đồng với app + Phase 2.
- **Không bao giờ mất text:** parse hụt cấu trúc → rơi `paragraph`/`slide`, vẫn giữ đủ text + page. Mất cấu trúc chấp nhận được, mất text thì không.
- **Không ghi đè, không xóa nhầm:** trùng tên → suffix; file lạ → để yên. Worker chỉ xóa **file gốc đã xử xong** trong `_inbox/`, không xóa gì khác.
- **Stateless:** không file sổ trạng thái tập trung. Quét lại từ filesystem mỗi vòng.
- **`bbox` CHƯA thêm** — chờ spike highlight (xem dưới). Phase này chỉ neo `page`.

---

## Bước 0 — Spike highlight (làm TRƯỚC khi khoá schema)

Kho còn ~5 file → đập-kho-làm-lại gần như free *lúc này*. Trước khi khoá schema bản cuối:
- Thử highlight overlay một đoạn trên PDF bằng thư viện Viewer của app.
- **Khả thi** → thêm field `bbox` vào schema (PyMuPDF nhả được toạ độ text), chạy lại worker trên 5 file.
- **Không khả thi** → bỏ highlight khỏi Phase 2, schema chốt ở `page`.

Spike này có thể chạy song song, không chặn worker lõi. Nhưng phải **quyết xong trước khi tuyên bố schema final**.

---

## Test (TDD)

**Repo:** riêng. Schema nguồn ở spec; worker tự có validator so sidecar sinh ra với hình dạng kỳ vọng.

**Fixture hai tầng:**
- **Tổng hợp** (assert chặt): Word luật mini (vd đúng "Điều 1, Điều 2, Khoản 1") → assert đúng số/loại unit; PPTX vài slide → assert mỗi slide một unit; file `.tmp`/0-byte → assert bị bỏ qua.
- **Thật** (smoke = nghiệm thu): 5 file của Gú (3 PDF luật + Word + PPTX) → chạy thật, mắt soi sidecar hợp lý.

**Ba lớp test:**
1. **Lọc đầu vào** — `.tmp`/`.crdownload`/đuôi lạ/0-byte/đang-ghi-dở bị bỏ; chỉ file hợp lệ + ổn định mới xử.
2. **Mỗi reader ra đúng hình dạng** — docx→dieu/khoan; pptx→slide 1-1; pdf prose→paragraph degrade sạch; không mất text.
3. **Đặt đúng chỗ** — bỏ tiền tố, cặp vào đúng môn, trùng tên→suffix cả cặp, gốc bị bỏ, "Chưa phân loại" đúng khu.

---

## Nghiệm thu (= checklist M7 trong build brief)

- [ ] Spike highlight xong → quyết `bbox`.
- [ ] Word luật → PDF + JSON đúng môn, gốc xóa, sidecar có Điều/Khoản + trang.
- [ ] PPTX → mỗi slide một unit `slide` + trang 1-1.
- [ ] PDF luật thật (không convert) → extract thẳng, degrade sạch, không mất text.
- [ ] File `.tmp` thật trong `_inbox/` → bỏ qua, không nuốt nửa vời.
- [ ] Trùng tên đích cùng môn → cặp thứ hai `(1)`, không đè.
- [ ] "Chưa phân loại" → đúng khu.
- [ ] *(Quan sát)* `.syncthing.*.tmp` có chớp qua `_inbox/` lúc nhận file không → tinh chỉnh lọc.

---

## Việc tay tiền đề (ngoài CC)

- Mini PC đã cài: Python + LibreOffice + Syncthing (Windows service, đã có từ M3/M8).
- 5 file thật đã nằm chờ trong `_inbox/` (3 PDF + Word + PPTX) + 1 file `.tmp` (fixture lọc). Sẵn sàng làm đầu vào chạy thật.
- Đăng ký Scheduled Task chạy worker mỗi vài phút (sau khi worker pass test).
