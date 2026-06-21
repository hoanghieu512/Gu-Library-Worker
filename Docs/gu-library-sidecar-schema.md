# Gú's Library — Sidecar JSON Schema (chốt trục 1 + bbox)

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
      "bbox": [72.0, 130.5, 523.0, 168.2] // TÙY CHỌN: [x0,y0,x1,y1] điểm PDF, gốc trên-trái, trên trang `page`. Vắng = chỉ nhảy trang.
    }
  ]
}
```

---

## Chú giải từng trường

### Cấp tài liệu
| Trường | Bắt buộc | Ý nghĩa |
|---|---|---|
| `schemaVersion` | ✓ | Đánh số schema. Bắt đầu `1`. Đổi hình dạng → tăng số → app biết đường đọc bản cũ. (`bbox` là field **tùy chọn thêm vào** — không phá bản cũ, giữ version `1`.) |
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

**Chốt (trục 1 + bbox):**
- Phẳng + `path` (không cây lồng).
- Text trong từng đơn vị, không blob `fullText` tổng.
- Neo `page` (trang bắt đầu), 1-indexed.
- Mỗi loại một `type`, có đáy phổ quát `paragraph`/`slide`, degrade sạch.
- **`bbox` TÙY CHỌN — đã thêm sau spike highlight PASS.** Điền cho nguồn PDF; Word/PPTX để trống. Vắng = nhảy trang, không lỗi.

**Để ngỏ — quyết sau:**
1. **`pageEnd`** (đơn vị vắt nhiều trang): hiện chỉ `page` bắt đầu. Cân khi thiết kế Viewer/search Phase 2 — nếu "nhảy tới + biết đơn vị dài tới đâu" cần thì thêm. Slide không bao giờ cần (1 trang). Để ngỏ, không thêm sớm (YAGNI).
2. **`bbox` cho Word/PPTX** (dò ngược trên PDF-render): bỏ ngỏ tới Phase 2 — chỉ làm nếu highlight slide/giáo trình thật sự cần.
