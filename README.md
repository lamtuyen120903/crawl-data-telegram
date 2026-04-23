# BD_Bingx - Telegram Crawler & Analytics

Crawl và phân tích dữ liệu Telegram bằng Modal (serverless Python platform).

## Tính năng

### `modal_crawler_by_link.py`
- Crawl tin nhắn từ một channel/groups qua link hoặc username
- Thu thập: tin nhắn, reactions, views, forwards, replies
- Hỗ trợ download media (ảnh, file)
- Lọc theo ngày (mặc định 30 ngày)
- Web endpoint: `POST /crawl`

### `modal_user_message.py`
- Phân tích group: danh sách admin, ranking user, top tin nhắn
- Thống kê chi tiết per user
- Web endpoint: `POST /analyze`

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy local

```bash
# Tạo session Telegram
python modal_crawler_by_link.py

# Deploy lên Modal
modal deploy modal_crawler_by_link.py
modal deploy modal_user_message.py
```

## API Endpoints

### Crawl by Link
```bash
curl -X POST https://your-app.modal.app/crawl \
  -H "Content-Type: application/json" \
  -d '{"link": "https://t.me/channel_name", "days": 30, "download_media": false}'
```

### User Analytics
```bash
curl -X POST https://your-app.modal.app/analyze \
  -H "Content-Type: application/json" \
  -d '{"group_link": "https://t.me/group_name", "days": 30}'
```

## Secrets cần thiết

Tạo Modal secret `telegram-secrets` với:
- `API_ID`: Telegram API ID
- `API_HASH`: Telegram API Hash

## Volume

- `telegram-session-link`: Lưu session Telegram (crawler by link)
- `telegram-session-analytics`: Lưu session Telegram (analytics)

## Yêu cầu

- Python 3.11+
- Modal account & CLI
- Telegram API credentials
