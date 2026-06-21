# Gú's Library — Design Spec

- **Tên hiển thị:** Gú's Library
- **Tên kỹ thuật (repo / applicationId base):** `gu-library`
- **Ngày:** 16/06/2026
- **Trạng thái:** Design đã chốt qua brainstorm, sẵn sàng chuyển sang `writing-plans`.

---

## 1. Tổng quan

### 1.1 Mục đích
App Android lưu trữ tập trung và xem tài liệu học luật cho **một người dùng duy nhất (Gú)**, dùng trên **3 thiết bị** (2 điện thoại Android + 1 Galaxy tablet), dữ liệu đồng bộ giữa cả ba. Tài liệu gồm slide bài giảng (PPTX/PDF) và văn bản luật (Word). Triết lý xuyên suốt: **local-first** và **ít thao tác nhất có thể** (người dùng không phải dev).

### 1.2 Người dùng & bối cảnh
- Một người dùng (Gú), tại một thời điểm chỉ dùng một thiết bị → **không có chỉnh sửa song song**, rủi ro xung đột sync gần như bằng 0.
- Gần như 100% thời gian các thiết bị cùng một mạng WiFi nhà. "Về nhà tự sync" được chấp nhận — không cần sync tức thời khi ra ngoài.
- Có sẵn 1 mini PC chạy 24/7 làm hạ tầng.

### 1.3 Nguyên tắc cốt lõi
1. **Local-first:** mỗi thiết bị giữ bản đầy đủ, đọc được offline, mở app là có ngay.
2. **File-based, không DB tập trung:** dữ liệu là nhiều file nhỏ, sync khỏe, mở bằng file manager vẫn hiểu được.
3. **Tách "định dạng để xem" khỏi "nguồn để hiểu":** PDF cho hiển thị, sidecar JSON cho tìm kiếm/cross-link.
4. **Index là dữ liệu phái sinh:** không sync, mỗi máy tự dựng lại từ file gốc.
5. **Mini PC là trung tâm xử lý nặng:** node neo đồng bộ + xưởng convert/extract + (sau này) auto-download. Điện thoại chỉ làm việc nhẹ.

---

## 2. Đóng gói & nền tảng

- App đóng gói bằng **Capacitor** (web app React/Vite bọc WebView native), build hoàn toàn bằng CLI (Android SDK command-line tools + Gradle + JDK), **không cần Android Studio**.
- Lý do chọn Capacitor: tận dụng stack JS/TS sẵn có, không học ngôn ngữ mới, đủ trưởng thành, gọi được tính năng máy (Share Intent, truy cập thư mục), chạy offline.
- **UI framework: Ionic + React** — cho sẵn component mobile (tab bar, chuyển trang, gesture, safe-area), trông native, giảm lượng visual design phải tự dựng. Theme bằng CSS variables (dễ áp palette ở mục 9.3). Dark mode để Ionic auto theo hệ thống (làm sau, không cản MVP).
- **Android scoped storage** là điểm cần xử lý cẩn thận: app cần xin đúng quyền truy cập thư mục kho (folder do Syncthing đồng bộ).

---

## 3. Đồng bộ (Sync) — *đã chốt*

### 3.1 Cơ chế
- **Syncthing** chạy ngầm trên cả 3 thiết bị + mini PC, đồng bộ folder kho.
  - **Android (2 điện thoại + tablet):** **Syncthing-Fork (Catfriend1)** — app Syncthing Android chính thức đã ngừng phát triển (bản cuối 12/2024); fork là bản còn maintain. Cần cho phép chạy nền (tắt battery optimization) kẻo bị Android kill.
  - **Mini PC (Windows, 24/7):** Syncthing chạy như **Windows service** (vd qua installer Bill Stewart), KHÔNG dùng SyncTrayzor — service mới sync được cả khi chưa ai đăng nhập.
  - Cả hai đều là **Syncthing v2** (đổi cấu trúc DB/config so với v1, có một lần migration). REST API code theo v2 thật trên instance đang chạy.
- **Mini PC là node neo 24/7:** giải bài toán hai điện thoại không bao giờ bật cùng lúc — chúng đồng bộ gián tiếp qua con neo.
- App chỉ đọc/ghi folder kho; **không tự viết logic sync**.
- **Setup Syncthing (cài + ghép cặp + share folder kho + versioning) là việc TAY làm ngoài app** — xem hướng dẫn `gu-library-syncthing-setup.md`. Là **tiền đề để nghiệm thu M3**.

### 3.2 Đèn trạng thái đồng bộ
App đọc API trạng thái của Syncthing và hiển thị **góc phải header**. Mốc an toàn là **"máy này đã đẩy hết lên mini PC chưa"** (KHÔNG cố báo "cả 3 máy đã giống nhau chưa" — không trả lời thành thật được vì máy kia có thể đang tắt). Ba trạng thái:

| Trạng thái | Ý nghĩa | Điều kiện |
|---|---|---|
| ✓ Đã đồng bộ | An toàn đổi máy | Không còn file chờ + thấy mini PC |
| ⟳ Đang đẩy… | Đợi chút | Còn file đang truyền lên mini PC |
| ⚠ Chưa thấy mini PC | Data còn kẹt ở máy này, về nhà mới đẩy được | Ngoài mạng / mini PC tắt |

- Không có nút "Sync now" để ra lệnh (Syncthing luôn tự chạy ngầm) — đèn chỉ để *yên tâm*, không phải để *ra lệnh*.

**Cách app đọc trạng thái (đã chốt):**
- App đọc REST API của Syncthing chạy trên **chính máy đó** — đèn báo "máy NÀY đã đẩy hết chưa" nên hỏi instance local, không phải instance mini PC.
- **Cách gọi (as-built M3):** GUI Syncthing v2 chạy **HTTPS + cert tự ký**, redirect HTTP→307. Nên app gọi `https://localhost:8384` qua **native plugin riêng (SyncthingPlugin) trust cert self-signed localhost-only** — KHÔNG dùng CapacitorHttp/`fetch` (không qua được self-signed cert ở tầng JS, lại dính CORS/mixed-content). Trust cert phải làm ở tầng native.
- **API key:** nhập tay một lần vào Settings của Gú's Library trên *mỗi* máy (key riêng từng máy), lưu qua Preferences. Không tự đọc `config.xml` của Syncthing.
- **Đâu là mini PC:** app gọi REST liệt kê devices → người dùng chọn "đây là mini PC" một lần, lưu Preferences.
- **Map điều kiện (field v2 thật):** "thấy mini PC" = `/rest/system/connections` báo device mini PC connected (v2 có primary/secondary — chỉ đọc `connected`); "đã đẩy hết" = `/rest/db/completion?folder=<id kho>&device=<minipc>` đạt 100% (`completion` là number). Poll định kỳ (~10s) đủ cho MVP, không cần event API.

---

## 4. Mô hình dữ liệu — *đã chốt*

### 4.1 Cấu trúc kho
- **Folder = môn học**, cấp 1 là "môn" (folder name chính là tên hiển thị; `_mon.json` giữ màu + thứ tự — xem 4.1b). **Lồng tự do** bên dưới (Môn → Chương → Buổi → … tùy môn).
- Metadata **phân tán**, không có file manifest trung tâm (tránh file bị tranh chấp khi sync).
- Phần điều hướng phải xử lý **độ sâu bất kỳ** (breadcrumb Môn ▸ Chương ▸ …), không hardcode số tầng.

```
kho/
  _inbox/                         # file gốc chờ mini PC xử lý (đường VÀO)
  _print/                         # bộ tài liệu gom để đi in (đường RA, xem 5b)
  Luật Công chứng/
    _mon.json                     # metadata môn: tên hiển thị, màu, thứ tự
    luat-cong-chung-2024.pdf      # bản để XEM
    luat-cong-chung-2024.json     # sidecar: text + cấu trúc + vị trí
    Chương 1/
      slide-buoi-1.pdf
      slide-buoi-1.json
  Tố tụng Hình sự/
    ...
```

### 4.1b Schema `_mon.json` — *đã chốt (option A)*
- **Tên hiển thị = chính folder name** (vd folder `Tố tụng Hình sự/` → hiển thị "Tố tụng Hình sự"). Không tách slug ASCII; giữ đúng triết lý "mở bằng file manager vẫn hiểu được". Android shared storage + Syncthing xử lý tên Unicode (UTF-8) tốt.
- **`_mon.json` chỉ giữ phần filesystem không diễn đạt được:** `color` (màu nhấn của môn) và `order` (thứ tự sắp xếp thủ công giữa các môn). Cả hai **tùy chọn** — thiếu thì app dùng mặc định (màu palette + sắp theo alphabet).
- `_mon.json` **chỉ đặt ở cấp môn (cấp 1)**, không rải ở thư mục con — folder con chỉ là điều hướng (Chương/Buổi), không mang metadata riêng.
- Trường này M2 *đọc*, M4 *hiển thị* — cùng một schema, là nguồn sự thật chung. Mở rộng thêm trường sau này được, nhưng giữ YAGNI ở Phase 1.

### 4.2 Mỗi tài liệu = cặp PDF + sidecar JSON
- **PDF:** bản canonical để xem (Viewer chỉ cần giỏi một việc: render PDF + nhảy trang).
- **Sidecar JSON (đi cùng tên):** chứa dữ liệu để *hiểu*, gồm:
  - Text đầy đủ (đã rút khi import).
  - **Cấu trúc Điều/Khoản/Điểm** (ranh giới + nhãn) — dành cho cross-link tới Điều.
  - **Vị trí gốc:** mỗi đoạn/Điều neo về trang số mấy trong PDF.
  - Metadata tài liệu: tên hiển thị, nguồn, ngày thêm, trạng thái xử lý.

### 4.3 Index tìm kiếm
- Là **dữ liệu phái sinh, KHÔNG sync.** Mỗi máy tự build index local từ các sidecar JSON nó nhận được.
- Hỏng/lệch thì xóa build lại; hai máy không bao giờ conflict vì không chia sẻ index.

### 4.4 Trạng thái "chờ xử lý"
- File gốc đã vào kho (qua Share khi ở ngoài) nhưng **chưa qua mini PC → chưa có PDF + sidecar**.
- App đánh dấu trạng thái ⏳: ở cấp môn (badge) và cấp tài liệu (file mờ, có nhãn, chưa bấm xem được).
- Tự hoàn tất khi về mạng và mini PC xử lý xong.

---

## 5. Đường nhập liệu (Import) — *đã chốt*

### 5.1 Đường chính: Share Intent
- Từ trình duyệt / Files sau khi tải file → **Share → Gú's Library** → app bật **sheet trượt lên** (không mở màn riêng — ít thao tác) hỏi **chọn môn ngay** (gợi ý môn vừa dùng) + nút "Chưa phân loại" làm lối thoát nhanh.
- File gốc rơi vào `_inbox/`, **tên gắn tiền tố môn đích** (vd `[Tố tụng Hình sự] file.pdf`; "Chưa phân loại" → tiền tố `[Chưa phân loại]`) → Syncthing đẩy lên mini PC.
- **Tiền tố môn là interface M6↔M7:** app chỉ biết môn đích lúc Gú chọn ở sheet, nhưng mini PC (M7) mới là nơi đặt cặp PDF+JSON vào đúng môn sau convert. Tiền tố tải môn đích kèm file qua `_inbox/` để M7 đọc — KHÔNG đẻ file phụ, tái dùng đúng cơ chế đặt tên của `_print/` (mục 5b).

### 5.1b Share nhiều file một lúc — *as-built v0.6.3*
- Share **một lô nhiều file** (kể cả trộn PDF/Word/PPTX) cũng vào được app. Android coi share ≥2 file là `ACTION_SEND_MULTIPLE` (khác `ACTION_SEND` của 1 file) → manifest phải khai báo **cả hai**, thiếu `SEND_MULTIPLE` thì app biến mất khỏi share sheet khi chọn nhiều file.
- **Một lô = một môn (đã chốt):** sheet trượt lên hỏi **một** môn → áp tiền tố đó cho **toàn bộ** file trong lô. KHÔNG chọn môn riêng từng file (giữ sheet "một câu hỏi", đúng tinh thần ít chạm). Lô lẫn nhiều môn → Gú share nhiều lần theo môn; hoặc quăng cả lô vào "Chưa phân loại" rồi phân loại sau (Phase 2).
- Mỗi file vào `_inbox/` thành một entry độc lập, tiền tố môn giống nhau; trùng tên gốc trong lô → app tự thêm `(1)` để không đè (đối xứng cơ chế trùng tên của M7, mục 5.4).
- *(Lý do thiết kế: thói quen thật là gom tài liệu theo môn rồi nạp một lượt; lô đa môn là ca hiếm, không đáng phình sheet thành form N dòng.)*

### 5.2 Đường phụ: Watch folder
- Lúc ngồi máy tính: copy file thẳng vào `_inbox/` → mini PC tự nuốt.

### 5.3 Đường dự phòng: nút "+" trong app
- Mở app → Thêm → file picker → chọn môn. Không phải đường mặc định.

### 5.4 Xử lý ở mini PC (xưởng convert + extract) — *worker M7, đã chốt thiết kế*

Worker là **script Python** (PyMuPDF cho PDF kèm toạ độ text, python-docx, python-pptx — hệ parse tài liệu mạnh hơn Node; worker là tiến trình riêng trên mini PC, không chia code với app nên "cùng ngôn ngữ app" không phải lợi thế). **Không nằm trong app.**

**Cơ chế chạy (polling, không daemon):** Scheduled Task của Windows chạy worker **mỗi vài phút**, mỗi lần quét một vòng `_inbox/` rồi thoát. KHÔNG dùng watcher thường trú/fs-event.
- *Lý do:* mô hình "về nhà tự sync" vốn không cần realtime (spec 1.2); Task Scheduler tự lo restart sau reboot/crash → độ bền lấy gần như miễn phí, ít cơ-phận-để-hỏng hơn daemon; polling nhìn trạng thái tĩnh nên né được tràng fs-event nhiễu của folder Syncthing.
- **Stateless:** worker KHÔNG giữ sổ "đã xử file nào". Trạng thái derive thẳng từ filesystem — file gốc **còn** trong `_inbox/` = chưa xử xong; xử xong thì worker đã move cặp pdf+json ra môn + bỏ gốc → `_inbox/` tự sạch. Không có state để lệch/hỏng (hợp tư duy file-based, spec mục 4).

**Cổng lọc đầu vào (chặn cửa trước khi đụng file):** chỉ xử file đuôi ∈ {pdf, doc, docx, ppt, pptx}.
- **Stability check:** trước khi đụng bất kỳ file nào, chờ kích thước **đứng yên qua 2 lần kiểm** (cách nhau vài giây) → chắc Syncthing/trình duyệt đã ghi xong. Đây là lưới bắt ca nguy hiểm nhất: file `.pdf` mà Syncthing **đang ghi dở** trông như PDF hợp lệ, worker nuốt vào extract ra text cụt → sidecar sai âm thầm.
- **Đuôi tạm bỏ thẳng:** `.tmp`, `.crdownload`, `.syncthing.*.tmp` (tên-đang-ghi, không phải đích). Đuôi lạ hẳn (`.txt`, `.zip`, ảnh) và file ẩn/hệ thống → lờ.
- **File kẹt KHÔNG tự xóa:** file đuôi-lạ/tmp tồn lại trong `_inbox/`, app vẫn hiện ⏳ → *đó là tín hiệu cho Gú vào dọn tay*. Worker không tự dọn (xóa là việc nhạy, spec 10).

**Với mỗi file hợp lệ:**
0. **Đọc tiền tố môn** từ tên file (`[<môn>] ...`); tiền tố `[Chưa phân loại]` → khu chưa phân loại.
1. **Convert sang PDF** bằng LibreOffice headless. **PDF gốc giữ nguyên (không convert);** PPTX/Word → PDF.
2. **Extract sidecar** theo `gu-library-sidecar-schema.md` (text + cấu trúc Điều/Khoản + neo trang). Extract từ *file gốc* khi gốc là Word/PPTX (cấu trúc sạch hơn PDF); **khi gốc đã là PDF thì extract thẳng trên PDF** — đây là ca khó nhất cho parse cấu trúc, degrade sạch về `paragraph` nếu hụt Điều/Khoản, không bao giờ mất text.
3. Đặt cặp `.pdf` + `.json` vào **đúng môn (từ tiền tố)**, bỏ tiền tố khỏi tên cuối, **bỏ file gốc**.
4. Syncthing rải về 3 máy.

**Trùng tên đích trong cùng môn:** nếu sau khi bỏ tiền tố, tên đã tồn tại trong folder môn → worker **tự thêm hậu tố `(1)`** cho **cả cặp** (`tên (1).pdf` + `tên (1).json`, không lệch). KHÔNG ghi đè (mất dữ liệu âm thầm — spec 10), KHÔNG để kẹt câm lặng. Đối xứng cơ chế `(1)` của app ở `_inbox/` (mục 5.1b). Bản trùng dư là "rác thấy được", Gú dọn sau bằng Quản lý kho (M10). Kiểm trùng phải tính cả file đang chờ trong cùng nhịp quét.

> **Đánh đổi đã chấp nhận:** import "xịn" cần đi qua mini PC. Ở ngoài thì file gốc vào trạng thái ⏳, convert khi về nhà.

---

## 5b. Đường ra — đi in (Print outbox) — *đã chốt, C ở Phase 1*

**Vấn đề gốc:** quy trình cũ là copy thủ công từng file vào một folder Drive tên "in", share folder đó cho người thứ ba in giùm. Lỗi nằm ở khâu **chọn đúng file + copy tay từng cái mỗi kỳ thi** (dễ sót, dễ nhầm), không phải khâu in.

**Nguyên tắc:** đường ra **đối xứng đường vào** — `_inbox/` là đường file đi *vào* kho, `_print/` là đường file đi *ra* để in. App lo đúng khâu dễ sai (chọn + đặt tên + chống trùng); người chỉ còn một thao tác bulk.

**Luồng (C — MVP):**
1. Đang đọc/duyệt, Gú đánh dấu **"cần in"** ở từng tài liệu (tick rải rác theo thời gian, kể cả trên điện thoại lúc ôn).
2. Khi gom: app copy tất cả tài liệu "cần in" vào `_print/` trong kho, **đặt tên có tiền tố môn** để chống trùng (vd `[Tố tụng Hình sự] slide-buoi-1.pdf`). Bản gốc trong môn **giữ nguyên** (in lại kỳ sau).
3. Gú (ở PC có sync kho) **kéo nguyên folder `_print/` thả vào folder Drive "in"** — một thao tác bulk, folder đã đúng sẵn.
4. Người thứ ba in từ Drive **như cũ, không đổi gì**.
5. Nhận bản in về → Gú tick **"xong"** → app dọn file khỏi `_print/` và clear cờ "cần in".

**Trạng thái (2 mốc có nghĩa thật):**

| Trạng thái | Nguồn sự thật | Ghi chú |
|---|---|---|
| **Cần in** | Ý định người dùng — app-owned, **có sync** | Tick lúc đọc; tách hẳn khỏi sidecar |
| **Đã gửi đi in** | **Suy ra từ filesystem** — file đã có trong `_print/` | Không lưu state riêng |

- KHÔNG có trạng thái "đang in": việc in xảy ra ngoài app (người khác in), app không quan sát được → tránh trạng thái kẹt mãi.
- "Xong" là hành động dọn thủ công, không phải mốc app tự đoán.

**Ràng buộc đã chốt:**
- Cờ "cần in" là ý định người dùng → **phải sync** nhưng **KHÔNG ghi vào sidecar JSON** (sidecar do mini PC sở hữu/sinh; app + worker cùng ghi một file là đúng cảnh báo mục 14.4). Lưu dạng metadata app-owned **per-file** (không file hàng đợi tập trung) — đúng triết lý "nhiều file nhỏ, không file bị nhiều máy tranh ghi".
- Gom = **copy**, không move (giữ bản gốc trong môn).
- Tên trong `_print/` phải gắn tiền tố môn để chống trùng giữa các môn.
- `_print/` được Syncthing sync ra cả 3 máy + mini PC → nhân bản tạm; **kỷ luật dọn sau khi in** (versioning mục 10 đỡ lỡ tay).

**Đường nâng cấp (A — Phase 3, không đập lại C):** mini PC watch `_print/` (y như watch `_inbox/`) và tự đẩy lên folder Drive "in" bằng rclone/Drive API. Lúc đó bước 3 (kéo tay) biến mất, thành no-touch. Cùng một folder outbox, chỉ thêm chân Drive cho mini PC. Việc mini PC nói chuyện Drive vốn đã thuộc Phase 3 (off-site backup) — chân Drive cho outbox đi in **gộp chung** vào năng lực Drive đó, không phát sinh hạ tầng mới.

---

## 6. Xem tài liệu (Viewer)

- Chỉ render **PDF + nhảy tới trang cụ thể + highlight đoạn**. Slide PPTX đã thành PDF nên đồng nhất một đường xem.
- **Điểm cần thử nghiệm (không phải code một phát ăn ngay):** highlight đúng đoạn khi nhảy tới — phải vẽ overlay lên đúng vị trí text trong PDF.

---

## 7. Tìm kiếm (Full-text search) — *đã chốt, Phase 2*

- **Passage-level:** gõ từ khóa → hiện đoạn trích kèm vị trí (Điều/trang/slide) → bấm **nhảy thẳng tới đúng chỗ**, highlight.
- Chạy **hoàn toàn local** (không OCR vì slide gần 100% là text PPTX/PDF, không phải ảnh) → không cần server, không cần mạng.
- Ăn từ **sidecar JSON** qua một **lớp rút text thống nhất**: bất kể nguồn (PDF/PPTX/Word) đều nhả ra cùng dạng (plain text + vị trí). Thêm format mới sau này chỉ cắm thêm "đầu đọc", phần còn lại không đụng.
- Index per-máy, derived, không sync (xem 4.3).

---

## 8. Cross-link văn bản luật — *đã chốt (tới Điều), Phase 2*

- Bấm tham chiếu ("Điều 5", "khoản 2 Điều 5", "Nghị định 23/2015/NĐ-CP") → **nhảy tới đúng Điều**, highlight.
- Bản chất là **passage-jump** giống search, chỉ khác nguồn kích hoạt → tái dùng cùng hạ tầng, không xây mới.
- Phát hiện tham chiếu bằng **pattern thuần** (format luật VN rất quy luật) → chạy local, offline, **không cần LLM/API**.
- "Tới Điều" gần như miễn phí vì sidecar đã chứa cấu trúc Điều/Khoản (parse một lần lúc import).
- Reference trỏ tới văn bản **chưa có trong kho** → link "treo" kiểu unresolved wikilink (hiện xám), nối với nút tải từ **vbpl.vn** (KHÔNG phải thuvienphapluat).

---

## 9. UX shell — *đã chốt*

### 9.1 Màn hình chính: Home lai
Thứ tự trên màn:
1. Header: tên + đèn trạng thái đồng bộ (góc phải).
2. Ô search (lối tắt gõ nhanh).
3. **"Đang đọc dở"** — card tài liệu đang đọc + tiến độ trang (0 chạm để đọc tiếp). Điểm nhấn trên cùng vì đây là hành vi số một của người học.
4. Danh sách môn (số tài liệu, badge ⏳ nếu có file chờ xử lý).
5. Thanh điều hướng dưới: Trang chủ / Tìm / Thêm / Cài đặt.

### 9.2 Phân vai search
- Ô trên Home = lối tắt gõ nhanh.
- Tab "Tìm" = trang tìm đầy đủ (lọc theo môn, lịch sử tra cứu, kết quả passage-level dài). Hai vai khác nhau, không trùng.

### 9.3 Design direction (UI) — *đã chốt*

**Tông: "nâu giấy"** (Gú chọn) — ấm, gợi sách giấy, dịu mắt khi đọc lâu.

- **Palette gốc:** nền kem `#E9E5CD`, nhấn nâu `#75420E`, nhấn đậm `#553B08`, xám phụ `#AAAAAA`, trắng `#FFFFFF`. (Sắc độ sáng hơn `#FBF7F0`, `#FFFDF8` dùng cho nền/card.)
- **Cặp font:** sans (vd **Montserrat**) cho giao diện; **serif (vd Merriweather)** cho phần *nội dung đọc* (văn bản luật) và tiêu đề — serif đọc đỡ mỏi mắt khi đọc dài.
- **Nguồn cảm hứng (north star):** bộ "Goodreads Mobile Redesign" (Figma community). Lấy *hướng thẩm mỹ*, **không bê logo/branding** — Gú's Library giữ bản sắc riêng.

**Lấy từ cảm hứng (phần thẩm mỹ):** bảng màu nâu giấy; cặp font sans/serif; card "đang đọc dở" kiểu Currently Reading (cover + tiến độ + progress bar); search bar bo tròn ở đầu; bottom nav; layout màn Cài đặt (nhóm dày + ô tìm setting).

**KHÔNG lấy (phần xã hội — Gú không có):** Home kiểu feed (Latest Reviews / Trending / Discussion); Profile với Friends/Following/Clubs; Notifications xã hội; Reviews/Ratings sao; kệ xếp theo trạng thái đọc (Want to Read / Read) — Gú xếp theo **môn**, không theo trạng thái.

### 9.4 Layout Home chi tiết — *đã chốt qua mockup*

Năm khối dọc (trên → dưới):

1. **Header:** tên "Gú's Library" (serif, đậm, nâu đậm `#553B08`) bên trái; **đèn sync dạng pill có CHỮ** bên phải (không chỉ chấm màu) — icon + nhãn đọc được: ✓ "Đã đồng bộ" (xanh trầm), ⟳ "Đang đẩy…" (nâu/amber), ⚠ "Chưa thấy mini PC" (đỏ trầm). Đổi cả màu + chữ theo trạng thái.
2. **Ô search:** input giả bo tròn (pill), icon kính lúp + placeholder "Tìm trong tài liệu…". Lối tắt gõ nhanh (mục 9.2).
3. **"Đang đọc dở":** **MỘT card lớn duy nhất** (tài liệu chạm gần nhất), nền nâu đậm để nổi. Gồm: khối cover/icon trái, tên tài liệu (serif), tên môn, progress bar + "Trang X / Y · chạm để đọc tiếp". Bấm card = mở đúng tài liệu ở đúng trang dừng (0 chạm phụ). *(Nhiều card cuộn ngang để dành nếu sau này cần — MVP một card.)*
4. **"Môn học":** **list 1 cột** (không lưới — tên môn luật dài, lưới cắt chữ). Mỗi môn một card: **swatch màu vuông** (lấy `color` từ `_mon.json`, default palette nếu thiếu) chứa chữ cái đầu môn; tên môn (serif); số tài liệu; **badge ⏳ pill "N chờ"** (cam đất) nếu có tài liệu chờ xử lý; chevron phải.
5. **Bottom nav:** Trang chủ / Tìm / Thêm / Cài đặt (icon + nhãn); mục active màu nâu, còn lại xám.

**Font (theo 9.3):** Merriweather (serif) cho tên tài liệu/môn + tiêu đề; Montserrat (sans) cho phần UI còn lại.

**Empty states (đề xuất, CC làm theo trừ khi đổi):**
- *Chưa đọc tài liệu nào:* ẩn hẳn khối "Đang đọc dở" (gọn hơn placeholder rỗng).
- *Kho rỗng / chưa cấp quyền folder:* màn Home hiện hướng dẫn ngắn dẫn vào Cài đặt để chọn folder kho (SAF) — vì chưa cấp quyền thì không có gì để liệt kê.

---

## 10. Backup — *đã chốt*

- **Rủi ro thật không phải hỏng ổ** (đã có 4 bản: 3 thiết bị + mini PC), mà là **xóa nhầm lan truyền** — Syncthing sync cả lệnh xóa ra mọi máy.
- **Bắt buộc:** bật **versioning của Syncthing trên mini PC** (giữ bản cũ file bị xóa/sửa, vd 30 ngày) → moi lại được khi lỡ tay.
- **Tùy chọn (Phase 3):** mini PC đẩy snapshot lên Google Drive định kỳ cho bản off-site.
- Kho là folder thuần → bản thân đã là "backup tự nhiên", copy đi đâu cũng sống.

---

## 11. Auto-download — *đã chốt phạm vi, Phase 3*

Hai nguồn thuộc hai thế giới khác hẳn, KHÔNG gộp:

| Nguồn | Quyết định | Lý do |
|---|---|---|
| **elearning HCMULAW (Moodle)** | **Làm** — dùng Moodle Web Services API với token của Gú | Tài liệu của chính người dùng, đường chính thống, ổn định hơn scrape. Điều kiện: trường bật Web Services; nếu tắt → lùi về tải thủ công + Share. |
| **Văn bản luật** | Kéo từ **nguồn công khai (vbpl.vn, Công báo)** | Văn bản quy phạm pháp luật không thuộc đối tượng bảo hộ quyền tác giả → nguồn mở sạch hoàn toàn. |
| **thuvienphapluat** | **KHÔNG auto-scrape** | Dịch vụ trả phí, có anti-bot, ToS cấm tải tự động. Nếu cần văn bản đó: lấy từ nguồn công khai hoặc tải thủ công rồi Share vào. |

---

## 12. Ranh giới module (để dễ test & bảo trì)

- **Storage layer** — đọc/ghi folder kho, hiểu cấu trúc môn/lồng, đọc metadata phân tán.
- **Sync status reader** — đọc API Syncthing → 3 trạng thái đèn.
- **Text-extraction layer** (ở mini PC) — nhiều "đầu đọc" (PDF/PPTX/Word) → một output chuẩn (text + cấu trúc + vị trí). Điểm mở rộng cho format mới.
- **Converter** (ở mini PC) — LibreOffice headless, mọi thứ → PDF.
- **Index builder** (per-máy) — sidecar JSON → index search local.
- **Search/cross-link engine** — passage-level, pattern phát hiện tham chiếu.
- **Viewer** — render PDF + nhảy trang + highlight.
- **UI shell** — Home lai, điều hướng độ sâu bất kỳ, Share Intent handler.
- **Print outbox** — đánh dấu "cần in" (app-owned per-file, có sync), gom → `_print/` đặt tên có tiền tố môn, dọn khi xong (mục 5b).
- **Quản lý kho (M10, Phase 2)** — app sửa cây kho trong folder môn: **đổi tên** (rename cặp pdf+json), **chuyển môn** (move cặp sang folder khác), **xóa** tài liệu. Tất cả là năng lực app *ghi vào folder môn* — vùng app chưa từng đụng ở Phase 1 (M6 ghi `_inbox/`, M9 ghi `_print/`).

---

## 13. Lộ trình build (phân phase)

### Phase 1 — MVP: kho dùng được trên 3 máy
Data model (folder=môn, lồng tự do, PDF + sidecar) · Sync (Syncthing + mini PC neo + đèn trạng thái) · Import (Share → mini PC convert + extract) · Viewer (PDF, nhảy trang) · Home lai · Backup versioning · Print outbox mức C (gom `_print/`, kéo Drive tay — mục 5b).
→ Hết Phase 1 đã là app dùng được: thêm tài liệu, đồng bộ, xem.

### Phase 2 — Lớp tri thức (chỗ app khác biệt)
Full-text search (passage-level, index derived) · Cross-link tới đúng Điều · **Quản lý kho (M10):** đổi tên / chuyển môn / xóa tài liệu.

> **Quản lý kho (M10) — đã chốt thiết kế dữ liệu (hiện thực hóa ở Phase 2):**
> - **Đổi tên KHÔNG đụng nội dung sidecar.** App hiển thị tên tài liệu theo **tên file** (basename), không đọc `title` trong sidecar → rename = đổi tên **cặp** `.pdf` + `.json` cho khớp (lệch một cái là vỡ "cùng basename = một tài liệu"). Không ghi *nội dung* sidecar do worker sở hữu → KHÔNG chạm cảnh báo mục 14.4. (Hệ quả: `title` trong sidecar sẽ lệch tên file sau rename; Phase 1 vô hại vì không ai đọc `title`. Khi thiết kế M10 quyết: lờ luôn, hay bỏ `title` khỏi schema.)
> - **Chuyển môn = move cặp file sang folder môn khác. Zero đụng JSON** — môn là folder name, sidecar không lưu môn (mục 4.1b), nên đổi folder = đổi môn tự động, không trường nào cần sửa. Rẻ nhất trong ba.
> - **Xóa** đụng đúng rủi ro mục 10 (xóa nhầm lan truyền qua Syncthing) → thiết kế chung cơ chế "app ghi/xóa trong folder môn" cùng rename/move một lượt.
> - Cả ba chia chung MỘT spike chưa làm: *app ghi được vào folder môn chưa* (M2 spike đọc; M6/M9 spike ghi `_inbox/`+`_print/`, chưa cái nào ghi folder môn).

### Phase 3 — Tự động hóa nhập liệu
Auto-download elearning (Moodle API) · Nguồn luật công khai (vbpl.vn) · Off-site backup (Drive) · Print outbox mức A (mini PC tự đẩy `_print/` lên Drive — gộp vào năng lực Drive).

> **Sợi chỉ xuyên suốt — quan trọng nhất khi bắt tay:** dù Search & Cross-link ở Phase 2, **Data model + sidecar ở Phase 1 phải chứa sẵn text + cấu trúc Điều/Khoản + vị trí trang ngay từ đầu.** Nếu không, Phase 2 phải đập sidecar xây lại + convert lại cả kho.

---

## 14. Rủi ro & điểm cần lưu ý khi triển khai

1. **Highlight passage trên PDF** — cần thử nghiệm, không phải làm một phát ăn ngay (mục 6).
2. **Android scoped storage** — xin đúng quyền truy cập folder kho (mục 2).
3. **Sidecar phải chuẩn bị cho Phase 2 ngay từ Phase 1** (mục 13).
4. **Sync friendly** — giữ dữ liệu dạng nhiều file nhỏ, metadata phân tán; tránh mọi file tập trung bị nhiều máy ghi.
5. **Phụ thuộc mini PC cho import "xịn"** — chấp nhận được trong mô hình "về nhà tự sync", nhưng cần trạng thái ⏳ rõ ràng.
6. **Moodle Web Services** có thể bị trường tắt → cần đường lùi (tải thủ công + Share).
7. **Scoped storage phần GHI** — app cần ghi/copy/xoá trong kho (`_inbox/` ở M6 khi Share, `_print/` ở M9 khi gom in, **folder môn ở M10** khi rename/move/xóa), không chỉ đọc cây kho. Xếp cùng nhóm "cần thử nghiệm" với highlight PDF (mục 1); spike phần ghi trước khi xây luồng (M6 + M9; M10 cần spike ghi *folder môn* riêng).
8. **File đang-ghi-dở trong `_inbox/`** (M7) — Syncthing/trình duyệt có thể để lộ file nửa chừng trông như hợp lệ → worker phải **stability check** (chờ size đứng yên) + lọc đuôi tạm trước khi đụng, kẻo extract ra sidecar cụt âm thầm (mục 5.4).
9. **PDF gốc là ca khó nhất cho extract** (M7) — khi gốc đã là PDF (không qua convert), parse cấu trúc Điều/Khoản kém hơn Word/PPTX (mục 4: "PDF tệ để parse cấu trúc"). Phải degrade sạch về `paragraph`, không bao giờ mất text.

---

## 15. Quyết định còn mở (để dành cho writing-plans)

- Thư viện render PDF cụ thể trên Capacitor/Android.
- Engine index search cụ thể (vd SQLite FTS5 local) — đã chốt *nguyên tắc* derived/không-sync, chưa chốt thư viện.
- ~~Định dạng/schema chi tiết của sidecar~~ → **ĐÃ CHỐT (trục 1 M7):** xem `gu-library-sidecar-schema.md`. Phẳng + `path` · text trong đơn vị · neo `page` · mỗi loại một `type` + đáy phổ quát `paragraph`/`slide`, degrade sạch.
- ~~Cơ chế cụ thể mini PC watch `_inbox/`~~ → **ĐÃ CHỐT (trục 3 M7):** polling vài phút qua Windows Scheduled Task, stateless, stability check + lọc đuôi tạm (mục 5.4).
- **`bbox` (toạ độ highlight) — để ngỏ, spike quyết:** schema hiện chỉ neo `page`. Vì kho còn nhỏ (~5 file), chạy spike highlight overlay Phase-2-sớm để quyết — khả thi thì thêm field `bbox` + chạy lại worker trên kho (rẻ lúc này); không khả thi thì bỏ highlight, schema giữ `page`. Cửa sổ "đập kho rẻ" này đóng dần khi kho lớn lên → quyết sớm.
- Cơ chế dọn `_print/` ở mức C (app xoá khi tick "xong" vs dọn định kỳ).
