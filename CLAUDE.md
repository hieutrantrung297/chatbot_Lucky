# Lucky Cake Chatbot — CLAUDE.md

Chatbot Facebook Messenger tự động cho tiệm bánh kem Lucky.
Tự động tư vấn, giải đáp và chốt đơn hàng — không cần nhắn tin thủ công.

---

## Trạng thái dự án

**Giai đoạn:** Code hoàn chỉnh, chưa deploy  
**Cập nhật lần cuối:** 2026-04-13

---

## Những gì đã hoàn thành

### Core code (100%)
| File | Trạng thái | Mô tả |
|------|-----------|-------|
| `app/main.py` | ✅ Hoàn thành | FastAPI webhook GET/POST, signature verify, BackgroundTasks |
| `app/conversation.py` | ✅ Hoàn thành | State machine, per-user async lock, route tới AI hoặc order handler |
| `app/order_handler.py` | ✅ Hoàn thành | Thu thập đơn tuần tự, validate SĐT/ngày, logic chữ trên bánh |
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
| `data/conversations.json` | ✅ Hoàn thành | File trống sẵn sàng (lưu state runtime) |

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
    ├── state = ORDERING  →  order_handler.py (thu thập tuần tự)
    └── state khác        →  ai_client.py (GPT-4o-mini tự do)
                                    ↓
                            messenger.py gửi reply
                                    ↓
                            sheets.py ghi đơn (khi hoàn tất)
```

### Logic đặc biệt: chữ ghi trên bánh
- **Bánh kem / bánh sinh nhật** (keyword: "bánh kem", "sinh nhật") → hỏi nội dung ghi lên bánh
- **Bánh khác** (bánh mì, bánh ngọt...) → bỏ qua bước này
- Hàm kiểm tra: `needs_cake_message(cake_type)` trong `app/order_handler.py`

### Luồng đặt hàng
```
tên → SĐT → loại bánh → size → hương vị → [chữ trên bánh*] → ngày giao → địa chỉ
```
*Chỉ hỏi khi là bánh kem hoặc bánh sinh nhật.

### Google Sheets columns
`Mã Đơn | Thời Gian | Tên KH | SĐT | Loại Bánh | Size | Hương Vị | Chữ Trên Bánh | Ngày Giao | Địa Chỉ | Ghi Chú | Tổng Tiền | Tiền Cọc | Trạng Thái`

---

## Bước tiếp theo (theo thứ tự)

### 1. Chuẩn bị credentials (làm trước khi chạy bất cứ thứ gì)

**Facebook:**
- [ ] Tạo Facebook Business Page tại `facebook.com/pages/create`
- [ ] Vào `developers.facebook.com` → Create App → Business → thêm Messenger
- [ ] Tạo Page Access Token → lấy `PAGE_ACCESS_TOKEN`
- [ ] Lấy `APP_SECRET` từ App Settings > Basic

**GitHub Models API:**
- [ ] Vào `github.com` → Settings → Developer Settings → Fine-grained PAT
- [ ] Tạo token với permission: **Models → Read**
- [ ] Lưu làm `GITHUB_TOKEN`

**Google Sheets:**
- [ ] Tạo Google Spreadsheet mới (tên sheet tab: "Đơn Hàng")
- [ ] Google Cloud Console → tạo Service Account → download JSON key
- [ ] Share Spreadsheet với email Service Account (role: Editor)
- [ ] Lấy Spreadsheet ID từ URL

### 2. Cấu hình local

```bash
# Tạo file .env từ template
cp .env.example .env
# Điền đầy đủ các giá trị trong .env

# Cài dependencies
pip install -r requirements.txt

# Chạy server local
uvicorn app.main:app --reload --port 8000
```

### 3. Test local với ngrok

```bash
# Terminal 2: mở tunnel
ngrok http 8000

# Cấu hình webhook Facebook:
# Callback URL: https://xxxx.ngrok.io/webhook
# Verify Token: (giá trị VERIFY_TOKEN trong .env của bạn)
# Subscribe: messages, messaging_postbacks

# Test: gửi tin nhắn từ tài khoản test Facebook
```

### 4. Deploy lên Render.com

```bash
# 1. Tạo repo GitHub, push code
git init && git add . && git commit -m "Initial commit"
git remote add origin https://github.com/<user>/chatbot_lucky.git
git push -u origin main

# 2. Render.com → New Web Service → kết nối GitHub repo
# 3. Điền tất cả env vars trong Render dashboard
# 4. Deploy → lấy URL https://<app>.onrender.com
# 5. Cập nhật Webhook URL trên Facebook Developer Dashboard
```

### 5. Tùy chỉnh catalog sản phẩm

Chỉnh `data/catalog.json` để cập nhật:
- Tên và mô tả sản phẩm thực tế của tiệm
- Giá thực tế theo từng size
- Thêm/xóa loại bánh
- Cập nhật thông tin chính sách (giờ mở cửa, địa chỉ...)

---

## Quyết định kiến trúc quan trọng

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

---

## Lưu ý quan trọng khi chỉnh sửa

- **Thêm loại bánh mới:** Chỉ cần chỉnh `data/catalog.json` — không cần đổi code
- **Đổi câu hỏi đặt hàng:** Chỉnh `FIELD_QUESTIONS` trong `app/order_handler.py`
- **Đổi tone AI:** Chỉnh `prompts/system_prompt.txt`
- **Thêm field đơn hàng:** Cập nhật `OrderInProgress` (models.py) + `FIELD_QUESTIONS` + `next_missing_field` (order_handler.py)
- **Migrate sang DB:** Chỉ cần thay thế `_load_all`/`_save_all` trong `app/conversation.py` và `append_order` trong `app/sheets.py`
- **Render.com free tier** sẽ sleep sau 15 phút không có traffic → tin nhắn đầu tiên có thể chậm ~30 giây khi wake up
