# Crawl Data Telegram

## Đây là gì?

Đây là một tool giúp bạn **thu thập dữ liệu từ Telegram** một cách tự động. Thay vì phải đọc tin nhắn từng channel một trên điện thoại hay máy tính, tool này sẽ tự động:

- Lấy **tất cả tin nhắn** từ một channel hoặc group Telegram
- Thu thập **thông tin chi tiết** của mỗi tin nhắn: ai gửi, giờ nào, có bao nhiêu reaction, bao nhiêu lượt xem
- Phân tích **ai hoạt động nhiều nhất** trong group
- **Đếm admin** và xem thông tin group

## Tại sao cần tool này?

Ví dụ bạn muốn:
- Biết một channel Telegram nào đó nói gì trong 30 ngày qua
- Thống kê xem ai là người hoạt động nhất trong group của bạn
- Lưu lại tin nhắn quan trọng để đọc lại sau
- Phân tích xu hướng thảo luận trong một cộng đồng

→ Tool này giúp bạn làm tất cả điều đó.

## Cách hoạt động

```
Bạn gửi yêu cầu (link channel/group, số ngày muốn lấy)
        ↓
Code chạy trên Modal (serverless platform - không cần server riêng)
        ↓
Telethon (thư viện Python) kết nối Telegram
        ↓
Trả về kết quả: tin nhắn, thống kê, phân tích
```

## Hướng dẫn sử dụng

### Bước 1: Cài đặt

```bash
pip install -r requirements.txt
```

### Bước 2: Lấy Telegram API

1. Vào https://my.telegram.org → Đăng nhập
2. Vào "API development tools"
3. Lấy `API_ID` và `API_HASH`

### Bước 3: Tạo Secret trên Modal

```bash
modal secret create telegram-secrets
# Thêm API_ID và API_HASH vào
```

### Bước 4: Deploy lên Modal

```bash
modal deploy modal_crawler_by_link.py
modal deploy modal_user_message.py
```

### Bước 5: Sử dụng

#### Crawl tin nhắn từ một channel

```bash
curl -X POST https://your-app.modal.app/crawl \
  -H "Content-Type: application/json" \
  -d '{"link": "https://t.me/channel_name", "days": 30}'
```

#### Phân tích một group

```bash
curl -X POST https://your-app.modal.app/analyze \
  -H "Content-Type: application/json" \
  -d '{"group_link": "https://t.me/group_name", "days": 30}'
```

## Các file trong project

| File | Mô tả |
|------|-------|
| `modal_crawler_by_link.py` | Crawl tin nhắn từ channel/group. Ví dụ: lấy 30 ngày tin nhắn từ một channel Telegram |
| `modal_user_message.py` | Phân tích user trong group. Ví dụ: biết ai là admin, ai gửi nhiều tin nhắn nhất, thống kê reactions |
| `requirements.txt` | Danh sách thư viện cần cài (modal, telethon, cryptg) |

## Ví dụ kết quả

### Kết quả crawl tin nhắn

```json
{
  "platform": "telegram",
  "type": "single_channel_crawl",
  "input_link": "https://t.me/example_channel",
  "data": {
    "info": {
      "title": "Example Channel",
      "username": "example_channel",
      "participants_count": 15000
    },
    "crawl": {
      "total_items": 150,
      "items": [
        {
          "message_id": 123,
          "caption": "Tin nhắn đầu tiên",
          "date": "2024-03-01T10:00:00",
          "views": 1500,
          "reaction_total": 45
        }
      ]
    }
  }
}
```

### Kết quả phân tích user

```json
{
  "admin_list": ["User A", "User B"],
  "user_ranking": [
    {"user": "User C", "message_count": 150},
    {"user": "User D", "message_count": 120}
  ],
  "top_users": [...]
}
```

## Requirements

- Python 3.11 trở lên
- Modal account (đăng ký miễn phí tại modal.com)
- Telegram API credentials (lấy từ my.telegram.org)
- Thư viện: modal, telethon, cryptg

## Cài đặt Modal CLI

```bash
pip install modal
modal setup
```

## Lưu ý

- **Không cần server riêng** - Code chạy trên Modal, bạn chỉ cần deploy và gọi API
- **Giới hạn** - Telegram có giới hạn rate khi crawl quá nhiều tin nhắn
- **Privacy** - Session và data được lưu trữ an toàn trên Modal Volume

---

Made with Modal + Telethon
