# Gú's Library — Ghi chú vận hành QA / Prod

*Cập nhật 2026-09-06, trạng thái: app v1.38.0 · worker v0.16.0. **Bản hợp nhất** —
nguồn chân lý duy nhất, phải khớp về cả repo app, repo worker lẫn Obsidian. File này
dành cho huynh (và cả hai CC khi cần dựng lại) — không phải tài liệu cho Gú.*

> **Prod đã có người dùng thật.** Gú đang dùng hằng ngày trên máy của Gú. Mọi thay đổi
> chạm Prod từ đây tính là chạm vào công cụ học của một người thật, không còn là sân tập.

## 1. Nguyên tắc gốc

- App local-first, không backend → **"môi trường" = folder kho nào + cụm Syncthing nào**,
  không phải tầng app. Không có build flavor riêng — cùng một APK chạy cả QA lẫn Prod,
  khác nhau duy nhất ở folder kho được chọn trong Cài đặt.
- App **agnostic tên/ID kho** từ v1.2.1 (badge query theo device, đã xóa hằng số kho cứng).
  Mọi cấu hình môi trường nằm ở Syncthing + worker, không nằm trong code app.
- **Không share chéo** hai kho: máy test không thấy kho Prod, máy Gú không thấy kho QA.

## 2. Sơ đồ hiện trạng

| | QA | Prod |
|---|---|---|
| Folder trên Atomman | `D:\GuLibrary\kho` | `D:\GuLibrary-Prod\kho` |
| Folder-ID Syncthing | `gu-library-kho` | `gu-library-kho-prod` |
| Máy trong cụm | Z Flip 4 · S22 Ultra · Z Fold 3 (máy test) | Galaxy Tab S9 (SM-X710) · S20 FE · Z Flip 6 (máy Gú) |
| Archive nguồn + backup sidecar | sibling ngoài cây sync (`…_archive\`, chi tiết §3) | sibling ngoài cây sync (`…_archive\`, chi tiết §3) |

- Tách ở **cấp cha** (`GuLibrary-Prod\kho`, không phải `kho-prod` cạnh nhau) — cô lập
  `.stversions/`, `_worker.log`, archive; worker trỏ rạch ròi, khó copy nhầm.
- Atomman = anchor node 24/7 (Syncthing chạy dạng Windows service). Android dùng
  Syncthing-Fork (Catfriend1).

## 3. Worker

- **Một tiến trình, quét tuần tự cả 2 kho** (`-KhoRoot` tách phẩy) — nguyên tắc cứng,
  KHÔNG chạy song song để tránh LibreOffice headless khóa profile.
- Scheduled Task `GuLibraryWorker` mỗi 3 phút, chạy `pythonw` (không cửa sổ).
  Task Scheduler tự lo restart sau reboot — không có daemon để chăm.
- Quan sát: `<kho>\_worker.log` (RotatingFileHandler 1MB×3, `_`-prefix nên app bỏ qua,
  `.stignore` giữ local). **Mỗi kho một log riêng**, mỗi dòng gắn nhãn kho
  (`[GuLibrary]` / `[GuLibrary-Prod]`) — soi Prod vs QA không lẫn. Console không hiện
  gì là **bình thường**.
- File nặng (PDF scan jpx/DPI cao) được chuẩn hóa ~0.8s/trang → một quyển lớn có thể
  kéo một vòng quét dài vài phút, kho còn lại trễ tối đa một vòng, tự lành vòng sau.
  PDF có text layer / scan nhẹ sẵn **KHÔNG** bị chuẩn hóa.
- **Ảnh trong `_inbox/` (v0.12.0):** file ảnh (`.jpg/.jpeg/.png/.webp/.gif/.bmp/.tif/.tiff`)
  → **mỗi ảnh thành một PDF 1 trang riêng**, khổ trang = tỉ lệ ảnh (ảnh ngang → trang
  ngang, không ép dọc), **KHÔNG bao giờ gộp** nhiều ảnh. Nhúng lossless (giữ nét); ảnh
  nặng thì tái dùng chuẩn hóa 150dpi như scan. Ảnh gốc = nguồn đã tiêu thụ (pixel đã nằm
  trong PDF, Gú giữ bản trên điện thoại) → **xóa, KHÔNG archive**. Sidecar ảnh hợp lệ
  nhưng rỗng text (`IMAGE_PAGE_MARKER`, không OCR).
- **Khu archive sibling `…\kho_archive\`** (vd `D:\GuLibrary-Prod\kho_archive\`, ngoài
  Syncthing) giữ ba loại nội dung: (a) bản gốc PDF scan nặng trước chuẩn hóa (v0.10.0),
  (b) gốc `.doc`/`.ppt` (OLE cũ) sau khi convert (v0.13.0), (c) `_sidecar_backup/` — bản
  sidecar trước khi `reslide` ghi đè (v0.14.0), (d) `_sidecar_backup_vni/` — bản trước khi
  `vnifix` ghi đè (v0.15.0). Trùng tên → suffix `(n)`, không đè.
  `.docx`/`.pptx` + ảnh **KHÔNG** vào archive; **PDF gốc chỉ vào archive khi bị re-raster**
  (scan nặng, nhánh (a)) — PDF thường thì không. Dọn tay định kỳ nếu đầy đĩa, không có gì
  tự xóa. Thực đo 2026-09-05: QA 12 nguồn OLE + 12 PDF scan; Prod 6 nguồn OLE + 4 PDF scan.
- **`reslide` — dựng lại cấu trúc slide (v0.14.0), chạy TAY, không nằm trong vòng 3 phút:**
  `python -m gu_library_worker.reslide --kho "D:\GuLibrary\kho" --kho "D:\GuLibrary-Prod\kho"`
  → **mặc định DRY-RUN**, chỉ báo; thêm `--apply` mới ghi. Gom các `paragraph` không nhãn
  của sidecar gốc-`.ppt` lại theo `page` thành một unit `slide` mỗi trang. **`page` bê
  nguyên từ unit cũ** — không tính lại, không convert lại PDF; sai bất kỳ điều kiện an
  toàn nào (page vượt `pageCount`, `validate_sidecar` bẩn) thì **bỏ qua, giữ sidecar
  degrade**. Sidecar cũ copy sang `_sidecar_backup/` trước khi ghi. Idempotent — chạy lại
  ra `targets=0`. Ghi log vào `<kho>\_worker.log` như pass thường.
- **Chuẩn hóa text lúc nuốt file — TỰ ĐỘNG, mọi định dạng (v0.16.0).** Worker tự sửa hai
  lỗi làm search không tra được dù chữ nhìn vẫn bình thường: (a) **font cũ VNI-Times**
  (`MIEÃN, GIAÛM` — gõ "miễn giảm" không khớp), (b) **dấu tiếng Việt bị tách rời**
  (`i` + dấu sắc tổ hợp thay vì `í`). Chạy **sau mọi nhánh reader và sau khi neo trang**,
  áp cho `.pdf` / `.docx` / `.pptx` / `.doc` / `.ppt` / ảnh như nhau. *(v0.15.0 chỉ cắm ở
  nhánh `.doc`/`.ppt` nên tài liệu PDF/docx/pptx cùng lỗi vẫn lọt — đã vá ở v0.16.0.)*
  **Không cần nhờ ai sửa tay nữa** với tài liệu thêm mới từ đây.
- **`vnifix` — vá ngược tài liệu ĐÃ nằm trong kho (v0.15.0, mở rộng v0.16.0), chạy TAY,
  ngoài vòng 3 phút:** `python -m gu_library_worker.vnifix --kho "D:\GuLibrary-Prod\kho"`
  → **mặc định DRY-RUN**, thêm `--apply` mới ghi. Làm đúng việc mà pipeline làm lúc nuốt
  file (VNI + NFC), nên chạy sau một lượt nhập sẽ ra `targets=0`. Tên module giữ `vnifix`
  từ v0.15.0 nhưng phạm vi giờ là **chuẩn hóa text nói chung**, không riêng VNI. **Chỉ
  `text` đổi** — `page`, `bbox`, `label`, `path`, metadata bê nguyên, nên neo trang không
  thể xê dịch. Từ chối ghi nếu làm rỗng unit, đổi số từ, đổi danh sách `page`, hoặc
  `validate_sidecar` bẩn. Backup vào `_sidecar_backup_vni/` (**tách khỏi**
  `_sidecar_backup/` của `reslide` — thư mục đó giữ bản trước-khi-gom-slide, không được
  đè). Idempotent.
- **Hai task hạ tầng riêng (v0.11.0 — ĐANG CHẠY, độc lập với `GuLibraryWorker`, chết
  độc lập):** `GuLibraryPrintSync` (mirror `_print/` Prod → `gdrive:GuLibrary/Di-in`
  mỗi ~15 phút) và `GuLibraryBackup` (CN 03:00 — robocopy snapshot → `rclone sync` lên
  `gdrive:GuLibrary/Backup`). Register bằng `scripts\register-ops-tasks.ps1` (Admin).
  Log riêng, **NGOÀI kho**: `D:\GuLibrary-Prod\_print-sync.log` và `_backup.log`. rclone
  cài user-scope (winget), remote tên `gdrive`, config OAuth ở `%APPDATA%\rclone\rclone.conf`.
- **Cảnh báo qua chat (v0.17.0, Zalo Bot — đổi sang Telegram chỉ bằng config):** print-sync
  lỗi liên tục **≥ 2 giờ** → tin `FAILING`, còn lỗi thì nhắc lại mỗi 24 giờ, hết lỗi →
  `RECOVERED`. Backup thì **gửi `OK` sau mỗi lượt Chủ nhật** — đây là nhịp tim: **Chủ nhật
  không thấy tin = có chuyện**, kể cả khi chính kênh cảnh báo đã chết. Config (chứa token,
  **ngoài repo**): `%APPDATA%\GuLibrary\notify.json`; state cạnh log
  (`_print-sync.state.json`, `_backup.state.json`). Setup/test: `scripts\notify-setup.ps1`
  (`-Test` để gửi thử). Cảnh báo hỏng → log `WARN notify failed`, không bao giờ làm task fail.
  **Câu chữ tiếng Việt nằm ở `scripts\notify-messages.json` (v0.18.0), không nằm trong code.**
  Backup xong nhắn "Đã backup xong rồi nha huynh!". Tin lỗi ghi rõ **nguyên nhân + cách xử
  lý + lỗi gốc**, tra theo danh sách `errors` (regex, khớp cái đầu tiên): mất mạng, hết hạn
  đăng nhập Google, Drive đầy, bị giới hạn tốc độ, lệch giờ, thiếu rclone/config, ổ đầy,
  robocopy lỗi. Gặp lỗi lạ (`error_unknown`) → thêm một mục vào `errors`.
  **Giới hạn 7 ngày (nếu có) không làm bot ngừng hoạt động:** chỉ chặn *bot tự nhắn trước*
  khi huynh không nhắn gì cho bot quá 7 ngày. Nhắn bot một tin bất kỳ là khung 7 ngày tính
  lại từ đầu. Phép thử: tin `OK` ngày 11/10/2026 — **không nhắn bot từ 29/09 tới 11/10**
  để phép thử có ý nghĩa.
  *Chưa chứng minh:* Zalo Bot có chặn tin chủ động sau 7 ngày không tương tác như Zalo OA
  hay không. Tài liệu Zalo Bot không nói; tin `OK` Chủ nhật tuần thứ 2 sau setup chính là
  phép thử. Không tới → đổi `provider` sang `telegram`.
- **Cả 3 Scheduled Task chạy principal S4U** (run-whether-logged-on-or-not) → sống lại
  sau reboot **không cần ai logon**, và headless (session 0, không cửa sổ). Đây chính là
  cái làm "reboot tự dậy" ở §4/§6 thành sự thật. Đổi/thêm task phải giữ S4U; các
  register script đã set sẵn.

## 4. Dựng máy mới vào cụm (hoặc dựng lại từ đầu) — 6 bước

1. **Folder:** trên Atomman, tạo (hoặc xác nhận) folder kho đúng cấp cha riêng
   (`D:\GuLibrary\kho` hay `D:\GuLibrary-Prod\kho`).
2. **Syncthing Atomman:** Add Folder với folder-ID đúng bảng trên; kiểm `.stversions`
   (simple versioning) bật — đây là lưới M8.
3. **Máy Android mới:** cài Syncthing-Fork → trao đổi device-ID với Atomman → share
   ĐÚNG MỘT folder (QA hoặc Prod, không bao giờ cả hai) → chờ sync xong lượt đầu.
4. **Worker:** *(Atomman mới — dựng môi trường trước:* cài Python 3.11+ và LibreOffice,
   `git clone` repo worker, `python -m venv .venv` rồi `.venv\Scripts\python -m pip install
   -e .`; soffice auto-detect nên không cần sửa PATH — chi tiết README worker.*)*
   Nếu là kho mới, thêm đường dẫn vào `-KhoRoot` (tách phẩy) của Scheduled
   Task; chạy `scripts\register-task.ps1` (Admin) và **tin vào bước verify của nó** (nó tự
   `Get-ScheduledTask` kiểm trước khi báo thành công — bài học v0.7.9 báo-thành-công-giả).
   **Nếu dựng lại Prod** cần thêm 2 task hạ tầng: cài rclone + `rclone config` (remote
   `gdrive`, OAuth — xem README worker mục "Prod ops") rồi
   `scripts\register-ops-tasks.ps1 -KhoRoot "D:\GuLibrary-Prod\kho" -RcloneRemote "gdrive"` (Admin).
   **Kèm theo: sửa nguồn giờ ngay từ đầu.** Mặc định Windows chỉ có một nguồn giờ
   (`time.windows.com`) và nó hỏng trên Atomman → đồng hồ trôi → rclone sync chết (§6).
   Chạy lệnh `w32tm /config /manualpeerlist:...` ở §6 rồi kiểm bằng `/stripchart`.
5. **App (dựng + cài APK release, làm trên máy Mac):** bump version = sửa **1 chỗ**
   `versionName` trong `package.json` (`versionCode` tĩnh =2 ở build.gradle — không tăng,
   sideload không cần). Dựng: `cd android && ./gradlew assembleRelease` →
   `app/build/outputs/apk/release/Gu-Library-<ver>-release.apk`. Keystore ngoài repo
   `~/keystores/gu-library/gu-library-release.jks`, credential `android/keystore.properties`
   (gitignored). Cài lên máy: release-đè-release **cùng keystore** không mất data;
   release-**đè-debug phải gỡ trước** (khác chữ ký → `install -r` báo lỗi). Rồi Cài đặt →
   Folder kho → chọn đúng folder qua SAF; kiểm badge "Đã đồng bộ" (dựa connected của
   device Atomman, không dựa tên kho).
6. **Smoke:** bỏ 1 file PDF qua đường Share vào một môn → thấy ⏳ → chờ vòng worker →
   thành tài liệu mở được. Thông chuỗi này = môi trường sống.

## 5. Backup & điểm không được mất

- **Keystore `gu-library-release.jks` + `keystore.properties`** = single point of no
  return. Mất là hết đường update app đã cài. Phải có bản ngoài máy Mac
  (cloud/USB/password manager) — kiểm lại định kỳ.
- **Schema sidecar** phải khớp thủ công ở **3 nơi**: repo app, repo worker, và tài liệu
  Obsidian. Không có cơ chế tự đồng bộ. Lệch một nơi = hỏng hợp đồng dữ liệu dài hạn,
  và sidecar là hợp đồng phục vụ cả những feature Phase 2 chưa viết. Sửa schema ở đâu
  thì phải sửa đủ ba, ngay trong cùng session.
  **Bản chốt phía worker: `Docs/gu-library-sidecar-schema.md`;** `validate_sidecar` kiểm
  đúng theo đó, gồm cả `bbox` (optional) và `IMAGE_PAGE_MARKER` cho PDF-ảnh. Nếu doc bên
  app mô tả sidecar, phải khớp đúng hai field này.
- **Kho Prod — chuỗi backup đang chạy (v0.11.0):** hàng tuần robocopy snapshot theo ngày
  vào `D:\GuLibrary-Prod\backup\` (giữ 4 bản gần nhất; snapshot **loại `.stversions`** cho
  gọn — chiều sâu thời gian là các bản-ngày, không phải version-history của Syncthing) →
  xong `rclone sync` folder backup lên Drive `GuLibrary/Backup` (offsite thật, vá ca
  mất-cả-cụm). Lưu ý trung thực: ransomware mã hóa local rồi nhịp sync kế chạy thì bản
  Drive bị đè theo, nhưng Drive trash + version history ~30 ngày vẫn là cửa lùi cuối.
  Mức này chấp nhận đủ.
- **`_print/` (Prod) → Drive `GuLibrary/Di-in`, mirror mỗi ~15 phút** (chính là M9
  mức A, về sớm không cần đụng app/worker): folder Drive luôn = hàng đợi cần in hiện
  tại — Gú tick "Xong" là file rời cả Drive; share link viewer cho người in một lần
  là xong vĩnh viễn.
- `_reading-<deviceId>.json`, `.print.json` sống trong kho nên đi theo backup kho,
  không cần lo riêng.

## 6. Khi có biến — checklist chẩn đoán nhanh

- **App báo "Chưa thấy Atomman":** kiểm Syncthing Atomman đang chạy (service) + máy đó
  connected trong Syncthing UI. Từ v1.2.1 badge chỉ sai khi device thật sự mất kết nối.
- **App (Cài đặt) hiện version cũ sau khi update:** `versionName` được **nướng vào APK
  lúc build** (build.gradle đọc `package.json`), không đọc runtime → cài lại một APK dựng
  *trước* lúc bump sẽ vẫn hiện số cũ dù code mới. Không phải bug: dựng LẠI `assembleRelease`
  sau khi bump rồi cài đè (đã gặp thật v1.16.0→v1.17.0).
- **File kẹt ⏳ lâu:** mở `<kho>\_worker.log`. File đuôi lạ/tmp kẹt lại là *tín hiệu
  dọn tay theo thiết kế*, worker không tự xóa. Segment tiền tố độc → worker route về
  "Chưa phân loại" + WARNING trong log.
- **Ảnh (jpg/jpeg/png/webp) kẹt ⏳ không thành PDF:** app **nhận ảnh từ v1.19.0** (picker
  "Chọn file từ máy" + share từ Gallery), nhưng đóng ảnh→PDF là việc của **worker**. Env
  nào app nhận ảnh thì worker env đó **PHẢI biết xử ảnh TRƯỚC**, không thì ảnh nằm ⏳ vô
  hạn. Thứ tự deploy bắt buộc: worker-image lên Prod trước → verify → rồi mới đẩy app
  v1.19.0 sang máy Gú. (App whitelist đúng jpg/png/webp — HEIC/gif KHÔNG nhận, cố ý.)
- **Thấy folder `_inbox (1)`, `_inbox (2)`… ở gốc kho, hoặc danh sách môn RỖNG dù kho
  đầy:** đã gặp thật (2026-07-13, Flip 4, khi nhập nhiều ảnh liên tiếp). Gốc: `_inbox` bị
  worker/Syncthing xóa+tạo lại giữa loạt import → cache SAF stale → app tạo trùng
  `_inbox (k)`; snapshot cũ coi `_inbox (k)` là môn rồi throw → **môn hiển thị rỗng —
  DATA KHÔNG MẤT** (folder môn còn nguyên trên đĩa). **Đã fix ở app v1.19.0** (ensureDir
  dò cursor tươi + tự lành dedup; snapshot lọc `_`-prefix + try/catch từng môn) → không
  còn tái sinh `_inbox (k)`. Nếu môn vẫn rỗng sau churn cực đoan: DocumentsProvider của
  OS kẹt index tạm thời → **reboot máy** dọn (data còn nguyên). File trong `_inbox (k)`
  mồ côi (máy chưa lên v1.19.0) — worker chỉ quét `_inbox` → **dồn tay về `_inbox` rồi
  xóa folder rác** (giữ nguyên tiền tố `[Môn]`).
- **Sync đứng, thấy file mồ côi `.syncthing.*.tmp`:** đã gặp thật trên Flip 4.
  **Không phải bug app/worker, không có fix code.** Syncthing tự hòa giải sau vài vòng.
  Chỉ theo dõi xem có tái diễn thành mẫu hình lặp lại hay không; nếu chỉ lẻ tẻ thì bỏ qua.
- **Nghi hai kho lẫn nhau:** kiểm từng máy Android chỉ share đúng 1 folder-ID;
  kiểm `-KhoRoot` của task đúng 2 đường dẫn.
- **Atomman vừa reboot:** không phải làm gì — service Syncthing + Scheduled Task (S4U)
  tự dậy. Chỉ kiểm nếu 15 phút sau file vẫn kẹt.
- **Nghi rclone chết:** hai task hạ tầng chết độc lập với worker — worker chạy ngon
  không nói lên rclone còn sống. Kiểm `D:\GuLibrary-Prod\_print-sync.log` / `_backup.log`
  và `Get-ScheduledTask GuLibraryPrintSync,GuLibraryBackup | Get-ScheduledTaskInfo |
  Select State,LastTaskResult` (LastTaskResult `0` = OK). Test auth tay: `rclone lsd gdrive:`.
  Từ v0.17.0 lỗi kéo dài sẽ tự báo qua Zalo (§3). **Không nhận được tin `OK` backup Chủ
  nhật** = kiểm cả kênh cảnh báo: `scripts\notify-setup.ps1 -Test` + tìm `WARN notify` trong log.
- **`_print-sync.log` lặp `ERROR sync failed: ... NOTICE: Time may be set wrong` — file
  nằm trong `_print/` mà không lên Drive:** đã gặp thật (2026-09-21 → 09-26, 6 ngày không
  sync được lần nào). **Đồng hồ Atomman lệch**, không phải lỗi Drive/OAuth — `rclone lsl
  gdrive:` chạy tay vẫn exit 0. Hai lớp chồng nhau:
  1. *Gốc — đồng hồ trôi:* Atomman chậm **~5 phút 44 giây**, trôi ~3 s/ngày. Lần sync
     giờ thành công cuối là **11/06/2026**. `w32time` mặc định chỉ có **một** nguồn
     `time.windows.com,0x9` (poll thưa ~9 tiếng), và nguồn đó hỏng dai dẳng từ máy này:
     Event Log (System, nguồn `Time-Service`) lặp **ID 47** "peer is unreachable" và **ID
     134** "No such host is known" (DNS lúc mạng rớt ban đêm). Không có nguồn dự phòng →
     không sync được lần nào. *Giả thuyết, chưa chứng minh:* `time.windows.com` chỉ có IPv4,
     service gửi từ **cổng nguồn UDP 123**, và nhiều ISP/router chặn cổng này. `w32tm
     /stripchart` (cổng ngẫu nhiên) tới **cùng IP đó vẫn nhận được giờ**, còn service thì
     không. `time.google.com` đi được qua IPv6 nên chạy ngon.
  2. *Khuếch đại — script dừng vì một dòng cảnh báo:* `scripts\sync-print.ps1` đặt
     `$ErrorActionPreference = "Stop"` và gọi `rclone ... 2>&1`. Trên **Windows PowerShell
     5.1**, *bất kỳ* dòng stderr nào (kể cả NOTICE vô hại) cũng thành lỗi dừng script ngay
     → rclone bị cắt trước khi kịp sync. Dấu hiệu nhận biết: dòng ERROR **không có** tiền
     tố `rclone exit N :` (tiền tố này chỉ có khi rclone thất bại thật). **Đã vá ở v0.16.1**
     (cả `sync-print.ps1` lẫn `backup.ps1`): script chỉ phán theo exit code. NOTICE giờ
     hiện thành dòng `WARN rclone: ...` rồi vẫn `sync ok` → **thấy dòng WARN lệch giờ là
     tín hiệu đi chỉnh đồng hồ**, sync không còn chết vì nó.
  **Cách xử (Admin PowerShell):** thêm nguồn giờ dự phòng, bỏ kiểu poll thưa, rồi buộc
  sync ngay:
  `w32tm /config /manualpeerlist:"time.google.com,0x8 time.windows.com,0x8"
  /syncfromflags:manual /update; Restart-Service w32time; w32tm /resync /rediscover`
  (thêm `Set-Service w32time -StartupType Automatic` nếu service đang Stopped/Manual).
  Báo `no time data was available` thì đợi 10–20 giây rồi chạy lại `w32tm /resync
  /rediscover`. Dùng `/resync` trơn ngay sau khi vừa bật service thì chắc chắn gặp lỗi
  này, vì peer chưa được hỏi lần nào. **Kiểm (không cần Admin):** `w32tm /stripchart
  /computer:time.google.com /samples:2 /dataonly` → độ lệch phải cỡ `±00.0xs`; `w32tm
  /query /peers` → `time.google.com` có `Stratum: 1`. Nút "Sync now" trong Settings dùng
  chung service/nguồn này nên cũng hỏng theo khi nguồn hỏng — đừng tin nó để chẩn đoán.

## 7. Mô hình test cuốn chiếu (đã chốt 2026-07-03)

- **Giữ song song dài hạn, QA chạy trước Prod một phase:** vd Phase 2 phát triển/test
  trên QA (3 máy test) trong khi Prod của Gú vẫn ở Phase 1 ổn định. Chỉ khi phase mới
  chín trên QA mới đẩy sang Prod.
- Hệ quả: 3 máy test không gập lại trong tương lai gần.
- **Ràng buộc sống còn (giờ đã có hiệu lực thật):** máy Gú đang chạy Prod hằng ngày →
  **APK thử nghiệm tuyệt đối không sideload sang máy Gú.** Máy Gú chỉ nhận bản đã
  nghiệm thu đủ hai máy test.

## 8. Trạng thái mốc & việc còn treo

- App **v1.38.0** trên main, sạch, chỉ còn nhánh `main` — **tìm kiếm toàn văn** đã merge,
  tag, nghiệm thu trên hai máy test. Search ăn thẳng `units[]` trong sidecar: mỗi đơn vị
  là một kết quả tra được, hiện kèm `label` (vd "Điều 5", "Slide 12") và `page`, chạm là
  mở PDF đúng trang.
- **Hệ quả vận hành của search (quan trọng khi sửa sidecar):** app đọc `units[].text`,
  `label`, `page`, và **cache chỉ mục theo `size` + `lastModified` của file sidecar**.
  Ghi đè sidecar → mọi máy Android đọc lại và dựng lại chỉ mục **riêng file đó** (đúng
  thiết kế). Ghi đè hàng loạt thì máy Gú sẽ có một lượt cập nhật chỉ mục dài — cân nhắc
  chia đợt nếu số file lớn. Loạt v0.14.0–v0.16.0 đụng 19 + 7 + 26 file nên không cần chia.
  **Chất lượng `units[]` giờ nhìn thấy được bằng mắt thường**, không còn là dữ liệu nằm im
  — đây là lý do cả ba beat vừa rồi đều đáng làm.
- Worker **v0.18.0** — hai task rclone đã triển khai và đang chạy; OAuth Drive đã setup.
  v0.16.1 vá lỗi script rclone dừng vì một dòng NOTICE (sự cố lệch giờ 09/2026, §6);
  v0.17.0 thêm cảnh báo qua Zalo Bot (§3), đã setup và nhận tin thử 2026-09-29; v0.18.0 tin tiếng Việt ghi rõ lỗi gì + cách xử.
  **Không còn nợ hạ tầng.** Beat gần đây: ảnh→PDF 1 trang (v0.12.0), archive gốc
  `.doc`/`.ppt` thay vì xóa (v0.13.0), dựng lại cấu trúc slide (v0.14.0),
  chuyển font cũ VNI→Unicode (v0.15.0),
  chuẩn hóa text mọi đường vào (v0.16.0).
- **Nợ Phase 2 "re-extract nguồn `.doc`/`.ppt` đã archive" — ĐÃ TRẢ (v0.14.0), nhưng khác
  cách đặt cọc.** Đo trước khi làm cho ra ba điều không lường:
  1. `.doc` **không** degrade — hai bộ luật `.doc` vẫn parse ra `legal` đủ 1717/912 unit.
     Chỉ `.ppt` (slide) mới hỏng. Phạm vi thật: **19 tài liệu** (QA 7, Prod 12), không
     phải hàng trăm. Tổng số sidecar degrade là 50/178 (QA) và 32/113 (Prod), nhưng phần
     lớn là **PDF gốc dạng văn xuôi** — vốn không có cấu trúc để cứu, không phải nợ này.
  2. Prod có **15 tài liệu gốc-OLE trong kho nhưng chỉ 6 nguồn trong archive** → 9 tài
     liệu mất nguồn (xử lý trước v0.13.0, hồi đó còn xóa gốc). Re-extract từ archive
     không chạm tới được.
  3. Vì vậy chọn cách **gom lại từ chính sidecar** thay vì đọc lại nguồn: `page` bê
     nguyên nên không thể lệch trang, và vá được cả 9 ca mất nguồn. Archive **không cần
     dùng tới**, nhưng vẫn giữ (nguồn OOXML còn giá trị nếu sau này muốn speaker notes).
  Verify: QA áp trước, xong mới tới Prod; kiểm ngược trên chính PDF trong kho —
  **515/515 unit (QA 140, Prod 375) có text nằm đúng trang nó trỏ tới**, không mất chữ,
  `validate_sidecar` sạch, chạy lại ra `targets=0`.
- **Mồ côi trong archive (tín hiệu, KHÔNG xóa):** QA có 2 nguồn đã archive mà không tìm
  thấy cặp `pdf`+`json` tương ứng trong kho — `BÀI GIẢNG LUẬT KINH TẾ-2.ppt` và
  `2022-11-Luat So huu tri tue - HN lan 3-2.doc`. Nhiều khả năng Gú đã xóa/đổi tên tài
  liệu trong kho sau khi worker xử lý. Prod map đủ 6/6.
- **Một sidecar hỏng sẵn ở QA (có từ trước, chưa đụng):** `Chưa phân loại\Giám định pháp
  y, tâm thần.json` thiếu `schemaVersion` + `title` → `validate_sidecar` fail. Có `.pdf`
  đi kèm. Không phải do beat này; cần soi riêng. Prod: 113/113 sidecar hợp lệ.
- **Nợ font cũ VNI-Times — ĐÃ TRẢ (v0.15.0).** Text sidecar ra dạng
  `"CHÖÔNG XV — MIEÃN, GIAÛM"` nên gõ "miễn giảm" không khớp. Thực tế là **6 deck chứ
  không phải 5** — `Bai 11` cũng có 645 ký tự VNI (chỉ ~9% nên chỉ số tỉ-lệ-ký-tự ban đầu
  không bắt được); tất cả nằm trong `Hình sự phần chung\Slide tổ HS\`. Cộng 1 đoạn lẫn
  VNI trong `Ôn thi\GIÁO TRÌNH HSPC` → **7 tài liệu, 224 unit** đã chuyển trên Prod.
  Nguồn `.ppt` trong archive được dùng làm **trọng tài**, không phải nguồn text: convert
  `.ppt`→`.pptx` bằng LibreOffice giữ nguyên tên font `VNI-Times` ở từng run, xác nhận
  chỗ nào VNI chỗ nào Unicode. Text vẫn lấy từ sidecar tại chỗ nên `page` không đổi.
  Verify: `page`/`bbox`/`label`/metadata/số-từ giữ nguyên tuyệt đối 7/7, `validate_sidecar`
  sạch. Còn **20 unit sót ký tự VNI** — mảnh chữ PDF trích ra đã vỡ sẵn (dấu bị tách khỏi
  nguyên âm bởi xuống dòng), không bảng chuyển nào cứu được.
- **Bài học từ v0.15.0 — dữ liệu thật bác hai quy tắc "hiển nhiên đúng", cả hai đều bị
  chặn ở dry-run:** (a) "nguyên âm + dấu" KHÔNG phải bằng chứng VNI — `oà`/`oá` là tiếng
  Việt Unicode bình thường, quy tắc đó biến `Toà án`→`Tồ án`, `hoàn thiện`→`hồn thiện`,
  `Hoàng`→`Hồng` trên 4 tài liệu; (b) ký tự `ö ä ü ñ` cũng KHÔNG phải bằng chứng — kho có
  trích dẫn tiếng Đức/Tây Ban Nha, quy tắc đó biến `öffentliches`→`ưffentliches`,
  `Acuña`→`Acuđa`. Bằng chứng chốt: **dấu riêng của VNI đứng NGAY SAU nguyên âm**. Đây là
  lý do mọi công cụ ghi-đè sidecar phải mặc định DRY-RUN.
- **Dấu tiếng Việt bị TÁCH RỜI — ĐÃ SỬA (v0.16.0).** Lưu là `i` + dấu sắc tổ hợp thay vì
  `í`: nhìn y hệt trên màn hình, nhưng không truy vấn nào khớp được. Đã chuẩn hóa NFC cho
  **26 tài liệu / 2.381 unit** ở Prod. Nặng nhất là các bộ luật —
  `3. HỢP NHẤT_BLHS 2015…` 940/1674 unit, `0. VBHN BLHS 2015` 938/1627,
  `8. TỌA ĐÀM TƯ PHÁP NGƯỜI CTN` 103/1157 — nên đây là món cải thiện tra cứu lớn nhất
  trong cả loạt. Kiểm mẫu xác nhận thay đổi **thuần NFC** (`NFC(cũ) == mới`, đổi do VNI = 0);
  verify 26/26 giữ nguyên `page`/`bbox`/`label`/metadata/số-từ.
- **Lỗ hổng v0.15.0 đã vá:** bản đó chỉ cắm chuẩn hóa ở nhánh `.doc`/`.ppt`, mà 26 tài
  liệu dính lỗi gồm **12 pdf, 8 pptx, 6 docx** — tức phần lớn vẫn lọt, và tài liệu thêm
  mới cũng sẽ lọt. v0.16.0 chuyển thành một lượt chạy sau mọi nhánh reader. Bài học: cắm
  bản vá vào đúng cái nhánh nơi mình *tình cờ tìm thấy* lỗi thì bỏ sót mọi đường vào khác.
- **OCR — số đo mới, mở lại món đã tưởng đóng (2026-09-05).** Con số cũ "1/178 (~0,6%)"
  đã lỗi thời (đo trước v0.12.0, trước khi có ảnh→PDF). Đo lại, tiêu chí: sidecar hợp lệ
  mà **mọi unit đều mang `IMAGE_PAGE_MARKER`**:

  | | Tài liệu | Trang |
  |---|---|---|
  | QA | 13/178 (7,3%) | 844/12.136 (7,0%) |
  | **Prod** | **12/113 (10,6%)** | **680/9.096 (7,5%)** |

  Đối chiếu với lịch sử đọc thật (`_reading-*.json`): Prod **5/12** tài liệu ảnh đã từng
  được mở, và mở gần đây (7/2026) — trong đó `2. Luật sửa đổi BLHS 2025` đọc tới trang
  **38/48**, `GT LUAT HINH SU PHAN CHUNG` 398 trang, `Giám định pháp y, tâm thần` 164
  trang. 7 tài liệu còn lại (6 ảnh báo giấy 1 trang + 1 NQ 6 trang) chưa mở bao giờ.
  Quy mô kỹ thuật: 680 trang, ~1,78 MP/trang, 146,7 MB. **Tesseract chưa cài trên
  Atomman.** *Ước lượng (CHƯA đo, chỉ để cân nhắc): Tesseract `vie` cỡ 1–3 s/trang ở độ
  phân giải này → ~12–35 phút cho một lượt toàn kho Prod, cộng công cài Tesseract +
  traineddata tiếng Việt.* Chưa xây gì — chờ huynh quyết.
- Backlog feature (M10 folder-level, breadcrumb bấm-nhảy-tầng, nav chữ-bên-icon) đang
  **đóng băng có chủ ý**: Gú đang dùng thật, chưa phát sinh feedback. Không mở beat mới
  cho tới khi có vấn đề quan sát được từ người dùng thật — không suy diễn nhu cầu.
