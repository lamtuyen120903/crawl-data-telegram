# Crawl Data Telegram

## What is this?

This is a tool that helps you **automatically collect data from Telegram**. Instead of manually reading messages from each channel on your phone or computer, this tool can:

- Fetch **all messages** from a Telegram channel or group
- Collect **detailed information** for each message: sender, timestamp, reactions, views
- Analyze **who is most active** in the group
- **Count admins** and view group information

## Why do you need this tool?

For example, if you want to:
- Know what a Telegram channel has been saying in the past 30 days
- Find out who is the most active member in your group
- Save important messages for later reference
- Analyze discussion trends in a community

→ This tool helps you do all of that.

## How it works

```
You send a request (channel/group link, number of days)
        ↓
Code runs on Modal (serverless platform - no dedicated server needed)
        ↓
Telethon (Python library) connects to Telegram
        ↓
Returns results: messages, statistics, analysis
```

## Setup Guide

### Step 1: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Get Telegram API credentials

1. Go to https://my.telegram.org → Login
2. Navigate to "API development tools"
3. Copy your `API_ID` and `API_HASH`

### Step 3: Create Secret on Modal

```bash
modal secret create telegram-secrets
# Add API_ID and API_HASH
```

### Step 4: Deploy to Modal

```bash
modal deploy modal_crawler_by_link.py
modal deploy modal_user_message.py
```

### Step 5: Usage

#### Crawl messages from a channel

```bash
curl -X POST https://your-app.modal.app/crawl \
  -H "Content-Type: application/json" \
  -d '{"link": "https://t.me/channel_name", "days": 30}'
```

#### Analyze a group

```bash
curl -X POST https://your-app.modal.app/analyze \
  -H "Content-Type: application/json" \
  -d '{"group_link": "https://t.me/group_name", "days": 30}'
```

## Project Files

| File | Description |
|------|-------------|
| `modal_app.py` | **Search channels by keyword** - Automatically search Telegram channels by keyword (e.g., "crypto signals"), then crawl all found channels |
| `modal_crawler_by_link.py` | Crawl messages from a specific channel/group via link. Example: fetch 30 days of messages from a Telegram channel |
| `modal_user_message.py` | Analyze users in a group. Example: identify admins, top message senders, reaction statistics |
| `requirements.txt` | List of required libraries (modal, telethon, cryptg) |

---

## How Each Module Works

### modal_app.py - Search channels by keyword

```
Input: keywords = "crypto signals, airdrop"
    ↓
Telethon SearchRequest (find channels containing keyword)
    ↓
Collect usernames (up to 100/channel)
    ↓
Crawl messages from all found channels
    ↓
Output: Channel list + messages
```

### modal_crawler_by_link.py - Crawl a specific channel

```
Input: link = "https://t.me/channel_name"
    ↓
Access channel via username/link
    ↓
Crawl all messages (filter by date)
    ↓
Output: Channel details + message list
```

### modal_user_message.py - Analyze group

```
Input: group_link = "https://t.me/group_name"
    ↓
Get admin list
    ↓
Rank users by message count
    ↓
Collect top messages
    ↓
Output: Admins, User ranking, Top messages
```

## Example Results

### Message crawl result

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
          "caption": "First message",
          "date": "2024-03-01T10:00:00",
          "views": 1500,
          "reaction_total": 45
        }
      ]
    }
  }
}
```

### User analysis result

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

## N8N Workflows

This project includes **4 N8N workflows** to connect crawl-data-telegram with other services like Google Sheets, Telegram Bot, and Gemini AI.

### Workflows Overview

| Workflow | Description |
|----------|-------------|
| `Crawl channel - combine` | Crawl multiple channels simultaneously by keyword, with Gemini AI generating additional related keywords |
| `Crawl Channel BD` | Crawl channel data + analyze content using AI (Summary, Mention, Spam, Referral link) |
| `Ana Channel` | Detailed channel analysis: info, reactions, views, subscribers |
| `Crawl Group BD_ tele bot` | Telegram bot that receives commands and returns group info: admins, user ranking, top messages |
| `Crawl Group` | Crawl channels by keyword (Gemini generates 10 VN+ID keywords), analyze content with AI, save to Google Sheets |

---

### 1. Crawl channel - combine

**Purpose:** Crawl multiple channels simultaneously based on keyword list, automatically generating related keywords using Gemini AI.

**Flow:**
```
Webhook (receive keyword from user)
    ↓
Google Sheets (read exclusion keyword list)
    ↓
Gemini AI (generate 5-10 related keywords: crypto signals, airdrop, trading...)
    ↓
HTTP Request → Modal API (crawl channels by keyword)
    ↓
Google Sheets (save results to Output_Data)
```

**Input:** `POST /crawl-keyword-tele` with keyword in body
**Output:** Crawl results saved to Google Sheets
<img width="889" height="585" alt="Screenshot 2026-04-23 at 14 10 48" src="https://github.com/user-attachments/assets/30a310b5-02b6-4fd4-a56f-43421267f9ef" />
<img width="1185" height="595" alt="Screenshot 2026-04-23 at 14 11 29" src="https://github.com/user-attachments/assets/8c10ef63-01e2-45b4-a1b0-76293a8be10b" />


---

### 2. Crawl Channel BD

**Purpose:** Crawl data from one or multiple channels, then analyze content using AI to extract important information.

**Flow:**
```
Google Sheets (read channel list to crawl)
    ↓
Loop Over Items (iterate through each channel)
    ↓
HTTP Request → Modal API (crawl messages)
    ↓
Information Extractor (Gemini AI analyzes):
    - Summary: Channel content summary
    - Mention: Which exchanges are mentioned (BingX, Binance, Bybit...)
    - Spam: Count spam/irrelevant messages
    - Referral link: Find referral links in messages
    - Language: Channel language
    ↓
Google Sheets (save analysis results)
```

**Input:** Google Sheets containing channel list (Keyword range)
**Output:**
- ID, Name, Link, Date Created
- Summary, Spam, Subscribers, Frequency
- Reaction, View, Mention, Referral link
<img width="1238" height="355" alt="Screenshot 2026-04-23 at 14 10 12" src="https://github.com/user-attachments/assets/d6705ac6-1fdf-4e86-b96d-4d76bfe92adc" />


---

### 3. Ana Channel

**Purpose:** Detailed analysis of a specific channel: basic info, reactions/views statistics, and content.

**Flow:**
```
Google Sheets (get Username_Channel and Days from input)
    ↓
HTTP Request → Modal API (crawl channel)
    ↓
Information Extractor (AI analyzes):
    - Mention: Exchanges mentioned
    - Spam: Spam messages
    - Referral link: Referral links
    - Referral BingX or not: Has BingX referral link or not
    - Language: Language
    - Summary: Content summary
    ↓
Google Sheets (update to Outpu_ChannelDatabylink)
```

**Input:** `Username_Channel` + `Days` from Google Sheets
**Output:**
- ID, Platform, Name, Link
- Date Created, Reaction, Frequency, View
- Mention, Subscribers, Run Date, Spam
- Referral link, Referral BingX or not, Language, Summary
<img width="1069" height="218" alt="Screenshot 2026-04-23 at 14 12 10" src="https://github.com/user-attachments/assets/08ac9b93-abcf-4fa0-b412-7360537525d5" />

---

### 4. Crawl Group BD_ tele bot

**Purpose:** Telegram bot that allows users to send commands to analyze a group: view admins, user ranking, top messages.

**Flow:**
```
Telegram Trigger (receive message from user)
    ↓
HTTP Request → Modal API (analyze group)
    ↓
Code (process data):
    - Extract Admin list
    - Split user ranking into chunks (23 users per chunk)
    - Extract top messages
    ↓
Loop Over Items (iterate through each user)
    ↓
Information Extractor (AI analyzes user behavior: Whale or not, losses/gains)
    ↓
Send Telegram messages (send results back to user)
```

**Features:**
- Receive commands from Telegram, analyze instantly
- Send results back to Telegram:
  - Admin list
  - User ranking (split into chunks of 23 users)
  - Whale behavior analysis for each user
- Analyze message content to identify Whales
https://web.telegram.org/k/#@crawlgroup_bot

![Telegram Bot Interface](images/tele_bot.png)

---

### 5. Crawl Group

**Purpose:** Crawl channels by keyword, Gemini AI generates 10 keywords (5 Vietnamese + 5 Indonesian), analyze content with AI and save to Google Sheets.

**Flow:**

```
Manual Trigger
    ↓
Google Sheets - Data (read data)
    ↓
Google Sheets - Keyword (get main keyword)
    ↓
Gemini AI (generate 10 keywords: 5 VN + 5 ID)
    ↓
HTTP Request → Modal API (crawl channels)
    ↓
Split Out (split data)
    ↓
Loop Over Items (iterate through each channel)
    ↓
Information Extractor (AI analyzes)
    ↓
Google Sheets - Append or update
```

**Input:** Keywords from "Keyword" sheet
**Output:**
- ID, Platform, Name, Link
- Date Created, Summary, Quantity
- Reaction, Frequency, View
- Mention, Subscribers
<img width="946" height="569" alt="Screenshot 2026-04-23 at 14 31 32" src="https://github.com/user-attachments/assets/a1e38d8d-6c0f-4391-8c90-8a8d6029ce10" />
<img width="1127" height="548" alt="Screenshot 2026-04-23 at 14 31 43" src="https://github.com/user-attachments/assets/bf743390-d705-47ec-b9a5-1e2a38755a6a" />
<img width="796" height="555" alt="Screenshot 2026-04-23 at 14 32 01" src="https://github.com/user-attachments/assets/29202e61-6e59-47a3-875c-6c00807e4d47" />


---

### How to import workflows into N8N

1. Open N8N → Click **Workflows** → **Import from File**
2. Select the corresponding JSON file in `N8N-BingX-crawl-telegram/` folder
3. Configure credentials:
   - **Google Sheets**: OAuth2 API
   - **Telegram API**: Bot Token
   - **Google Gemini**: API key for AI features
4. Activate workflow

---

## Requirements

- Python 3.11+
- Modal account (free sign-up at modal.com)
- Telegram API credentials (from my.telegram.org)
- Libraries: modal, telethon, cryptg
- N8N instance (self-hosted or cloud)
- Google Sheets credentials
- Gemini AI API key (for AI features)

## Install Modal CLI

```bash
pip install modal
modal setup
```

## Notes

- **No dedicated server needed** - Code runs on Modal, just deploy and call the API
- **Rate limits** - Telegram has rate limits when crawling too many messages
- **Privacy** - Session and data are securely stored on Modal Volume

---

Made with Modal + Telethon
