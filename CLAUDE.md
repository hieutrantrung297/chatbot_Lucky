# Lucky Cake Chatbot — CLAUDE.md

Chatbot Facebook Messenger tự động cho tiệm bánh kem Lucky.
Tự động tư vấn, giải đáp và chốt đơn hàng — không cần nhắn tin thủ công.

---

## Trạng thái dự án

**Giai đoạn:** Đang chạy local — hoạt động đầy đủ, chưa deploy Render.com  
**Cập nhật lần cuối:** 2026-05-30

---

## Những gì đã hoàn thành

### Core code (100%)
| File | Trạng thái | Mô tả |
|------|-----------|-------|
| `app/main.py` | ✅ Hoàn thành | FastAPI webhook GET/POST, signature verify, BackgroundTasks |
| `app/conversation.py` | ✅ Hoàn thành | State machine, per-user async lock, auto-reset timeout, session separator |
| `app/order_handler.py` | ✅ Hoàn thành | Thu thập đơn tuần tự, bước xác nhận, sửa field, validate SĐT/ngày |
| `app/ai_client.py` | ✅ Hoàn thành | GitHub Models API (OpenAI-compatible), history management |
| `app/messenger.py` | ✅ Hoàn thành | Facebook Graph API — gửi/nhận/verify webhook |
| `app/sheets.py` | ✅ Hoàn thành | Google Sheets integration qua gspread + Service Account |
| `app/catalog.py` | ✅ Hoàn thành | Load catalog.json, get_price, get_catalog_text |
| `app/models.py` | ✅ Hoàn thành | Pydantic v2 models: Order, OrderInProgress, ConversationRecord |
| `app/config.py` | ✅ Hoàn thành | pydantic-settings, load .env, cached singleton |

### Data & Prompts (100%)
| File | Trạng thái | Mô tả |
|------|-----------|-------|
| `data/catalog.json` | ✅ Hoàn thành | 8 loại bánh mẫu, giá theo size, chính sách cửa hàng |
| `prompts/system_prompt.txt` | ✅ Hoàn thành | System prompt tiếng Việt, inject catalog + state |
| `data/conversations.json` | ✅ Hoàn thành | Lưu state runtime per user |

### Deployment config (100%)
| File | Trạng thái | Mô tả |
|------|-----------|-------|
| `requirements.txt` | ✅ Hoàn thành | FastAPI, OpenAI SDK, gspread, pydantic-settings... |
| `render.yaml` | ✅ Hoàn thành | Render.com deploy config |
| `Procfile` | ✅ Hoàn thành | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| `.env.example` | ✅ Hoàn thành | Template đầy đủ với hướng dẫn lấy từng key |
| `.gitignore` | ✅ Hoàn thành | Bảo vệ `.env` và data runtime |

---

## Trạng thái từng phần

### Luồng hội thoại
```
Khách nhắn tin
    ↓
conversation.py (state machine)
    ├── state = CONFIRMING  →  process_confirming() — xác nhận / sửa / hủy
    ├── state = ORDERING    →  process_ordering()   — thu thập tuần tự
    └── state khác          →  ai_client.py (GPT-4o-mini tự do)
                                        ↓
                                messenger.py gửi reply
                                        ↓
                                sheets.py ghi đơn (khi chốt xong)
```

### Luồng đặt hàng (đã cập nhật)
```
tên → SĐT → loại bánh → size → hương vị → [chữ trên bánh*] → ngày giao → địa chỉ
    → TÓM TẮT ĐƠN (hỏi xác nhận)
        ├── "xác nhận/ok/đúng" → chốt đơn → Google Sheets → gửi xác nhận
        ├── "sửa tên/ngày/..." → reset field đó → hỏi lại
        └── "hủy"              → hủy đơn
```
*Chỉ hỏi khi là bánh kem hoặc bánh sinh nhật.

### Logic đặc biệt: chữ ghi trên bánh
- **Bánh kem / bánh sinh nhật** (keyword: "bánh kem", "sinh nhật") → hỏi nội dung ghi lên bánh
- **Bánh khác** (bánh mì, bánh ngọt...) → bỏ qua bước này
- Hàm kiểm tra: `needs_cake_message(cake_type)` trong `app/order_handler.py`

### Logic quản lý context hội thoại
- **Auto-reset timeout:** Nếu state = ORDERING / CONFIRMING / CONFIRMED và không có tin nhắn quá `ORDERING_TIMEOUT_HOURS` (hiện = 1 phút để test, đổi thành 120+ phút khi production) → reset state, xóa message_history, bắt đầu mới
- **Session separator:** Sau khi chốt đơn xong, inject dòng `[ĐƠN HÀNG ĐÃ HOÀN TẤT...]` vào history → AI hiểu đơn cũ đã xong, không tiếp tục context cũ

### Google Sheets columns
`Mã Đơn | Thời Gian | Tên KH | SĐT | Loại Bánh | Size | Hương Vị | Chữ Trên Bánh | Ngày Giao | Địa Chỉ | Ghi Chú | Tổng Tiền | Tiền Cọc | Trạng Thái`

---

## Đã hoàn thành & kiểm tra thực tế

### Infrastructure đã chạy
- [x] Facebook Business Page tạo xong
- [x] Facebook Developer App tạo xong, Messenger configured
- [x] PAGE_ACCESS_TOKEN + APP_SECRET đã lấy và điền vào `.env`
- [x] GITHUB_TOKEN (Models API) đã cấu hình
- [x] Google Service Account tạo xong, JSON key đã điền vào `.env`
- [x] Google Spreadsheet tạo xong, đã share cho Service Account
- [x] ngrok chạy tunnel → webhook Facebook kết nối thành công
- [x] uvicorn chạy local tại port 8000

### Đã test và xác nhận hoạt động
- [x] Webhook verify (GET) thành công
- [x] Nhận tin nhắn từ Facebook (POST) thành công
- [x] AI trả lời tự nhiên tiếng Việt
- [x] Luồng đặt hàng đầy đủ + bước xác nhận trước khi chốt
- [x] Sửa field trong lúc xác nhận ("sửa ngày", "sửa địa chỉ"...)
- [x] Google Sheets ghi đơn hàng thành công
- [x] Auto-reset đơn bị bỏ ngang sau timeout
- [x] Không bị lặp context đơn cũ khi khách quay lại sau nhiều ngày
- [x] Người dùng khác (Moderator của Page) nhắn tin được trong Development mode

---

## Bước tiếp theo

### 1. Tùy chỉnh catalog & thông tin tiệm thực tế

Chỉnh `data/catalog.json`:
- Tên, mô tả, giá sản phẩm thực tế
- Giờ mở cửa, địa chỉ tiệm, chính sách giao hàng
- Thêm/xóa loại bánh

Thông tin cần hỏi chủ tiệm:
- Đặt trước tối thiểu mấy ngày? (hiện: 2 ngày)
- Phí giao hàng? Khu vực giao?
- Số tài khoản ngân hàng để thanh toán

### 2. Đổi timeout auto-reset về giá trị thực tế

Trong `app/conversation.py`, dòng 15:
```python
ORDERING_TIMEOUT_HOURS = 1   # ← đang để 1 phút để test
```
Đổi thành số phút phù hợp (VD: `120` = 2 tiếng, `1440` = 24 tiếng).

### 3. Deploy lên Render.com (chạy 24/7, không cần giữ máy)

```bash
# Push code lên GitHub
git add . && git commit -m "Production ready"
git remote add origin https://github.com/<user>/chatbot_lucky.git
git push -u origin main

# Render.com → New Web Service → kết nối GitHub repo
# Điền env vars → Deploy → lấy URL https://<app>.onrender.com
# Cập nhật Webhook URL trên Facebook Developer Dashboard
```

**Lưu ý:** Render.com free tier sleep sau 15 phút không có traffic → tin nhắn đầu tiên chậm ~30 giây.

### 4. App Review để public (ai cũng nhắn được)

1. `developers.facebook.com` → App → **App Review** → **Permissions and Features**
2. Yêu cầu permission: **`pages_messaging`**
3. Cung cấp: video demo (~1-2 phút) + mô tả use case + Privacy Policy URL
4. Submit → Meta review trong vài ngày đến 2 tuần
5. Sau khi approved → bật **Live mode** → public

---

## Quyết định quan trọng & lý do

| Quyết định | Lý do |
|-----------|-------|
| **GPT-4o-mini qua GitHub Models API** | Miễn phí với GitHub PAT, đủ chất lượng cho tư vấn bánh, không cần billing |
| **Google Sheets** (thay vì DB) | Chủ tiệm dễ xem đơn hàng trực tiếp, không cần học thêm công cụ mới |
| **Render.com** (thay vì Railway) | Free tier hoàn toàn miễn phí (Railway có giới hạn $5 credit) |
| **Xử lý async với BackgroundTasks** | Facebook yêu cầu webhook trả về 200 trong <5 giây; AI response có thể mất 3-8 giây |
| **JSON file cho conversation state** | Đơn giản, không cần setup DB, phù hợp quy mô nhỏ (<100 đơn/ngày) |
| **Tách `order_handler` khỏi AI** | Thu thập đơn hàng cần chính xác 100% — dùng code xác định thay vì AI có thể hallucinate |
| **Per-user asyncio.Lock** | Tránh race condition khi 2 tin nhắn từ cùng 1 user đến gần nhau |
| **Keyword detect "bánh kem/sinh nhật"** | Quy tắc đơn giản, rõ ràng hơn dùng AI để classify — ít lỗi hơn |
| **Bước xác nhận trước khi chốt đơn** | Tránh chốt nhầm thông tin; cho phép sửa field mà không cần đặt lại từ đầu |
| **Session separator sau khi chốt đơn** | AI không đọc context đơn cũ khi khách quay lại sau nhiều ngày đặt đơn mới |
| **Không nhắc tiền cọc trong bot** | Bộ phận tiệm sẽ liên hệ trực tiếp — bot chỉ ghi nhận đơn, không xử lý thanh toán |

---

## Lưu ý quan trọng khi chỉnh sửa

- **Thêm loại bánh mới:** Chỉ cần chỉnh `data/catalog.json` — không cần đổi code
- **Đổi câu hỏi đặt hàng:** Chỉnh `FIELD_QUESTIONS` trong `app/order_handler.py`
- **Đổi tone AI:** Chỉnh `prompts/system_prompt.txt`
- **Bật lại thông báo tiền cọc:** Tìm `# DEPOSIT_NOTICE` trong `app/order_handler.py`, uncomment 2 dòng
- **Đổi timeout reset:** Chỉnh `ORDERING_TIMEOUT_HOURS` trong `app/conversation.py` (đơn vị: phút)
- **Thêm field đơn hàng:** Cập nhật `OrderInProgress` (models.py) + `FIELD_QUESTIONS` + `next_missing_field` (order_handler.py)
- **Migrate sang DB:** Chỉ cần thay thế `_load_all`/`_save_all` trong `app/conversation.py` và `append_order` trong `app/sheets.py`
