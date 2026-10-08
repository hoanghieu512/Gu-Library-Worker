# Zalo Bot — hướng dẫn dùng lại (bàn giao cho SquarePilot Phase 6)

> Viết 08/10/2026 trên Atomman (Gu-Library-Worker). Bot này chạy cảnh báo ops cho Gu Library từ
> 29/09/2026. Mục đích: SquarePilot (Mac) dùng **chính bot này** thay Telegram cho bước duyệt bài
> (PRD §2 bước 8, US#52–57; plan Phase 6 `telegram-approver`) mà không phải research lại.
> Docs chính thức: <https://bot.zapps.me/docs/>. Mục nào ghi *(quan sát)* là đo thật trên bot
> này; *(docs)* là đọc tài liệu, chưa chạy thử.

## TL;DR — những điểm khác Telegram

1. **Cùng dạng API**: `POST https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>`, body JSON,
   trả `{ "ok": true, "result": … }`. Nhưng **ít tính năng hơn nhiều**.
2. **Không có nút bấm**: không có `reply_markup` / inline keyboard / `callback_query` *(docs)*.
   → Duyệt bằng **lệnh chữ** kèm mã draft (§5).
3. **Tin nhắn đến không cho biết đang trả lời tin nào**: không có quote, không có `reply_to` *(docs)*.
   → Mỗi lệnh phải tự mang mã draft.
4. **Mỗi tin tối đa 2000 ký tự** (text và caption ảnh đều vậy) *(docs)*. Draft SquarePilot dài
   ~1600–2100 ký tự, bài đầu tiên đã 2039 NFC → **phải tách thành nhiều tin**.
5. **`sendPhoto` CHỈ nhận URL `http(s)`** *(quan sát 08/10)*. Không upload file được, không dùng
   data-URI được. Muốn gửi PNG local thì **bắt buộc có URL public** (§6.2).
6. **Nhận tin có 2 cách**: `getUpdates` (long-poll, không có `offset`) hoặc webhook (URL HTTPS
   public + header secret). **Hai cách loại trừ nhau** *(docs)*.
7. **Không có giới hạn 7 ngày** *(quan sát 08/10)*: 9 ngày sau lần cuối huynh nhắn bot, bot tự
   gửi vẫn tới. Khác Zalo OA, **không cần** nhắn bot định kỳ.

## 1. Bot hiện có — dùng lại, không tạo bot mới

- **Token và `chat_id`** nằm trên mini PC, ở `%APPDATA%\GuLibrary\notify.json`
  (`{"provider":"zalo","token":"…","chat_id":"…"}`). Huynh **tự copy** sang `.env` của
  SquarePilot. Không gửi qua git, chat hay log.
- `chat_id` là ID cuộc chat giữa **bot này** và huynh, nên dùng lại được ngay, khỏi chạy setup.
- Token có dạng `<số>:<secret>`. Nếu mất token, lấy lại ở chỗ quản lý bot trong Zalo (Zalo Bot
  Creator / bot.zaloplatforms.com). Token nằm trong tin chào lúc tạo bot. *(Đệ chưa kiểm lại UI.)*
- `.env` đề xuất, thay `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` ở PRD §4.4:

  ```
  ZALO_BOT_TOKEN=
  ZALO_CHAT_ID=
  ZALO_API_BASE=https://bot-api.zaloplatforms.com   # trỏ sang fake server khi test
  ```

- Kiểm nhanh từ terminal Mac (token lấy từ env, không gõ thẳng):

  ```bash
  curl -s -X POST "$ZALO_API_BASE/bot$ZALO_BOT_TOKEN/getMe"
  curl -s -X POST "$ZALO_API_BASE/bot$ZALO_BOT_TOKEN/sendMessage" \
    -H 'Content-Type: application/json' \
    -d "{\"chat_id\":\"$ZALO_CHAT_ID\",\"text\":\"SquarePilot test\"}"
  ```

## 2. API rút gọn

| Method | Tham số | Ghi chú |
|---|---|---|
| `getMe` | — | Kiểm token |
| `sendMessage` | `chat_id`, `text` (1–2000), `parse_mode`? (`markdown`\|`html`), `text_styles`? | Trả `{"ok":true,"result":{"message_id":"…","date":<epoch ms>},"error_code":0}` *(quan sát)* |
| `sendPhoto` | `chat_id`, `photo` (URL `http(s)`), `caption`? (1–2000) | Body JSON. Trả `result.message_type: "CHAT_PHOTO"` *(quan sát)* — chỉ URL, xem §6.2 |
| `sendChatAction` | `chat_id`, `action` (`typing` \| `upload_photo`) | Chỉ hiện trạng thái "đang gõ…" |
| `getUpdates` | `timeout` (string, giây, mặc định 30) | Không có `offset`. Không chạy được khi đang có webhook |
| `setWebhook` | `url` (HTTPS public), `secret_token` (8–256 ký tự) | localhost / IP nội bộ bị từ chối. URL vẫn được lưu dù verify fail |
| `deleteWebhook`, `getWebhookInfo`, `testWebhook` | — | `testWebhook` kiểm URL có tới được không |
| `sendSticker`, `sendVoice` | — | SquarePilot không cần |

**Tin đến** (webhook body, hoặc phần tử trong `result` của `getUpdates`) *(docs)*:

```json
{ "ok": true, "result": {
    "event_name": "message.text.received",
    "message": {
      "from": { "id": "…", "display_name": "…", "is_bot": false },
      "chat": { "id": "…", "chat_type": "PRIVATE" },
      "text": "d K7", "message_id": "…", "date": 1750316131602 } } }
```

Các giá trị `event_name`: `message.text.received`, `message.image.received`,
`message.sticker.received`, `message.voice.received`, `message.unsupported.received`.
Ngoài `message.text.received`, các loại còn lại đều bỏ qua.
Webhook gửi kèm header `X-Bot-Api-Secret-Token: <secret_token>`. Header sai thì trả 403.

## 3. Bài học thực chiến từ worker

- **`getUpdates` trả MỘT object update**, còn Telegram trả mảng *(quan sát 29/09)*.
  → Chuẩn hóa bằng `[].concat(resp.result ?? [])` rồi lọc phần tử có `message.chat.id`.
- **`getUpdates` chỉ trả tin đến TRONG LÚC đang chờ** *(quan sát)*. Tin gửi lúc không ai poll
  thì không lấy lại được. Không có `offset`, nên mỗi tin chỉ về một lần.
  → Poller phải chạy liên tục. Timeout HTTP của client phải lớn hơn `timeout` poll (worker để +15 s).
- **Gọi lỗi vẫn trả HTTP 200**, ví dụ `{"ok":false,"description":"Bad request: …","error_code":400}`
  *(quan sát)*. → Phải kiểm `ok`, không dựa vào status HTTP. Lỗi thật nằm ở `description`.
- **URL có chứa token** → redact token trong mọi log lỗi (`err.message`, URL request).
  Worker không bao giờ in token ra.
- **Gửi draft thì bỏ `parse_mode`** để Zalo không nuốt `*`, `_`, `#`, `$`. Như vậy chữ hiện ra
  đúng nguyên văn, khớp nguyên tắc "text truyền nguyên văn" của SquarePilot.
- **Tách tin dài**: worker cắt ở 1900 ký tự + `" ..."`. SquarePilot nên tách theo ranh giới
  đoạn văn, mỗi tin ≤ ~1900 ký tự. Zalo đếm ký tự theo đơn vị nào thì docs không nói, nên chừa biên.
- **Ai cũng tìm được bot và nhắn được cho bot** → **chỉ xử lý tin có
  `message.chat.id === ZALO_CHAT_ID`** và `from.is_bot === false`. Tin khác chỉ ghi log, bỏ qua.
- Body UTF-8: `fetch` của Node tự lo. (Worker phải gửi bytes vì PowerShell 5.1 — không liên quan Mac.)

## 4. Dùng chung bot với Gu-Library-Worker

- Worker **chỉ gửi** (`sendMessage` từ mini PC), không đọc update. SquarePilot được **toàn
  quyền** phần nhận (getUpdates hoặc webhook).
- Hai luồng **chung một khung chat**: tin backup Chủ nhật, cảnh báo ⚠️ xen giữa các draft. Tin
  do bot gửi không quay về dạng update, nên SquarePilot không tự đọc lại tin của mình. Parser
  chỉ cần bỏ qua mọi chữ không phải lệnh.
- `scripts/notify-setup.ps1` của worker dùng `getUpdates`. Chỉ phải chạy lại khi mất `chat_id`,
  hiện chưa cần. Nếu có lúc phải chạy, tắt poller hoặc `deleteWebhook` bên SquarePilot trước.
- Đổi (revoke) token → cập nhật **cả hai nơi**: `notify.json` trên mini PC và `.env` trên Mac.

## 5. Map Telegram → Zalo cho Phase 6 (đề xuất)

| PRD / plan (Telegram) | Zalo |
|---|---|
| Inline keyboard `Đăng` / `Viết lại` / `Đổi visual` / `Bỏ` | Lệnh chữ `d` / `v` / `a` / `b` + mã draft |
| `callback_data` = draft id | Mã ngắn trong lệnh (vd. `K7`) |
| Ảnh + draft + NFC/NFD + gate trong một tin | Tin 1: ảnh + caption ngắn (mã, trend, mode, nguồn, gate, NFC/NFD, chi phí). Tin 2…n: draft nguyên văn, tách ≤ 1900 ký tự |
| Bấm Bỏ → hỏi lý do bằng nút | Danh sách lý do đánh số in sẵn trong tin; trả lời `b K7 2` |
| Long-poll `getUpdates` nền | Long-poll liên tục hoặc webhook (§6.1) |

**Giao thức lệnh đề xuất:**

- Mỗi draft có **mã 2–3 ký tự**, không trùng giữa các draft chưa hết hạn. Tránh ký tự dễ nhầm
  (`0/O`, `1/I/l`).
- Chuẩn hóa tin trước khi so khớp: lowercase → NFD → bỏ dấu → `đ`→`d` → gộp khoảng trắng.
  Huynh gõ "Đăng K7" hay "dang k7" đều được.
- Lệnh:
  - `d K7` hoặc `dang K7` → Đăng
  - `v K7` hoặc `viet K7` → Viết lại
  - `a K7` hoặc `anh K7` → Đổi visual
  - `b K7 <số>` hoặc `bo K7 <số>` → Bỏ với lý do số `<số>`. Thiếu số thì bot gửi lại danh sách lý do
  - `?` → hướng dẫn
- Chỉ có **đúng 1** draft đang chờ thì được bỏ mã (gõ `d` là đủ). Từ 2 draft trở lên thì
  bắt buộc có mã.
- Footer mẫu ở cuối tin draft:

  ```
  [K7] Trả lời: d K7 = Đăng · v K7 = Viết lại · a K7 = Đổi visual · b K7 <số> = Bỏ
  Lý do bỏ: 1 … · 2 … · 3 … · 4 khác
  ```

- **Luôn trả lời xác nhận (ACK)**: `✅ Đã đăng K7 (square_post_id …)`, `⌛ K7 đã hết hạn`,
  `❓ Không hiểu lệnh — gửi ? để xem hướng dẫn`. Gửi lệnh mà ~1 phút không thấy ACK thì có
  thể tin đã rơi (§3) → gửi lại. Vì vậy **mọi lệnh phải idempotent**.
- **Đăng idempotent**: chuyển `drafts.status` từ `pending` sang `approved` trong **một
  transaction, trước** khi gọi Square. Lệnh lặp lại thấy status không còn `pending` thì báo
  trạng thái hiện tại, không đăng lần hai. Dedupe thêm theo `message.message_id`.
- Giữ acceptance test Phase 6 "không có code path nào đăng được mà không qua callback", đổi
  thành: không có code path nào đăng được mà không có lệnh hợp lệ từ `ZALO_CHAT_ID`.

## 6. Hai việc bên Mac phải chốt

### 6.1 Nhận tin

- **A. Long-poll liên tục.** Chạy bằng plist launchd riêng có `KeepAlive`, tách khỏi job 3 lần/ngày.
  - Ưu: không cần URL public, giữ nguyên kiến trúc local-first của plan.
  - Nhược: docs nói getUpdates dành cho dev/test. Tin gửi đúng khe giữa hai lần poll, hoặc lúc
    process đang restart, có thể rơi. ACK + gửi lại giảm được rủi ro này.
- **B. Webhook qua Cloudflare Tunnel (hoặc ngrok).**
  - Ưu: docs khuyên dùng cho Prod, không rơi tin khi server đang sống.
  - Nhược: cần tunnel có URL cố định. Quick tunnel đổi URL mỗi lần chạy, nên phải `setWebhook`
    lại mỗi lần khởi động. Mac ngủ thì vẫn rơi tin. Thêm một service phải trông.
- **Đệ nghiêng A.** Chỉ 1 bài/ngày, lại có ACK, nên lỡ rơi tin chỉ phiền chứ không hại. Thấy
  rơi tin thật thì mới chuyển B.

### 6.2 PNG local → Zalo

**Đã thử 08/10 trên bot này** (PNG 540×675):

| Cách gửi | Kết quả |
|---|---|
| `multipart/form-data` (`chat_id`, `photo=@file.png`) | ❌ `"The chat_id must not be empty"` — Zalo không đọc multipart |
| JSON, `photo: "data:image/png;base64,…"` | ❌ `"The photo must start with http:// or https://"` |
| JSON, `photo: "https://…png"` | ✅ `ok:true`, `message_type: CHAT_PHOTO` |

→ PNG local phải có **URL public** trước khi gửi. Các cách lấy URL:

- **A. Upload lên object storage** (Cloudflare R2 / S3), public-read hoặc presigned, tên file
  ngẫu nhiên, tự xóa sau vài ngày.
  - Ưu: ổn định, không phụ thuộc Mac đang online.
  - Nhược: thêm credential và một dịch vụ cloud.
  - Chưa thử: Zalo có nhận URL presigned có query string dài không.
- **B. Serve PNG từ Mac qua tunnel.** Chỉ hợp lý khi đã chọn webhook ở 6.1.
  - Ưu: không thêm dịch vụ.
  - Nhược: chưa biết Zalo có tải ảnh về giữ lại lúc gửi không; nếu không, Mac tắt là ảnh hỏng.
- **C. Chỉ gửi text, không gửi ảnh.** Phá US#52 (duyệt trên điện thoại có kèm ảnh).
- **Đệ nghiêng A.** Đi kèm với lựa chọn long-poll ở 6.1A (không cần tunnel), và ảnh không chết
  theo Mac.

## 7. Test

- Cho `ZALO_API_BASE` cấu hình được để vitest trỏ sang fake server. Worker cũng làm vậy:
  `api_base` trong `notify.json` + fake bot API.
- Các case nên có:
  - Chuẩn hóa update (object / mảng / rỗng)
  - Lọc `chat_id` lạ
  - Parse lệnh có dấu / không dấu
  - Thiếu mã khi có 1 draft so với khi có nhiều draft
  - Lệnh `b` thiếu số lý do
  - Draft đã hết hạn
  - Đăng lặp 2 lần → chỉ đăng 1
  - Tách tin ≤ 1900 ký tự
  - Token không xuất hiện trong log
- Thử thật: `getMe` → `sendMessage` → bật poller → nhắn lệnh từ điện thoại → thấy ACK.

## 8. Việc sửa tài liệu bên SquarePilot

PRD §2 bước 8, §4.4 (Auth), US#52–57; plan Phase 6 (`telegram-approver`) và Phase 7 ("Telegram
báo lý do dừng"). Nên đổi thành interface `approver` / `notifier` có implementation Zalo, giống
PRD §4.1 "Publisher là một interface".

## Nguồn

- Zalo Bot docs: <https://bot.zapps.me/docs/> · [sendMessage](https://bot.zapps.me/docs/apis/sendMessage/) ·
  [sendPhoto](https://bot.zapps.me/docs/apis/sendPhoto/) · [getUpdates](https://bot.zapps.me/docs/apis/getUpdates/) ·
  [setWebhook](https://bot.zapps.me/docs/apis/setWebhook/) · [Webhook](https://bot.zapps.me/docs/webhook/)
- Ghi chú tích hợp bên thứ ba (OpenClaw): <https://docs.openclaw.ai/channels/zalo.md>
- Code worker: `scripts/notify.ps1` (gửi), `scripts/notify-setup.ps1` (lấy `chat_id` qua getUpdates)
