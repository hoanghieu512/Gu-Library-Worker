# Spike: phạm vi OCR + thử engine OCR (2026-10-03)

> **CHỈ ĐO, KHÔNG SHIP.** Không ghi gì vào `D:\GuLibrary\kho` / `D:\GuLibrary-Prod\kho`, không đụng
> Scheduled Task, không bump version. Mọi thử nghiệm chạy trên **bản sao** trong thư mục scratch
> (ngoài cây Syncthing). Chỗ nào là *suy luận* thay vì *đo* đều ghi rõ.
>
> Máy đo: Atomman — Intel Core Ultra 9 185H (16 nhân / 22 luồng), 95,5 GB RAM, Windows 11, CPU-only.

---

## TL;DR

| | QA | **Prod** |
|---|---|---|
| Trang ảnh / tổng trang | **844 / 12.303 (6,9 %)** | **680 / 10.966 (6,2 %)** |
| Tài liệu ảnh / tổng sidecar | 13 / 180 | 12 / 136 |
| Trang ảnh "ẩn" (PDF có chữ nhưng vài trang không chữ — app không đếm) | 13 trang / 13 tài liệu | 9 trang / 7 tài liệu |

- **Gú có đọc không (Prod):** 5/12 tài liệu ảnh từng được mở (+1 mở rồi gỡ khỏi danh sách).
  Chỉ **1** tài liệu đọc sâu thật: `2. Luật sửa đổi … Bộ Luật hình sự_2025` tới **trang 38/48**.
  Ba tài liệu lớn chỉ dừng ở trang 1–5. Lần chạm cuối vào bất kỳ tài liệu ảnh nào: **2026-07-28**;
  hai tháng nay Gú chỉ đọc tài liệu có chữ.
- **Engine:** Tesseract 5.4 `vie` (tessdata_best) render **200 dpi**: ~3 s/trang một tiến trình,
  RAM ~50–100 MB, WER **0–1 %** trên scan sạch (luật, giáo trình), ~10–12 % trên photocopy mờ /
  ảnh báo; parser luật của worker nhận đúng Điều/Khoản; bbox dùng được.
  **PaddleOCR: loại** — từ điển nhận dạng của model thiếu **44/67** chữ thường tiếng Việt
  (ạ, ờ, ể, ữ…), WER 39–62 %, 44–212 s/trang.
- **Chạy thật hết 680 trang tồn Prod (bản sao):** 569 s (~9,5 phút) với 4 tiến trình song song,
  1.488 s (~24,8 phút) với 1 tiến trình. 677/680 trang ra chữ; 3 trang giữ câu đánh dấu (2 trang trắng +
  1 ảnh báo 109 dpi ra chữ rác — bắt bằng cổng OOV đề xuất ở §6.3, áp lên kết quả sau khi chạy). 12/12 sidecar qua `validate_sidecar` của worker.
- **Khuyến nghị: LÀM**, theo kiểu backfill có ngân sách thời gian, Tesseract, đọc thẳng PDF canonical
  trong kho. Lý do bằng số ở [§5](#5-khuyến-nghị).
- ⚠️ Brief ghi "worker v0.14.0" — worker hiện đã ở **v0.19.0**, nên bản có OCR sẽ là **v0.20.0**.

---

## 1. Phần 1a — Theo TRANG

### Cách đo
- Duyệt mọi `*.json` không bắt đầu bằng `_` (bỏ `_mon.json`, `_reading-*`), bỏ `.stversions`,
  `.stfolder`, `_inbox`, `_print`. Sidecar = JSON có `units`.
- **Trang ảnh** = unit có `text` bắt đầu bằng `[trang ảnh scan` (khớp TIỀN TỐ). Đếm số trang
  khác nhau mang câu đó, so với `pageCount`.
- Kiểm chéo bằng chính PDF canonical (mở từ bytes, chỉ đọc): mỗi trang đếm ký tự lớp chữ + tỷ lệ
  ảnh phủ trang. Với cả 25 tài liệu ảnh (QA+Prod): `số trang mang câu đánh dấu == pageCount ==
  số unit đánh dấu`, mọi trang `rotation=0`, cropbox gốc `(0,0)`.

### Tổng
| | Sidecar | Tổng trang | Tài liệu ảnh | Trang ảnh |
|---|---|---|---|---|
| QA `D:\GuLibrary\kho` | 180 | 12.303 | 13 | **844 (6,9 %)** |
| Prod `D:\GuLibrary-Prod\kho` | 136 | 10.966 | 12 | **680 (6,2 %)** |

Số tài liệu khác con số trong tài liệu (178 / 113) vì kho đã lớn thêm (Prod: +23 tài liệu tháng 9,
chủ yếu `Thương mại`, `PLCTKD`). Số **trang ảnh** không đổi so với lần đo 2026-09-05 trong runbook
(844 / 680) — tức từ đó tới nay không có tài liệu ảnh mới.

### TOÀN ẢNH hay LẪN
**Cả 25/25 tài liệu ảnh đều TOÀN ẢNH.** Đây là hệ quả của code chứ không phải ngẫu nhiên:
`read_pdf` chỉ sinh câu đánh dấu khi **toàn bộ** PDF không có chữ; PDF có chữ ở bất kỳ trang nào
đi nhánh thường, và trang không chữ trong đó **không sinh unit nào** (không đánh dấu).

→ Nên có một nhóm trang ảnh "ẩn" mà app không đếm. Đo bằng PDF (trang 0 ký tự, ảnh phủ > 30 %):
- Prod: **9 trang / 7 tài liệu** — trang bìa của 2 kỷ yếu hội thảo, 1 trang ảnh trong 4 bộ slide,
  3 trang trong `PLCTKD/ôn thi/SLIDE PLCTKD.pdf` (445 trang).
- QA: 13 trang / 13 tài liệu (cùng kiểu).
- Thêm nhóm "chữ rất ít trên nền ảnh" (< 60 ký tự, ảnh phủ > 50 %): Prod 110 trang / 33 tài liệu,
  gần hết là slide tiêu đề/slide hình. Giá trị tra cứu thấp — **đề xuất để ngoài phạm vi**.

### Danh sách tài liệu ảnh — Prod (12 tài liệu, 680 trang)
| Đường dẫn tương đối | pageCount | Trang ảnh | Loại | Nguồn | Ảnh trong PDF kho |
|---|---|---|---|---|---|
| `Hình sự phần chung/Ôn thi/GT LUAT HINH SU PHAN CHUNG-2017_ĐH LUẬT HÀ NỘI.pdf` | **398** | 398 | TOÀN ẢNH | PDF scan *(suy luận)* | JPEG 150 dpi (đã chuẩn hoá; gốc CCITT 398 dpi còn trong `kho_archive`) |
| `Hình sự phần chung/VBQPPL/Giám định pháp y, tâm thần.pdf` | 164 | 164 | TOÀN ẢNH | PDF scan *(suy luận)* | JPEG 150 dpi (gốc JPX 300 dpi trong archive) |
| `Hình sự phần chung/VBQPPL/2. Luật sửa đổi, bố sung một số điều của Bộ Luật hình sự_2025.pdf` | 48 | 48 | TOÀN ẢNH | PDF scan *(suy luận)* | JPEG 200 dpi (không chuẩn hoá) |
| `Hình sự phần chung/Bản án tham khảo/1. VỤ ÁN BÌNH PHƯỚC.pdf` | 39 | 39 | TOÀN ẢNH | PDF scan *(suy luận)* | JPEG 150 dpi (gốc JBIG2 200 dpi trong archive) |
| `Hình sự phần chung/VBQPPL/NQ hướng dẫn Đ65 án treo.pdf` | 19 | 19 | TOÀN ẢNH | PDF scan *(suy luận)* | JPEG 200 dpi |
| `Hình sự phần chung/VBQPPL/NQ Hướng dẫn Đ66 Tha tù trước thời hạn.pdf` | 6 | 6 | TOÀN ẢNH | PDF scan *(suy luận)* | JBIG2 400 dpi đen trắng (vào kho 07-02, trước bộ chuẩn hoá v0.10.0) |
| `Hình sự phần chung/Bản án tham khảo/Báo giấy/1_4_2026.pdf` | 1 | 1 | TOÀN ẢNH | ảnh `_inbox` v0.12.0 *(suy luận)* | JPEG 1221×1221 px (~104 dpi) |
| `…/Báo giấy/4_5_2026.pdf` | 1 | 1 | TOÀN ẢNH | ảnh `_inbox` *(suy luận)* | JPEG 1276×924 px (~109 dpi) |
| `…/Báo giấy/9_5_2026.pdf` | 1 | 1 | TOÀN ẢNH | ảnh `_inbox` *(suy luận)* | JPEG 150 dpi (đã chuẩn hoá) |
| `…/Báo giấy/12_5_2026.pdf` | 1 | 1 | TOÀN ẢNH | ảnh `_inbox` *(suy luận)* | JPEG 150 dpi |
| `…/Báo giấy/14_4_2026.pdf` | 1 | 1 | TOÀN ẢNH | ảnh `_inbox` *(suy luận)* | JPEG 150 dpi |
| `…/Báo giấy/20_5_2026.pdf` | 1 | 1 | TOÀN ẢNH | ảnh `_inbox` *(suy luận)* | JPEG 150 dpi |

**Vì sao "suy luận":** log worker xoay vòng chỉ còn từ 2026-08-18 (Prod) / 2026-08-14 (QA), mà cả 25
tài liệu ảnh vào kho trong tháng 7 → không còn dòng `processed <tên gốc> -> …` để biết đuôi gốc.
Dấu hiệu dùng: 6 tài liệu "Báo giấy" đều 1 trang, cạnh dài đúng 842 pt (chữ ký của
`image_to_single_page_pdf`), `addedAt` 2026-07-13 22:31 — sau commit v0.12.0 (16:51 cùng ngày).
Nội dung là trang báo in chụp/scan, phần lớn là trang trải đôi. Các PDF nhiều trang còn lại là scan;
4 cái có bản gốc nặng trong `kho_archive` (đã qua bộ chuẩn hoá 150 dpi).

**Giáo trình 398 trang:** ở Prod nằm trong `Hình sự phần chung/Ôn thi/` (tên "Ôn tập thi" là tên thư
mục bên **QA**: `Hình sự chung/Ôn tập thi/…`). Một mình nó = **58,5 %** trang ảnh Prod (398/680).
Trang A5 (420×595 pt), chữ in sạch → OCR tốt nhất trong cả bộ (xem §3).

### Danh sách tài liệu ảnh — QA (13 tài liệu, 844 trang)
Cùng bộ với Prod (đường dẫn cũ `Hình sự chung/…`), cộng thêm 1 bản trùng
`Chưa phân loại/Giám định pháp y, tâm thần (1).pdf` (164 trang). Khác biệt: ở QA, `NQ Hướng dẫn Đ66`
đã qua chuẩn hoá (150 dpi). Chi tiết đầy đủ nằm trong `scope.json` của lượt đo (không commit).

---

## 2. Phần 1b — Gú có đọc không

### Dữ liệu
3 file `_reading-*.json` ở gốc kho Prod (3 thiết bị), 84 entry, 15 tombstone. Đã xem entry mẫu
trước khi ghép: key là đường dẫn tương đối `/`, có đuôi `.pdf`, khớp thẳng với đường dẫn PDF trong
kho (so khớp sau NFC).

⚠️ **Đơn vị `lastReadAt` không phải ms.** Giá trị thật 1,7828·10¹⁵ … 1,7904·10¹⁵. Đọc là ms ra năm
~58.000; đọc là **µs** ra 2026-06-30 … 2026-09-27, khớp mtime các file. Ba chữ số cuối trông như bộ
đếm (`…000` → `…028`) — có thể là `ms × 1000 + counter`. **Bên Mac nên kiểm lại hợp đồng** (tài liệu
nói ms). So tombstone với `lastReadAt` vẫn đúng vì cùng thang.

Quy tắc xoá áp dụng **chéo thiết bị** (tombstone của máy nào cũng tính): 6 entry bị coi là đã xoá —
toàn bộ là đường dẫn cũ trước khi Gú sắp lại thư mục (`Chưa phân loại/Giám định…`, `bai tap SACH.pdf`…).
Riêng tombstone trong từng file: 0 entry bị xoá.

### Ghép với 12 tài liệu ảnh Prod
| Tài liệu | Trang | Đã mở? | Xa nhất (mọi thiết bị) | Lần cuối |
|---|---|---|---|---|
| `2. Luật sửa đổi … BLHS_2025` | 48 | ✅ 2 thiết bị | **38/48** | 2026-07-07 19:28 |
| `1. VỤ ÁN BÌNH PHƯỚC` | 39 | ✅ 2 thiết bị (1 qua đường dẫn cũ `Tố tụng Hình sự/…`) | 3/39 | 2026-07-28 20:42 |
| `GT LUAT HINH SU PHAN CHUNG-2017` | 398 | ✅ 1 thiết bị | **1/398** | 2026-07-27 23:54 |
| `Giám định pháp y, tâm thần` | 164 | ✅ 1 thiết bị (+1 entry đường dẫn cũ, đã tombstone) | 5/164 | 2026-07-02 23:22 |
| `NQ hướng dẫn Đ65 án treo` | 19 | ✅ 1 thiết bị | 2/19 | 2026-07-02 23:21 |
| `NQ Hướng dẫn Đ66 …` | 6 | ⚠️ không còn entry; có tombstone 2026-07-02 23:21 → **từng nằm trong danh sách rồi bị gỡ**, không biết trang | — | — |
| 6 × `Báo giấy/*.pdf` | 1 | ❌ không entry, không tombstone | — | — |

Giới hạn dữ liệu: mỗi file chỉ giữ **trang cuối** từng thiết bị, không phải lịch sử từng trang —
"38/48" không chứng minh đã đọc 38 trang, chỉ là chỗ dừng cuối.

Bối cảnh: entry mới nhất của cả 3 thiết bị là 2026-09-27, toàn tài liệu có chữ (BLHS, Luật hợp đồng,
PLCTKD). Tài liệu ảnh không được chạm vào từ 2026-07-28.

---

## 3. Phần 2 — Thử engine (trên bản sao)

### Thiết lập
- **Bản sao:** 12 PDF ảnh Prod + 3 PDF có chữ + 3 bản gốc `kho_archive`, chép vào scratch
  (`%TEMP%\claude\…\scratchpad\copies`). Render bằng PyMuPDF, ảnh xám, **200 và 300 dpi**.
- **Tesseract 5.4.0.20240606** (bản UB-Mannheim, đúng bản `winget` sẽ cài), bung *portable* vào
  scratch — **không cài hệ thống**. `vie.traineddata` từ `tessdata_best` (12,4 MB, LSTM float) và
  `tessdata` chuẩn (7,8 MB). `--psm 3`, xuất TSV (chữ + khung từng từ + conf). Bản này **đơn luồng**
  (đặt `OMP_THREAD_LIMIT` không đổi thời gian) → song song hoá bằng nhiều tiến trình.
- **PaddleOCR 3.7.0 + paddlepaddle 3.3.1 (CPU)** trong venv riêng. Thử 2 cấu hình:
  `lang="vi"` (→ `PP-OCRv6_medium_det/rec`) và `PP-OCRv5_mobile_det` + `latin_PP-OCRv5_mobile_rec`.
- **Bộ trang:** 14 trang thật đa dạng từ Prod (ưu tiên tài liệu Gú đã mở): luật scan ×4 (gồm
  **trang 38 Gú đang đọc**, NQ Đ65 có mộc dọc, NQ Đ66 400 dpi), bảng ×2, giáo trình A5 ×3, bản án
  photocopy ×2, ảnh báo ×3; với 7 trang có bản gốc archive thì chạy cả bản gốc. Cộng 5 trang **có lớp
  chữ** làm xuống 150 dpi JPEG q75 y như bộ chuẩn hoá → có **đáp án tự động** (lớp chữ).
- **Đáp án gõ tay** cho 4 đoạn trang thật (luật tr.38, giáo trình tr.21, bản án tr.10, báo 14/4):
  ~420 từ. CER/WER tính trên NFC, so từng dòng đáp án với dòng OCR giống nhất.
- Đo giờ: wall-clock mỗi trang (không gồm render, render 0,06–0,2 s); RAM: peak working set tiến
  trình tesseract (Paddle: RSS lấy mẫu + peak working set của tiến trình).

### Bảng engine
| Engine | s/trang (1 tiến trình) | RAM đỉnh | Chất lượng (WER trên đáp án gõ tay) | Cấu trúc luật sau OCR | bbox |
|---|---|---|---|---|---|
| **Tesseract 5.4 `vie` best, 200 dpi** | scan: 1,4–3,8 (trung vị theo nhóm 1,9–2,7); **cả tài liệu kể cả render: 1,7–3,1**; ảnh báo (tự lên 300 dpi): 6–32 | 46–80 MB (ảnh báo 300 dpi: ~100 MB) | luật **0,8 %** · giáo trình **0 %** · bản án photocopy 12,4 % · báo (300 dpi) 9,4 % · trang có chữ chuẩn: CER 0,5 % | ✅ Điều/Khoản nhận đúng (§3.3) | ✅ dòng, IoU trung vị 0,91 so với lớp chữ |
| Tesseract 5.4 `vie` chuẩn (tessdata), 200 dpi | ~35 % nhanh hơn best (trung vị ~1,5) | như trên | luật 1,5 % · giáo trình 0 % · bản án **22,9 %** · báo (300) 11,3 % | như trên | như trên |
| PaddleOCR `lang=vi` (PP-OCRv6 medium), oneDNN tắt | **44–212** | RSS ~0,84 GB (peak WS 3,2 GB) | luật **62 %** · giáo trình 55 % · bản án 39 % · báo 55 % | ❌ ("Điu", "Khon" — mất chữ) | có (khung dòng) |
| PaddleOCR PP-OCRv5 mobile + `latin` rec, oneDNN tắt | 36,8 (1 trang, gồm khởi động) | RSS ~0,34 GB sau nạp | luật **61 %** | ❌ | có |

**Vì sao Paddle loại hẳn (không phải chỉnh tham số):** kiểm `character_dict` trong model —
`PP-OCRv6_medium_rec` (18.708 ký tự) thiếu **44/67** chữ thường tiếng Việt, `latin_PP-OCRv5_mobile_rec`
(772 ký tự) thiếu 45/67: toàn bộ khối có dấu chồng/dấu nặng (ảạằắẳẵặầấẩẫậẻẽẹềếểễệỉịỏọốổỗộờớởỡợủụừứửữựỳỷỹỵ).
Model không thể sinh ra chữ không có trong từ điển → "Trong thi hn 05 ngày k t ngày Quyt đnh".
Thêm: với oneDNN bật, suy luận văng `NotImplementedError … onednn_instruction.cc` (lỗi Paddle 3.x
trên CPU Windows); tắt oneDNN thì chạy nhưng 44–212 s/trang. Lần cài đầu còn hỏng vì đường dẫn
dài vượt MAX_PATH (không bật long-path vì là setting hệ thống) → cài lại vào `D:\ocrspike`.
Venv Paddle ~630 MB. Theo brief "đừng sa lầy": dừng ở đây. (Hướng còn lại nếu sau này cần —
VietOCR, hoặc tự train rec model tiếng Việt cho Paddle — đều nặng hơn nhiều, không thử.)

### 3.1 Chất lượng — mẫu kết quả
Trang 38 `Luật sửa đổi BLHS 2025` (trang Gú đang đọc), Tesseract best 200 dpi — khớp đáp án trừ 1 dấu:
```
Trong thời hạn 05 ngày kể từ ngày Quyết định về đặc xá được niêm yết,
phổ biến, người đang chấp hành án phạt tù có thời hạn, tù chung thân nhưng đã
được giảm xuống tù có thời hạn căn cứ vào quy định tại Điều 11 và Điều 12 của
Luật này làm đơn đề nghị đặc xá.
```
Cùng trang, Tesseract **chuẩn** 200 dpi: giống hệt, trừ `phỗố biến`.

Cùng trang, PaddleOCR `lang=vi`:
```
Trong thi hn 05 ngày k t ngày Quyt đnh v đc xá đưc niêm yt,
ph bin, ngưi đang chp hành án pht tù có thi hn, tù chung thân nhưng đã
```

Trang 10 `VỤ ÁN BÌNH PHƯỚC` (photocopy chữ đánh máy mờ), Tesseract best 200 dpi — **ca xấu nhất của
nhóm scan**: sai gần như toàn dấu (11/13 lỗi là chỉ sai dấu: dẫn→dân, ngồi→ngôi, nằm→năm, vẫn→vấn):
```
và dân ông Mỹ dĩ vào phòng bắt ngồi xuống giường của cháu Anh, rồi kêu U lên ra
đóng cửa lại. Tiến ra ngoài khép cửa, khi quay vào nhìn thấy bà Nga ngôi trên
```

Ảnh báo 14/4 (300 dpi) — sai kiểu `ê/ế`, `ô/ố`: `vê việc`, `đôi với`, `tiêp tục`, `ý kiên`.

**Kiểu lỗi chung của Tesseract `vie`:** gần như chỉ sai **dấu** (hỏi↔huyền↔ngã, mũ có/không sắc),
hiếm khi sai chữ cái hay mất dòng (mất dòng: 0 trong 4 đoạn đáp án). Trên 21 nguồn trang thật (14 trang kho + 7 bản archive), OOV (tỷ lệ
token không có trong từ vựng ~13,3 nghìn token rút từ các sidecar có chữ của QA+Prod) chỉ 2–3 % —
nhưng OOV **đánh giá thấp** lỗi vì sai dấu thường vẫn ra từ hợp lệ ("phố", "kề", "hỗ").

### 3.2 DPI: 200 tốt hơn 300 cho scan; ảnh báo thì ngược lại
| Đoạn đáp án | WER 200 dpi | WER 300 dpi |
|---|---|---|
| Luật tr.38 (gốc JPEG 200 dpi) | **0,8 %** | 5,4 % |
| Giáo trình tr.21 (kho 150 dpi) | **0 %** | 0,8 % |
| Bản án tr.10 (kho 150 dpi) | 12,4 % | 11,4 % |
| Ảnh báo 14/4 (150 dpi, chữ nhỏ) | 26,4 % | **9,4 %** |

Phóng ảnh 200 dpi lên 300 làm nhoè nét dấu → Tesseract đọc sai thêm 6 dấu ở trang luật. Ngược lại
chữ báo nhỏ cần phóng. **Quy tắc tách được bằng một số đo đơn giản:** chiều cao dòng trung vị khi
render 200 dpi — trang scan 40–56 px, ảnh báo 19–23 px. Quy tắc dùng trong lượt chạy thật: *render
200 dpi; nếu chiều cao dòng trung vị < 30 px thì render lại 300 dpi* → 5/6 ảnh báo tự lên 300 dpi,
mọi trang scan ở 200 dpi.

**Bản gốc `kho_archive` (300–400 dpi) không tốt hơn bản kho 150 dpi một cách nhất quán:** giáo trình
tr.21 WER 0 % (kho) vs 1,5 % (archive); bản án tr.10 12,4 % vs 9,5 %. → OCR **đọc thẳng PDF canonical**
trong kho được; không cần phụ thuộc archive (vốn chỉ có cho một phần tài liệu).

### 3.3 Cấu trúc: đi qua parser của chính worker
Cách làm: OCR ra dòng (chữ + khung, đã đổi sang điểm PDF) → gom theo block/đoạn của Tesseract → đưa
vào **đúng** `pdf_reader.read_pdf` của worker, chỉ thay hàm `_read_pages` (nguồn dòng). Như vậy đi
qua cả lọc header/footer lặp, lọc chữ ký số, `has_legal_structure` → `parse_legal` hoặc rơi về
`paragraph`, rồi `normalize_text`, `to_sidecar`, `validate_sidecar`.

| Tài liệu | kind | Unit | Điều nhận được |
|---|---|---|---|
| Luật SĐ BLHS 2025 (48 tr.) | `legal` | 16 dieu · 156 khoan · 2 heading · 20 paragraph | Điều 1, 2, 3 của luật sửa đổi + các điều BLHS được trích sửa (236–252, 28, 31) — đúng kiểu một luật sửa đổi |
| NQ Đ65 (19 tr.) | `legal` | 12 dieu · 49 khoan · 43 paragraph | **Điều 1 → 12 liên tục**; `Điều 4a.` không nhận (regex `\d+\.` — giới hạn sẵn có, PDF có chữ cũng vậy) |
| NQ Đ66 (6 tr.) | `legal` | 8 dieu · 16 khoan · 13 paragraph | **Điều 1 → 8 liên tục** |
| Giám định pháp y (164 tr., bảng) | `legal` | 7 dieu · 18 khoan · 24 heading · 6.771 paragraph | phần lời Thông tư nhận Điều; bảng thương tật vỡ thành mảnh `paragraph` (tra được, hiển thị dạng mảnh) |
| Giáo trình 398 tr., bản án, 6 ảnh báo | `prose` | toàn `paragraph` | đúng — không có tiêu đề "Điều N." |

- **`diem`:** parser hiện có **không có quy tắc `diem`** (chỉ `dieu`/`khoan`; dòng `a)`, `b)` nối vào
  khoản) — PDF có chữ cũng vậy, không phải do OCR.
- Nhầm `Đ` ↔ `Ð` (U+00D0) — hay gặp ở OCR khác: 0–7 lần/tài liệu, không lần nào rơi vào dòng tiêu đề Điều.
- Dòng gần-như-Điều bị lỡ: chỉ thấy tham chiếu giữa câu (`Điêu 102, khoản 4…`) — đúng là không phải tiêu đề.
- Lỗi dấu ở tiêu đề in hoa (`HỘI ĐÔNG THẮM PHÁN`) không ảnh hưởng regex vì regex chỉ cần `Điều N.`.

### 3.4 bbox
**Có, dùng được.** TSV của Tesseract cho khung từng từ → hợp thành khung dòng, đổi sang điểm PDF
gốc trên-trái bằng `px × 72 / dpi` (trang render từ `page.rect`, mọi trang ảnh `rotation=0`, cropbox
gốc `(0,0)` → không cần xoay/dịch). Kiểm:
- Trang có lớp chữ: IoU trung vị giữa khung OCR và khung dòng của lớp chữ **0,83–0,97** (TB 0,91).
- Trang scan thật (luật tr.38): vẽ bbox unit lên trang bằng **đúng công thức của app**
  (`coord × render_w / page_w`) → khung ôm đúng dòng đầu khoản.
- Unit luật mang bbox **dòng đầu** (giống hành vi `parse_legal` với PDF có chữ); unit `paragraph`
  mang khung hợp của đoạn.

### 3.5 Chạy thật toàn bộ tồn Prod (680 trang, bản sao)
Tesseract best, quy tắc 200/300 dpi ở §3.2, cổng chặn trang: < 20 ký tự hoặc conf trung bình < 60
→ giữ câu đánh dấu.

| Tài liệu | Trang | 1 tiến trình | 4 tiến trình |
|---|---|---|---|
| Luật SĐ BLHS 2025 | 48 | 144,5 s | 40,7 s |
| NQ Đ65 | 19 | 53,0 s | 16,7 s |
| NQ Đ66 | 6 | 15,3 s | 5,5 s |
| Giám định pháp y (bảng) | 164 | 352,3 s | 109,9 s |
| Giáo trình HSPC 398 tr. | 398 | 669,0 s | 220,3 s |
| Vụ án Bình Phước | 39 | 119,2 s | 40,9 s |
| 6 ảnh báo (1 trang/tài liệu: 6,1 – 17,2 – 18,5 – 30,2 – 30,8 – 31,9 s) | 6 | 134,7 s ¹ | 134,7 s |
| **Tổng** | **680** | **1.488 s (~24,8 phút)** | **569 s (~9,5 phút)** |

- ¹ Ảnh báo đo trong lượt 4 tiến trình, nhưng mỗi tài liệu chỉ 1 trang (lượt này song song theo
  trang *trong* một tài liệu) nên thực chất là tuần tự — dùng chung cho cả hai cột.
- 4 tiến trình nhanh ~2,9–3,6× so với 1 trên tài liệu nhiều trang. RAM: 4 × ~50–100 MB.
- **Trang giữ câu đánh dấu:** giáo trình tr.5 (chỉ có số trang) và tr.398 (trắng) — conf 0, đúng mong muốn.
- **Lọt cổng nhưng là rác:** `Báo giấy/4_5_2026` (1276×924 px, ~109 dpi, trang trải đôi): conf 62
  > 60 nhưng chữ ra rác (OOV 19 %, vd "HLH5 nằm 2015 [ma đôi, hồ sung"). OOV trung vị mỗi trang trên
  670 trang là 0,4 %, chỉ 9 trang > 10 %, **1 trang > 15 %** (chính là trang này) → thêm cổng
  **OOV > 15 % ⇒ giữ câu đánh dấu** là đủ tách. Lượt chạy chỉ dùng cổng conf (chặn 2 trang); áp thêm
  cổng OOV lên kết quả → 677/680 trang ra chữ, 3 giữ đánh dấu.
- Dung lượng: 12 sidecar đánh dấu hiện tại 191 KB → sidecar OCR ~3,5 MB (indent 1; worker ghi indent 2
  sẽ lớn hơn chút). Giáo trình 398 trang: 110 KB → 1,17 MB.

---

## 4. Thời gian chạy hết lượng tồn
- **Đo thật (bản sao, Atomman):** 1.488 s (~24,8 phút) tuần tự, 569 s (~9,5 phút) với 4 tiến trình.
- Ràng buộc vận hành: Scheduled Task `GuLibraryWorker` chạy mỗi 3 phút, `MultipleInstances IgnoreNew`,
  `ExecutionTimeLimit 30 phút` (`scripts/register-task.ps1`) → không được chạy một mạch cả tài liệu
  398 trang trong một vòng; phải có ngân sách thời gian mỗi vòng (§6).
- Với ngân sách ~120 s OCR/vòng: ~40–70 trang/vòng (1 tiến trình, 1,7–3,1 s/trang) hoặc ~140–200
  trang/vòng (4 tiến trình) → tồn Prod hết trong **~10–17 vòng ≈ 30–50 phút** hoặc **~4–5 vòng ≈
  15 phút** đồng hồ.
  QA (844 trang) cỡ tương tự ×1,25.
- Tài liệu mới về sau: 1 trang scan ~3 s; một ảnh báo 6–32 s.

---

## 5. Khuyến nghị

| Option | Ưu | Nhược |
|---|---|---|
| **A. Không làm** (giữ câu đánh dấu) | Không rủi ro, không phụ thuộc mới | 680 trang (6,2 % Prod) + mọi ảnh/scan mới **mãi không tra được**, kể cả luật Gú đọc tới tr.38 |
| **B. OCR trong worker: backfill có ngân sách + tài liệu mới** (Tesseract) | Một lần ~1.488 s (~24,8 phút) CPU cho cả tồn Prod; app **không cần sửa**; chất lượng luật/giáo trình WER 0–1 %; tự phủ ảnh mới từ `_inbox` | Thêm phụ thuộc Tesseract (cài admin ~250 MB); sidecar bị ghi đè trong cây Syncthing (§6.5); trang photocopy/báo còn sai dấu ~10 % |
| C. Script chạy tay một lần cho tồn hiện có | Không đổi worker | Ảnh/scan mới không được phủ; phải nhớ chạy lại; vẫn ghi đè sidecar như B nhưng không có các chốt an toàn của pipeline |

**Đệ khuyến nghị B**, vì:
1. **Chi phí rất nhỏ so với phần phủ thêm:** cả tồn Prod tốn 1.488 s (~24,8 phút) CPU một lần (4 tiến trình:
   569 s (~9,5 phút)), RAM < 100 MB/tiến trình, máy 22 luồng gần như rảnh.
2. **Chất lượng đủ cho tra cứu ở đúng loại tài liệu chiếm phần lớn:** giáo trình (398/680 trang =
   58,5 %) WER 0 %, luật scan sạch WER 0,8 %; cấu trúc Điều/Khoản nhận liên tục.
3. **Hợp đồng không đổi:** chữ vào `units[].text`, `page` = trang PDF canonical (OCR chạy trên chính
   PDF đó, cùng chỉ số trang) → app tự tách từ lại theo dấu vân tay size:mtime.
4. Phía chống lại phải nói thẳng: **giá trị đọc hiện tại vừa phải** — mới 1/12 tài liệu ảnh được
   đọc sâu, và 2 tháng nay Gú không chạm tài liệu ảnh. Nếu ưu tiên hiện tại là "đóng băng tới khi
   có feedback người dùng thật" (runbook), B vẫn rẻ nhưng không gấp; khi đó có thể làm B sau.

**Không** nên làm: OCR phần "trang ảnh ẩn" (9 trang) và slide tiêu đề nền ảnh (110 trang) — giá trị thấp.

---

## 6. Phần 3 — Đề xuất thiết kế (CHỈ VIẾT, CHƯA CODE) — worker v0.20.0

### 6.1 OCR nằm ở đâu
- **Không** OCR ngay trong bước nhập (`process_one_file`): một tài liệu 398 trang ~20 phút sẽ vượt
  ngân sách vòng 3 phút và `ExecutionTimeLimit` 30 phút. Bước nhập giữ nguyên như nay (đóng ảnh →
  chuẩn hoá 150 dpi → sidecar đánh dấu) → tài liệu hiện ngay trong app.
- Thêm **giai đoạn OCR riêng cuối mỗi vòng**, sau `scan_once` của mọi kho. Tài liệu mới và tồn cũ
  đi chung một đường: "sidecar còn unit đánh dấu" = việc cần làm. Stateless như phần còn lại của
  worker (trạng thái suy từ filesystem).
- **Nguồn ảnh:** chính PDF canonical trong kho (bản đã chuẩn hoá 150 dpi nếu có) → `page` khớp
  tuyệt đối. Không render ở 150 dpi gốc: render **200 dpi**, lên **300 dpi** khi chiều cao dòng trung
  vị < 30 px (§3.2). Không dùng `kho_archive` (không tốt hơn, và chỉ một phần tài liệu có).
- Dựng unit bằng **đúng** `read_pdf` hiện có, tách hàm `_read_pages` thành "nguồn dòng" có hai cài đặt
  (lớp chữ PyMuPDF / OCR). Nhờ đó OCR hưởng sẵn lọc header/footer, chữ ký số, parse luật, degrade
  `paragraph`, `normalize_text`.

### 6.2 Backfill: thứ tự, ngân sách, chạy lại, chạy dở
- **Ưu tiên:** (1) tài liệu có entry trong `_reading-*.json` chưa bị tombstone (chéo thiết bị), mới
  nhất trước — với dữ liệu hôm nay: Bình Phước (07-28) → giáo trình (07-27) → Luật SĐ BLHS 2025
  (07-07, đọc sâu nhất 38/48) → Giám định → NQ Đ65; có thể nâng tài liệu đọc sâu (`page/total`
  lớn) lên đầu nếu muốn; (2) còn lại
  ít trang trước (nhiều tài liệu tra được sớm), giáo trình 398 trang để sau cùng nếu chưa ai mở.
  Kho Prod trước QA.
- **Ngân sách:** ~120 s OCR mỗi vòng (cả hai kho cộng lại), N tiến trình tesseract (đề xuất 4, cấu
  hình được). Hết ngân sách giữa chừng thì dừng sau trang đang chạy; vòng sau làm tiếp. Kho nào có
  file trong `_inbox` thì bước nhập vẫn chạy trước, OCR không bao giờ chặn nhập liệu.
- **Chạy dở tiếp được:** kết quả từng trang lưu ở **`<kho>_ocrcache/`** (anh em với `<kho>_archive`,
  ngoài cây Syncthing), khoá theo `(đường dẫn tương đối, size:mtime của PDF, số trang, phiên bản
  engine + traineddata + tham số)`. Vòng sau đọc cache, chỉ OCR trang thiếu. PDF đổi (size:mtime khác)
  → cache cũ tự vô hiệu.
- **Chạy lại ra cùng kết quả:** Tesseract đơn luồng, cùng ảnh + cùng model ⇒ cùng chữ. Dựng sidecar
  từ cache là hàm thuần; nếu sidecar dựng ra giống hệt cái đang có thì **không ghi**.
- **Ghi sidecar một lần cho cả tài liệu** khi đủ mọi trang — không ghi từng phần (tránh N phiên bản
  trong `.stversions` và N lần app tách từ lại).

### 6.3 Trang OCR hụt → giữ câu đánh dấu
Trang giữ nguyên unit `"[trang ảnh scan — chưa có lớp văn bản] (trang N)"` (đúng định dạng hiện tại,
app vẫn lọc theo tiền tố) khi: < 20 ký tự, **hoặc** conf trung bình < 60, **hoặc** OOV > 15 %
(từ vựng rút từ chính các sidecar có chữ, hoặc một danh sách âm tiết tiếng Việt cố định đi kèm
worker). Đo trên 680 trang: chặn đúng 3 trang (2 trắng + 1 ảnh báo rác), không chặn nhầm trang tốt nào
trong mẫu. Tài liệu lúc đó thành "LẪN" (có cả chữ lẫn đánh dấu) — **cần bên Mac xác nhận** app đếm
"N tài liệu là ảnh" theo *mọi* unit hay *bất kỳ* unit đánh dấu.

### 6.4 Field tùy chọn mới? (chỉ ĐỀ XUẤT — bên Mac chốt, phải khớp worker / app / `gu-library-sidecar-schema.md`)
Không bắt buộc: hợp đồng hiện tại đủ cho tính năng. Nếu muốn, đề xuất tối thiểu, đều **tùy chọn,
cộng thêm, giữ `schemaVersion: 1`** (giống cách đã thêm `bbox`):
- unit `"ocr": true` — vắng = `false`. Cho app gắn nhãn "chữ nhận dạng tự động, có thể sai dấu" ở
  kết quả tìm kiếm; và giúp phân biệt unit OCR với unit lớp chữ nếu sau này OCR cả trang ảnh "ẩn"
  trong PDF lẫn.
- cấp tài liệu `"ocrEngine": "tesseract 5.4.0 vie-best 200dpi"` — để biết lúc nào cần OCR lại khi
  đổi engine. (Có thể thay bằng khoá cache bên worker, không cần lộ ra sidecar.)
- Lưu ý `kind` có thể đổi `prose` → `legal` sau OCR (NQ Đ65/Đ66, Luật SĐ 2025): cần bên Mac xác nhận
  app chịu được `kind` đổi trên tài liệu đã có.

### 6.5 Rủi ro ghi đè sidecar trong cây Syncthing
- **Versioning:** folder `gu-library-kho-prod` trên Atomman dùng *staggered*, `maxAge` 30 ngày (chưa
  kiểm cấu hình 3 thiết bị kia). Thay thế do worker ghi tại chỗ không tạo version trên Atomman;
  các máy nhận sẽ cất bản cũ vào `.stversions`. Bản cũ là sidecar đánh dấu nhỏ: tổng 191 KB cho cả
  12 tài liệu Prod → không đáng kể, **với điều kiện ghi một lần mỗi tài liệu** (§6.2). Ghi từng phần
  giáo trình 398 trang ~7 lần sẽ cất ~7 bản lớn dần tới ~1 MB mỗi máy — vẫn nhỏ nhưng vô ích.
- **Conflict:** app (Quản lý kho M10) có thể đổi tên/chuyển/xoá cặp pdf+json trên điện thoại đúng lúc
  worker ghi sidecar → `*.sync-conflict-*` hoặc json mồ côi ở đường dẫn cũ. Chốt: ngay trước khi
  thay, kiểm lại PDF còn đó + size:mtime như lúc bắt đầu + sidecar còn đúng bản đánh dấu đã đọc;
  lệch bất kỳ → bỏ, vòng sau tính lại.
- **File tạm:** không bao giờ tạo file tạm trong kho (Syncthing sẽ đồng bộ nó). Ghi vào
  `<kho>_ocrcache/` (cùng ổ D:) rồi `os.replace` sang đích → thay nguyên tử, Syncthing thấy một thay đổi.
- **Băng thông:** ~3,5–4 MB sidecar mới cho cả tồn Prod, một lần.

### 6.6 Vận hành
- Cài Tesseract trên Atomman bằng `winget install UB-Mannheim.TesseractOCR` (cần Admin), thêm
  `vie.traineddata` bản **best** vào `tessdata`. Worker cấu hình đường dẫn; thiếu binary/traineddata
  → bỏ qua giai đoạn OCR, log một dòng mỗi vòng, **không** làm hỏng bước nhập.
- Không dùng `tessdata` chuẩn để tiết kiệm thời gian: nhanh hơn ~35 % nhưng photocopy WER 23 % vs 12 %.
- Test: dựng PDF ảnh nhỏ từ chữ đã biết → OCR → khẳng định `page`, chữ, bbox; skip nếu máy test
  không có Tesseract.

---

## 7. Sự cố quan sát được trong lúc đo (ngoài phạm vi, chưa rõ nguyên nhân)
- `GuLibraryWorker` **không chạy vòng nào từ 19:55 tới 21:01** (cả QA lẫn Prod). Hai instance khởi
  động lúc 19:58 và 20:31 kẹt ở **launcher `pythonw.exe` của venv** (5–6 MB, 1 luồng, không có tiến
  trình con — trình thông dịch thật chưa kịp chạy), mỗi cái bị `ExecutionTimeLimit 30 phút` diệt;
  các lần kích hoạt giữa chừng bị từ chối `0x800710E0` do `MultipleInstances IgnoreNew`.
- **Tự hồi:** vòng 21:01 và 21:04 chạy bình thường. Đệ không đụng task hay tiến trình (ràng buộc cứng).
- Khung 19:58–20:55 **trùng đoạn spike tải nặng nhất** (pip cài Paddle ~630 MB, Paddle suy luận nhiều
  luồng, chạy Tesseract cả tài liệu). Trước đó (16:20–19:55) spike cũng chạy mà worker vẫn đều. Không
  loại trừ được việc tải của spike gây ra; cũng chưa chứng minh được. Task chạy kiểu S4U, quyền
  Limited, Python gốc là bản Microsoft Store (không cập nhật — cài 2025-07-10).
- Ảnh hưởng: `_inbox` hai kho trống suốt khung đó (vòng hồi phục `processed=0`) → không file nào bị
  chậm. Cơ chế báo bù v0.19.0 chỉ dò khoảng nghỉ của print-sync nên sự cố này không có cảnh báo chat.
- Liên quan thiết kế OCR (§6): nếu chạy OCR nhiều tiến trình ngay trong worker, nên đo lại hiện tượng
  này trước (vd chạy 4 tiến trình tesseract liên tục 30 phút, xem launcher của vòng kế có kẹt không),
  và có thể cân nhắc chạy worker bằng `python.exe` của bản Python cài thường thay vì alias Store.

---

## Phụ lục — tái lập & dọn dẹp
- Script đo (scratch, không commit): `snapshot.py` (số file + mtime hai kho trước/sau), `scope.py`
  (Phần 1, chỉ đọc), `bench_tess.py`, `bench_paddle.py`, `eval_real.py` (đáp án gõ tay),
  `fulldoc.py` (đưa OCR qua `read_pdf` + `validate_sidecar` của worker), `agg.py`.
- Đã xoá sau khi đo: bản sao PDF + ảnh render + kết quả OCR/sidecar thử (đều là dữ liệu dẫn xuất
  từ kho), Tesseract portable + traineddata, 7-Zip giải nén từ MSI (`msiexec /a`, không đăng ký),
  venv spike, venv Paddle `D:\ocrspike` (kể cả model), và cache Paddle mà thư viện tự rải ra home
  (`~/.paddlex`, `~/.cache/paddle`, 4 thư mục `models--PaddlePaddle--*` trong cache HuggingFace —
  phần còn lại của cache HF có từ trước, giữ nguyên). Không cài gì vào hệ thống, không đụng venv
  `.venv` của worker (chỉ dùng python của nó chạy script đọc kho, thư viện chuẩn + PyMuPDF có sẵn).
  Cache tải về chung của pip có thể còn giữ wheel paddle — không xoá vì là cache dùng chung.
- Xác nhận kho không đổi: snapshot (đường dẫn, size, mtime_ns của mọi file, kể cả
  `.stversions`) lúc 16:20 và 20:55 ngày 2026-10-03:
  - QA: 403 → 403 file, 36 → 36 thư mục, 0 thêm / 0 xoá; 1 file đổi: `_worker.log`.
  - Prod: 318 → 318 file, 39 → 39 thư mục, 0 thêm / 0 xoá; 1 file đổi: `_worker.log`.
  - `_worker.log` đổi do Scheduled Task `GuLibraryWorker` tự ghi mỗi vòng (62 vòng `scan starting` /
    `done: processed=0 …` từ 16:20 tới 19:55), không phải do spike.
