# Gú's Library — Sidecar JSON Schema (chốt trục 1 + bbox + ocr)

> **Vai trò:** hợp đồng dài hạn giữa worker M7 (sinh) và app + Phase 2 search/cross-link (tiêu thụ).
> **Nguyên tắc:** một hình dạng cho cả 3 loại nội dung (luật / slide / giáo trình). Degrade sạch khi parse hụt — mất cấu trúc, không bao giờ mất text.

---

## Hình dạng tổng thể

```jsonc
{
  // ---- METADATA cấp tài liệu ----
  "schemaVersion": 1,
  "title": "Luật Công chứng 2024",   // tên hiển thị (từ tên file gốc, bỏ tiền tố môn)
  "source": "share",                 // nguồn nhập: share | watch | (sau: moodle | vbpl)
  "addedAt": "2026-06-21T10:30:00+07:00",
  "sourceFormat": "pdf",             // gốc trước convert: pdf | docx | pptx
  "pageCount": 42,                   // số trang PDF canonical
  "kind": "legal",                   // phân loại thô tài liệu: legal | slide | prose
                                     //   (giúp app chọn cách render danh sách; KHÔNG thay type đơn vị)

  // ---- DANH SÁCH ĐƠN VỊ (phẳng, tuyến tính theo thứ tự đọc) ----
  "units": [
    {
      "type": "dieu",               // dieu | khoan | diem | slide | heading | paragraph
      "label": "Điều 5",            // nhãn hiển thị của đơn vị (rỗng nếu không có)
      "path": ["Chương I", "Điều 5"], // tổ tiên để hiện ngữ cảnh đầy đủ; [] nếu không có
      "text": "Văn bản đầy đủ của đơn vị này…",
      "page": 3,                    // trang BẮT ĐẦU trong PDF canonical (1-indexed)
      "bbox": [72.0, 130.5, 523.0, 168.2], // TÙY CHỌN: [x0,y0,x1,y1] điểm PDF, gốc trên-trái, trên trang `page`. Vắng = chỉ nhảy trang.
      "ocr": true                   // TÙY CHỌN: unit sinh từ OCR trang ảnh (worker v0.20.0+). Vắng = false.
    }
  ]
}
```

---

## Chú giải từng trường

### Cấp tài liệu
| Trường | Bắt buộc | Ý nghĩa |
|---|---|---|
| `schemaVersion` | ✓ | Đánh số schema. Bắt đầu `1`. Đổi hình dạng → tăng số → app biết đường đọc bản cũ. (`bbox` và `ocr` là field **tùy chọn thêm vào** — không phá bản cũ, giữ version `1`.) |
| `title` | ✓ | Tên hiển thị, lấy từ tên file gốc sau khi worker **bỏ tiền tố môn** `[<môn>]`. |
| `source` | ✓ | Đường vào. Phase 1: `share` / `watch`. Để sẵn cho `moodle`/`vbpl` Phase 3. |
| `addedAt` | ✓ | Thời điểm worker xử lý (ISO 8601, có offset giờ VN). |
| `sourceFormat` | ✓ | Định dạng gốc TRƯỚC convert. Cho biết file đi qua nhánh reader nào. |
| `pageCount` | ✓ | Tổng trang PDF canonical — app dùng cho progress bar "Trang X / Y". |
| `kind` | ✓ | Phân loại thô: `legal` / `slide` / `prose`. App dùng để chọn kiểu hiển thị; KHÔNG dùng thay cho `type` đơn vị. |

### Cấp đơn vị (mỗi phần tử `units[]`)
| Trường | Bắt buộc | Ý nghĩa |
|---|---|---|
| `type` | ✓ | Loại đơn vị mịn. Tập giá trị Phase 1: `dieu` `khoan` `diem` `slide` `heading` `paragraph`. **`paragraph` (văn xuôi) / `slide` (slide) là đáy phổ quát** — parse hụt cấu trúc thì rơi về đây, không bao giờ có đơn vị "không loại". |
| `label` | ✓ (có thể rỗng) | Nhãn người đọc thấy: "Điều 5", "Khoản 2", "Slide 12". Văn xuôi không nhãn → `""`. |
| `path` | ✓ (có thể `[]`) | Mảng nhãn tổ tiên, để search/cross-link hiện "Khoản 2 · Điều 5 · Chương I" mà khỏi dựng cây. Phi-luật thường `[]`. |
| `text` | ✓ | Toàn văn đơn vị. **Hạt search** (passage-level, spec 7). Không bao giờ rỗng nếu đơn vị có chữ. |
| `page` | ✓ | Trang BẮT ĐẦU của đơn vị trong PDF canonical (1-indexed). Hạt để Viewer nhảy tới (spec 6). |
| `bbox` | ✗ (tùy chọn) | `[x0, y0, x1, y1]` — khung text của đơn vị, **điểm PDF, gốc trên-trái**, trên trang `page`. Để Viewer **highlight đúng đoạn** (Phase 2). **Vắng = degrade sạch**, Viewer chỉ nhảy tới `page`. Map sang màn: `coord × (bề_rộng_render / bề_rộng_trang)`, gốc trên-trái khớp thẳng. |
| `ocr` | ✗ (tùy chọn) | `true` = `text` của unit do **OCR** nhận dạng từ trang ảnh, không phải lớp chữ thật — có thể sai dấu (xem mục "Unit từ OCR"). **Vắng = `false`.** Chỉ worker v0.20.0+ sinh. |

---

## Trang ẢNH chưa OCR — câu đánh dấu (`IMAGE_PAGE_MARKER`)

Trang là ảnh scan, không có lớp văn bản → worker vẫn sinh unit hợp lệ nhưng `text` mang một **câu
đánh dấu** thay vì nội dung:

```
[trang ảnh scan — chưa có lớp văn bản] (trang 12)
```

- **`IMAGE_PAGE_MARKER` là TÊN HẰNG SỐ trong source worker, KHÔNG phải giá trị.** Ghi giá trị thật
  ra đây vì đã có lần bên app đặt hằng số bằng chính cái tên đó → không khớp gì cả (v1.38.0/1).
- **Có đuôi `(trang N)` đổi theo từng trang** → bên tiêu thụ phải khớp **TIỀN TỐ**, không so bằng nhau.
- Đây **không phải nội dung**: bên tiêu thụ (index tìm kiếm) phải loại nó ra, nếu không tài liệu
  ảnh sẽ nằm trong chỉ mục như thể tra được. App loại ở `isReadableText()`
  (`src/search/invertedIndex.ts`), và đếm riêng `imageOnly` để nói cho người dùng biết.
- Đối chiếu 2026-09-05, kho QA: đúng **13/178** tài liệu có MỌI unit mang câu này (kho Prod 12/113).
  Theo TRANG (spike 2026-10-03): QA **844/12.303** · Prod **680/10.966** trang.
- **Từ worker v0.20.0 (OCR):** trang ảnh được OCR và câu đánh dấu bị **thay bằng chữ thật** (unit
  `ocr: true`). Trang OCR hụt (trắng, độ tin thấp, chữ rác) **GIỮ NGUYÊN câu đánh dấu** đúng định dạng
  trên → một tài liệu có thể **LẪN** (unit chữ + unit đánh dấu). App chịu được: chỉ coi là tài liệu
  ảnh (`imageOnly`) khi **không có unit đọc được nào**; unit đánh dấu vẫn bị loại theo tiền tố.
- Câu đánh dấu chỉ sinh khi **TOÀN BỘ** PDF không có lớp chữ. PDF có chữ mà vài trang là ảnh thì
  trang đó **không sinh unit nào** (không đánh dấu, không OCR) — ngoài phạm vi, giá trị tra cứu thấp.

---

## Unit từ OCR (`ocr: true`) — worker v0.20.0+

Đúng hình dạng unit thường, khác ở nguồn chữ. Bên tiêu thụ **không cần nhánh xử lý riêng** — chỉ mục
app tự tách từ lại tài liệu khi sidecar đổi (so dấu vân tay `size:lastModified`).

- **Engine:** Tesseract 5.4 `vie` (tessdata **best**), render 200 dpi, tự lên 300 dpi khi chữ nhỏ.
  Chạy local trên Atomman — không cloud, đúng spec §7.
- **`page`:** OCR chạy trên **chính PDF canonical trong kho** → `page` khớp tuyệt đối, không suy ngược.
- **Cấu trúc:** chữ OCR đi qua **đúng** parser của nhánh PDF (lọc header/footer, `dieu`/`khoan`,
  degrade `paragraph`). Vì vậy **`kind` có thể đổi** `prose` → `legal` khi sidecar được ghi lại
  (vd nghị quyết, luật sửa đổi) — app không dùng `kind` cho hành vi nên an toàn.
- **`bbox`:** có, quy từ khung chữ OCR về điểm PDF (`px × 72 / dpi`, gốc trên-trái). Unit luật mang
  khung **dòng đầu** (như PDF có chữ); `paragraph` mang khung hợp của đoạn.
- **Chuẩn hoá chữ:** NFC như mọi nhánh (v0.16.0) **cộng** `Ð`/`ð` (U+00D0/U+00F0, chữ eth OCR hay
  nhầm) → `Đ`/`đ` (U+0110/U+0111). Bắt buộc: `fold()` của app chỉ đổi `đ`→`d`, để lọt `Ð` thì
  "Ðiều" tách thành token `ieu`, tra "dieu" không ra.
- **Chất lượng (spike 2026-10-03):** sai gần như CHỈ ở **dấu** (hỏi↔huyền↔ngã, mũ). WER luật scan sạch
  0,8% · giáo trình 0% · photocopy mờ ~12% · ảnh báo ~9%. Tìm kiếm của app bỏ dấu hai phía nên lỗi dấu
  gần như vô hại với tra cứu; chỉ lộ ra ở chữ trong đoạn trích.
- **Ghi sidecar:** MỘT lần mỗi tài liệu khi đủ mọi trang (không ghi từng phần), thay nguyên tử —
  tránh N bản trong `.stversions` và N lần app tách từ lại.

---

## Quy tắc điền `bbox` (đã chốt — chỉ PDF)

- **Nguồn PDF** (`sourceFormat: "pdf"`, gốc đã là PDF): PyMuPDF nhả toạ độ text thẳng trên PDF canonical → **điền `bbox`**.
- **Nguồn Word/PPTX** (`docx`/`pptx`): cấu trúc extract từ file gốc — file gốc KHÔNG có toạ độ PDF → **để trống `bbox`** ở Phase 1. Vẫn hợp lệ, vẫn nhảy trang. (Highlight cho slide/giáo trình để Phase 2 nếu cần — không ép dò ngược trên PDF-render.)
- Unit PDF parse hụt toạ độ → **bỏ `bbox`**, giữ `page`. Không bao giờ vì thiếu bbox mà chặn unit.

---

## Ba loại nội dung trông như thế nào

**Luật** (`kind: "legal"`): units là chuỗi `dieu`/`khoan`/`diem`, `path` mang Chương/Điều, cross-link Phase 2 nhảy theo `type: "dieu"`. Nếu nguồn PDF → có `bbox`.

**Slide** (`kind: "slide"`, gốc pptx): mỗi slide một unit `type: "slide"`, `label: "Slide N"`, `page` = đúng trang đó (1 slide ≈ 1 trang PDF), `path: []`. Nguồn pptx → **không** `bbox`.

**Giáo trình** (`kind: "prose"`): units là `heading` + `paragraph` xen kẽ, `path` mang chương/mục nếu nhận diện được, không thì `[]`. PDF → có `bbox`; docx → không.

---

## Đã CHỐT / để NGỎ

**Chốt (trục 1 + bbox + ocr):**
- Phẳng + `path` (không cây lồng).
- Text trong từng đơn vị, không blob `fullText` tổng.
- Neo `page` (trang bắt đầu), 1-indexed.
- Mỗi loại một `type`, có đáy phổ quát `paragraph`/`slide`, degrade sạch.
- **`bbox` TÙY CHỌN — đã thêm sau spike highlight PASS.** Điền cho nguồn PDF; Word/PPTX để trống. Vắng = nhảy trang, không lỗi.
- **`ocr` TÙY CHỌN — đã thêm 2026-10-03 sau spike OCR** (worker v0.20.0). Thêm ngay dù app chưa đọc
  (rẻ lúc sinh, đắt nếu phải ghi lại cả kho sau). Dự kiến dùng: nhãn "chữ nhận dạng tự động" ở kết quả
  tìm. **KHÔNG** có `ocrEngine` cấp tài liệu — khoá cache `<kho>_ocrcache/` bên worker lo việc OCR lại khi
  đổi engine.

**Để ngỏ — quyết sau:**
1. **`pageEnd`** (đơn vị vắt nhiều trang): hiện chỉ `page` bắt đầu. Cân khi thiết kế Viewer/search Phase 2 — nếu "nhảy tới + biết đơn vị dài tới đâu" cần thì thêm. Slide không bao giờ cần (1 trang). Để ngỏ, không thêm sớm (YAGNI).
2. **`bbox` cho Word/PPTX** (dò ngược trên PDF-render): bỏ ngỏ tới Phase 2 — chỉ làm nếu highlight slide/giáo trình thật sự cần.
