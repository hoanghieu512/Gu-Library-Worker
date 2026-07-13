# Changelog

Worker `gu-library-worker` (mini PC). Theo [Semantic Versioning](https://semver.org/):
feature/milestone = minor, sửa lỗi + hạ tầng vận hành nhỏ = patch. Bump version thì
cập nhật file này ngay trong cùng session (song song với `pyproject.toml` +
`src/gu_library_worker/__init__.py`).

## [0.12.0] — 2026-07-13 — Beat A: đóng ảnh thành PDF một trang
### Added
- **Nhận file ảnh trong `_inbox/`** (`.jpg/.jpeg/.png/.webp/.gif/.bmp/.tif/.tiff`): mỗi ảnh → **một PDF 1 trang riêng**, khổ trang = tỉ lệ ảnh (ảnh ngang → trang NGANG, không ép dọc, không méo). Mỗi ảnh là một tài liệu độc lập — KHÔNG bao giờ gộp nhiều ảnh. `images.image_to_single_page_pdf` (cạnh dài = 842pt/A4, nhúng JPEG giữ nguyên bytes → không re-encode, giữ nét); nhánh ảnh cắm ở `process_one_file` giữa `.pdf` và `.docx/.pptx`, rồi đi tiếp pipeline sidecar/tiền tố/đặt vào môn như thường.
- **Ảnh không có text → sidecar hợp lệ nhưng rỗng text** (tái dùng nhánh zero-text: `IMAGE_PAGE_MARKER`, không OCR, không kẹt). Ảnh nặng cho điện thoại → tái dùng chuẩn hóa scan (150dpi JPEG) để nhẹ.
- **Ảnh gốc = nguồn đã tiêu thụ** (pixel đã nằm trong PDF, Gú giữ bản trên điện thoại) → **xóa, KHÔNG archive** như scan re-raster (`Prepared.normalized` cố ý giữ `False` ở nhánh ảnh dù có chuẩn hóa nội bộ).
### Notes
- File không phải ảnh / không hợp lệ để yên như cũ (không regression). `insert_image` xác nhận lossless (probe 1600→1600, 3000→3000). 155 pass / 1 skip (+8 test ảnh: `test_images.py`, pipeline, scan; `test_constants_shapes` cập nhật do hợp đồng extension đổi theo tính năng).

## [0.11.0] — 2026-07-03 — Hạ tầng Prod: `_print/` → Drive + backup tuần offsite
### Added
- **Hai Scheduled Task Prod riêng, độc lập với `GuLibraryWorker` (rclone headless, chạy-rồi-thoát):** `GuLibraryPrintSync` (mỗi ~15 phút, `rclone sync` `_print/` → `gdrive:GuLibrary/Di-in` — mirror, tick "Xong" là file rời cả Drive) và `GuLibraryBackup` (CN 03:00 — robocopy snapshot theo ngày `…\backup\YYYY-MM-DD\` loại `.stversions`, giữ 4 bản mới nhất, rồi `rclone sync` lên `gdrive:GuLibrary/Backup`). `scripts/sync-print.ps1`, `scripts/backup.ps1` (`-SkipDrive` = snapshot local), `scripts/register-ops-tasks.ps1`.
- **Cả 3 task chạy principal S4U** (run-whether-logged-on-or-not) → sống lại sau reboot không cần logon + headless không cửa sổ. `register-task.ps1` cập nhật để `GuLibraryWorker` cũng S4U.
- `backup\` là sibling ngoài cây Syncthing; mỗi task log riêng ngoài kho (`_print-sync.log`/`_backup.log`); lỗi mạng/Drive → log + thoát, nhịp sau tự thử lại (không retry-loop, không popup). README: setup OAuth rclone + test tay.
### Notes
- KHÔNG đụng pipeline convert/sidecar/tiền tố/chuẩn hóa — regression suite nguyên trạng (147 pass / 1 skip). Verify tại chỗ: parse 4 script, snapshot + retention (giả lập 5 tuần → 4 bản), sync-print lỗi-rclone → log + exit 1.

## [0.10.0] — 2026-07-03 — Chuẩn hóa PDF scan nặng (150dpi JPEG) trước khi vào kho
### Added
- **Chỉ nhánh zero-text (PDF scan/ảnh):** nếu raster trang quá nặng cho viewer (effective DPI > 200 và/hoặc encode JPEG2000) → phát hành vào kho bản **150dpi JPEG** thay bản gốc (giữ số trang + kích thước trang points; trang xám → grayscale, có màu thật → RGB, đo độ lệch kênh mỗi trang). `normalize.is_heavy_scan` (metadata-only) + `normalize.normalize_pdf`; cắm ở điểm `src → canonical` trong `process_one_file`.
- **Archive bản gốc** `move` sang sibling `…\kho_archive\` (ngoài Syncthing) trước khi publish; log rõ. Sidecar khớp bản chuẩn hóa.
### Notes
- PDF có text layer / scan nhẹ sẵn KHÔNG bị re-raster. DOCX/PPTX/LibreOffice không đụng. ~0.8s/trang → quyển lớn kéo một vòng quét dài, kho còn lại trễ tối đa một vòng, tự lành (kiến trúc vòng lặp không đổi). 147 pass / 1 skip.

## [0.9.0] — 2026-07-02 — Tiền tố lồng (đích thư mục con `[Môn][Con]`)
### Added
- **Mỗi cặp ngoặc đầu = một cấp thư mục:** `[Luật Đất đai][Bài giảng] x.pdf` → `<kho>/Luật Đất đai/Bài giảng/`, độ sâu bất kỳ, thư mục thiếu tự tạo (`mkdir` race-safe). Một ngoặc = hành vi cũ y nguyên (tương thích ngược cứng). `subject` mang path `/`-join, `Paths.subject_dir` tách thành folder.
- **Sanitize từng segment** (chặn `..`, `/`, `\`, rỗng, bắt đầu `_`); segment độc hoặc nested dưới "Chưa phân loại" → route an toàn về "Chưa phân loại" + WARNING (không bao giờ ra ngoài kho). Dedup `(1)` áp tại thư mục con cuối.
### Notes
- 137 pass / 1 skip; 127 test cũ không sửa expectation. Điều kiện: app v1.3.0 gửi tiền tố lồng.

## [0.8.5] — 2026-07-02 — Sidecar tối thiểu cho PDF ảnh/scan (zero-text)
### Fixed
- PDF không có text layer rút 0 unit → validator `units must not be empty` → **kẹt `_inbox/` vô hạn, spam log**. Nay: rút 0 text ở TOÀN BỘ trang → sinh 1 unit/trang (type `paragraph`, `bbox` cả trang, text placeholder mang `IMAGE_PAGE_MARKER` cho Phase-2 OCR) → qua validator, vào kho, Viewer render ảnh trang. Ngưỡng: có text ở bất kỳ trang nào → nhánh thường (PDF hỗn hợp không degrade). Không OCR (để Phase 2).
### Notes
- 127 pass / 1 skip. Cũng phủ test cho nhánh legacy `.doc`/`.ppt` (convert → PDF → extract).

## [0.8.4] — 2026-07-01 — `register-task.ps1` nhận `-KhoRoot` nối phẩy
### Fixed
- `powershell -File register-task.ps1 -KhoRoot "a","b"` bị PowerShell bẹp mảng thành chuỗi `"a,b"` → task đăng ký 1 kho bogus không tồn tại → không kho nào chạy. Nay tự tách dấu phẩy (chạy đúng cả kiểu `-File` lẫn `& .\script`); một kho không đổi.

## [0.8.3] — 2026-07-01 — `register-task.ps1` resolve RepoRoot từ `$PSCommandPath`
### Fixed
- Chạy qua `powershell -File` báo "No Python found: `D:\.venv\...`" — `$PSScriptRoot` trong param-default không đáng tin (rỗng → `"\.."` → drive root `D:\`). Nay derive RepoRoot ở thân script từ `$PSCommandPath`.

## [0.8.2] — 2026-07-01 — `register-task.ps1` không báo-thành-công-giả + verify đủ kho
### Fixed
- `Register-ScheduledTask` "Access is denied" (thiếu admin) là lỗi CIM không bị `$ErrorActionPreference='Stop'` bắt → script vẫn in "Registered" láo, lại còn nhận nhầm task cũ 1-kho. Nay ép `-ErrorAction Stop` (catch + exit 1) và verify **arguments có đủ mọi `--kho`** (không chỉ kiểm task tồn tại).

## [0.8.1] — 2026-07-01 — PDF-origin hết kẹt (PyMuPDF giữ file handle → WinError 32)
### Investigation
- Thả cùng file vào 2 kho, chỉ kho đầu xử. Root cause: PDF-origin có canonical LÀ file `_inbox`; PyMuPDF (`read_pdf` + `page_count`) mở bằng path, giữ mmap sau close → `write_pair` `original.unlink()` chập chờn `WinError 32` (đo được 8/8 lần fail khi mở-bằng-path). File đã copy vào môn nhưng gốc xóa không được → kẹt + đếm failed. Cũng chính là thủ phạm mấy ca "file kẹt" bí ẩn trước.
### Fixed
- `pdf_reader._read_pages` + `pages.page_count`/`anchor_pages` mở từ bytes (`fitz.open(stream=path.read_bytes())`) → không giữ OS handle. `write_pair` xóa gốc có retry ngắn (hấp thụ khóa AV/Syncthing tạm); vẫn khóa hẳn → rollback cặp vừa ghi (tránh trùng nhịp sau).
### Notes
- 123 pass / 1 skip (+3). Không đổi schema/convert/naming/multi-kho.

## [0.8.0] — 2026-06-30 — Watch nhiều kho (một tiến trình tuần tự)
### Added
- **`--kho` lặp được → quét N kho tuần tự trong một process** (một `--kho` = y như cũ). Tách môi trường QA + Prod trên mini PC. KHÔNG song song để tránh LibreOffice headless khóa profile chung.
- **Cô lập lỗi từng kho:** mất path / mất quyền / lỗi giữa chừng → skip kho đó + log tên, vòng chạy tiếp các kho còn lại.
- **Log gắn nhãn kho:** mỗi kho một `<kho>/_worker.log`, dòng gắn `[GuLibrary]`/`[GuLibrary-Prod]` (handler attach/detach từng kho). `register-task.ps1` `-KhoRoot` nhận mảng.
### Notes
- 120 pass / 1 skip (+5). Logic per-kho không đổi.

## [0.7.11] — 2026-06-29 — Chuẩn hóa tên `.tmp` Samsung/SAF trong `_inbox`
### Added
- Android SAF (Samsung) đôi khi ghi file thật `<tên>.<ext>.tmp` trong khi báo tên sạch cho app → worker (đọc FS thật) là nơi sửa chắc. `intake.normalize_tmp_name`: file đuôi tài liệu hợp lệ nằm dưới ≥1 lớp `.tmp` (`X.pdf.tmp`, cả `X.pdf.tmp.tmp`) → rename bỏ `.tmp` rồi xử bình thường. `.syncthing.*.tmp` / `.tmp` không phải đuôi tài liệu → để yên.
### Notes
- **Stability-check TRƯỚC, strip SAU** (chủ đích, không theo spec gốc): file đang-ghi-dở và file kẹt-tên trông giống nhau, chỉ rename sau khi size đứng yên. Dedup `(k)` trước đuôi nếu tên strip ra trùng `_inbox`. 115 pass / 1 skip (+13).

## [0.7.10] — 2026-06-27 — Task chạy `pythonw.exe` (không cửa sổ)
### Fixed
- Task gọi `python.exe` (console app) → nhá cửa sổ terminal mỗi 3 phút. Nay trỏ `pythonw.exe` (không console) trong venv; vắng thì fallback `python.exe` + cảnh báo. Verify: chạy qua `pythonw` không console vẫn ghi `_worker.log` + xử file đúng (stdout/stderr None vô hại).

## [0.7.9] — 2026-06-27 — `register-task.ps1` lặp vô hạn đúng + verify thật
### Fixed
- `-RepetitionDuration ([TimeSpan]::MaxValue)` serialize ra `P10675199DT2H48M5…` → Task Scheduler từ chối (0x80041318) → register fail nhưng script vẫn in "Registered" láo. Nay: repetition vô hạn bằng cách copy `.Repetition` từ trigger lặp (Duration để trống); try/catch + `Get-ScheduledTask` verify trước khi báo thành công.

## [0.7.8] — 2026-06-27 — Log bền `_worker.log` (rotating)
### Added
- Scheduled Task chạy nền nuốt stdout → thêm `RotatingFileHandler` `<kho>/_worker.log` (~1MB×3): mỗi vòng ghi thời điểm, `ScanReport`, lý do từng file skip/failed (kèm traceback). `_`-prefix nên app/filter bỏ qua; README kèm `.stignore` giữ local. Stateless (chỉ quan sát, không đọc lại).
### Notes
- 102 pass / 1 skip (+6). Stdout giữ nguyên (chạy tay vẫn thấy).

## [0.7.7] — 2026-06-24 — Bắt dòng `Email:` khối ký số trang 1
### Fixed
- v0.7.6 bắt email đứng-riêng nhưng sót biến thể `Email: thongtinchinhphu@chinhphu.vn` → còn lọt vào Khoản trang 1 (file _3: chen giữa Khoản 1 và điểm a). Mở rộng net ký số: bắt dòng bắt đầu `Email:`/`E-mail:` + địa chỉ (mọi trang). Email nhúng trong câu thật → giữ nguyên.

## [0.7.6] — 2026-06-23 — Loại metadata trang bìa công báo (ký số + masthead)
### Fixed
- Khối chỉ-xuất-hiện-trang-1 (cơ chế lặp không bắt được): (1) cụm chữ ký số (email/`Cơ quan:`/`Thời gian ký:`) — bắt mọi trang (không bao giờ có trong text luật; file _3 chen giữa điểm a → xóa dòng cho khớp lại); (2) masthead công báo (`VĂN BẢN QUY PHẠM PHÁP LUẬT`/`CHỦ TỊCH NƯỚC - QUỐC HỘI`/`QUỐC HỘI`/`Luật số:`) — chỉ trang 1, trước đơn vị luật đầu (theo `seen_unit`). Tiêu đề luật + "Căn cứ …" giữ nguyên; Dân sự không bị loại nhầm.

## [0.7.5] — 2026-06-23 — Khóa dedup gửi-lại + log skip (điều tra)
### Investigation
- Báo: gửi lại file đã xử → kẹt `_inbox`, không sinh `(1)`. Điều tra trên code hiện tại: **không reproduce** — `naming._is_free` kiểm folng môn trên đĩa từ commit đầu, repo chưa từng có bug này. Nguyên nhân thật ở máy = build cũ / lỗi khác (đã handle/log).
### Added
- Test integration khóa hành vi gửi-lại (dedup vs cặp môn sẵn có → `(1)`, không đè, `_inbox` sạch) + log nhánh gate-skip vốn câm.

## [0.7.4] — 2026-06-22 — Loại running-header tầng-dòng + digit-mask (PDF)
### Fixed
- v0.7.2 lọc tầng block bằng text chuẩn-hóa-whitespace → trượt ca thật: Khoản vắt đáy trang bị nối footer+chữ-ký+số-trang+header-trang-kế vào CUỐI text (bbox giữa trang, ngoài band margin). Nay: dò+loại tầng **dòng, trước khi khâu qua trang**, khớp bằng **digit-mask** (số trang `3/4/5`, `Số 363+364`, `Thời gian ký: …` cùng quy về một khuôn lặp). Dòng cấu trúc (Điều/Chương) không bao giờ bị loại.

## [0.7.3] — 2026-06-22 — Smoke loại `.stversions`
### Fixed
- Smoke `KeyError: 'schemaVersion'` trên kho có M8 versioning: `rglob("*.json")` trúng sidecar schema-đời-cũ dưới `<kho>/.stversions/`. Nay `validate_document_sidecars` bỏ mọi path có thành phần `.st*` (ở bất kỳ độ sâu). Rà worker: `scan_once` chỉ quét `_inbox/` non-recursive → không bao giờ nuốt file versioned (đã có guard test).

## [0.7.2] — 2026-06-22 — Chất lượng PDF legal reader (running-header + regex Điều)
### Fixed
- **Defect 1 — running header/footer nuốt vào sidecar:** phát hiện theo hình học (text lặp cùng vùng margin qua nhiều trang) → loại ngay khâu đọc; vô hại với PDF không header.
- **Defect 2 — regex Điều quá lỏng bắt nhầm dẫn chiếu:** ranh giới Điều CHỈ nhận `Điều <số>.` (bắt buộc dấu chấm) → "Điều 201 của Luật này" thành text thường, hết Điều lặp/false-positive.
### Notes
- Chỉ nhánh PDF legal; DOCX/PPTX + đếm Điều khóa bằng regression snapshot.

## [0.7.1] — 2026-06-22 — Vá chặn smoke M7 (resolve soffice + loại `_mon.json`)
### Fixed
- **`soffice` không phụ thuộc PATH:** `convert.resolve_soffice` — `GULIB_SOFFICE` env > thư mục cài chuẩn Windows > PATH; không thấy → lỗi rõ (không lòi `[WinError 2]`). Vá ca Scheduled Task nền không có user-PATH.
- **Smoke bỏ `_mon.json`:** `validate_document_sidecars` chỉ validate sidecar tài liệu (có `.pdf` cùng basename, không `_`-prefix) → hết `KeyError: 'schemaVersion'` trên `_mon.json`.

## [0.1.0] — 2026-06-21 — M7: worker convert + extract sidecar
### Added
- **Worker Python stateless polling `_inbox/` (Scheduled Task mỗi vài phút):** cổng lọc {pdf,doc,docx,ppt,pptx} + stability-check + bỏ đuôi tạm; đọc tiền tố môn `[<môn>]`; convert non-PDF → PDF (LibreOffice headless, PDF gốc giữ nguyên); extract sidecar theo `Docs/gu-library-sidecar-schema.md` (schemaVersion 1: `dieu/khoan/diem/slide/heading/paragraph`, degrade sạch về `paragraph`/`slide`, không mất text, neo `page`); đặt cặp `pdf+json` đúng môn (bỏ tiền tố), auto-suffix `(1)` khi trùng, bỏ file gốc; file lạ/kẹt để yên.
- **`bbox` (optional per-unit)** cho nguồn PDF sau khi spike highlight PASS (docx/pptx để trống).
- Dựng TDD (readers docx/pptx/pdf, legal parser, page-anchor, converter, naming dedup, writer write-before-delete, scan orchestration, CLI); `scripts/register-task.ps1`; smoke thật gate bằng `GULIB_SMOKE_KHO`.
