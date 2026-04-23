# Crawl Data Telegram

Tool crawl dữ liệu từ Telegram bằng Modal (serverless platform).

## Cái gì?

Dự án này giúp bạn:

- **Thu thập tin nhắn** từ bất kỳ Telegram channel/group nào
- **Phân tích user** trong group: ai hoạt động nhiều nhất, ai là admin
- **Lưu trữ & xem lại** dữ liệu sau này

## Cách hoạt động

```
Telegram → Modal (Python) → API response
```

Code chạy trên Modal (serverless), không cần VPS/server riêng.

## Bắt đầu

### 1. Cài đặt

```bash
pip install -r requirements.txt
```

### 2. Cấu hình Telegram API

Tạo secret trên Modal:
```bash
modal secret create telegram-secrets
# Thêm API_ID và API_HASH từ my.telegram.org
```

### 3. Deploy

```bash
modal deploy modal_crawler_by_link.py
modal deploy modal_user_message.py
```

## Ví dụ sử dụng

### Crawl tin nhắn từ channel

```bash
curl -X POST https://your-app.modal.app/crawl \
  -H "Content-Type: application/json" \
  -d '{"link": "https://t.me/channel_name", "days": 30}'
```

### Phân tích group

```bash
curl -X POST https://your-app.modal.app/analyze \
  -H "Content-Type: application/json" \
  -d '{"group_link": "https://t.me/group_name", "days": 30}'
```

## Các file chính

| File | Mô tả |
|------|-------|
| `modal_crawler_by_link.py` | Crawl tin nhắn từ channel/group qua link |
| `modal_user_message.py` | Phân tích user & thống kê group |

## Requirements

- Python 3.11+
- Modal account
- Telegram API (lấy từ my.telegram.org)

---

Made with Modal + Telethon
