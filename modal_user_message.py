"""
Modal App - User Message Analytics
Phân tích tin nhắn theo user trong Group (dành cho deploy trên Modal.com)

Endpoints:
- POST /user-ranking: Lấy bảng xếp hạng user
- POST /user-messages: Lấy tin nhắn của user cụ thể

NOTE: Tất cả parameters đều bắt buộc từ request, không có giá trị mặc định
"""
import modal
import json
import os
import asyncio
import base64
import io
import re
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# --- Modal App Setup ---
app = modal.App("telegram-user-analytics")

# Volume for persistent Telegram session storage
session_volume = modal.Volume.from_name("telegram-session-analytics", create_if_missing=True)

# Docker image with required dependencies
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "telethon",
    "cryptg",
    "fastapi[standard]",
    "requests",
)

# Secrets (API_ID and API_HASH)
secrets = modal.Secret.from_name("telegram-secrets")

# Constants for local entrypoint
API_ID = 30182503
API_HASH = "c6f6ef5389f37bb27ec0fd9f5fc3aed0"


# --- Helper Classes ---
class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, bytes):
            return str(o)
        return super().default(o)


# --- Helper Functions ---
def get_sender_info(sender):
    """Extract sender information"""
    from telethon.tl.types import User, Channel, Chat
    
    if not sender:
        return None
    
    if isinstance(sender, User):
        return {
            "type": "user",
            "id": sender.id,
            "first_name": sender.first_name,
            "last_name": sender.last_name,
            "username": sender.username,
            "phone": sender.phone,
            "is_bot": sender.bot,
            "is_verified": sender.verified,
            "is_premium": getattr(sender, 'premium', False),
        }
    elif isinstance(sender, Channel):
        return {
            "type": "channel",
            "id": sender.id,
            "title": sender.title,
            "username": sender.username,
        }
    elif isinstance(sender, Chat):
        return {
            "type": "chat",
            "id": sender.id,
            "title": sender.title,
        }
    
    return {"type": "unknown", "id": getattr(sender, 'id', None)}


async def get_media_info_with_base64(client, message, download_media: bool = False):
    """Extract media information and optionally convert photos to base64"""
    from telethon.tl.types import (
        MessageMediaPhoto, MessageMediaDocument,
        MessageMediaWebPage, MessageMediaContact,
        MessageMediaGeo, MessageMediaPoll
    )
    
    if not message.media:
        return None
    
    media_info = {"type": "unknown"}
    
    if isinstance(message.media, MessageMediaPhoto):
        media_info = {
            "type": "photo",
            "photo_id": message.media.photo.id if message.media.photo else None,
        }
        if download_media:
            try:
                buffer = io.BytesIO()
                await client.download_media(message.media, file=buffer)
                buffer.seek(0)
                photo_bytes = buffer.read()
                base64_string = base64.b64encode(photo_bytes).decode('utf-8')
                media_info["base64"] = f"data:image/jpeg;base64,{base64_string}"
                media_info["size_bytes"] = len(photo_bytes)
            except Exception as e:
                media_info["base64_error"] = str(e)
                
    elif isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            media_info = {
                "type": "document",
                "document_id": doc.id,
                "mime_type": doc.mime_type,
                "size": doc.size,
                "file_name": None
            }
            for attr in doc.attributes:
                if hasattr(attr, 'file_name'):
                    media_info["file_name"] = attr.file_name
                if hasattr(attr, 'duration'):
                    media_info["duration"] = attr.duration
                if hasattr(attr, 'w') and hasattr(attr, 'h'):
                    media_info["width"] = attr.w
                    media_info["height"] = attr.h
                    
            if download_media and doc.mime_type and doc.mime_type.startswith('image/'):
                try:
                    buffer = io.BytesIO()
                    await client.download_media(message.media, file=buffer)
                    buffer.seek(0)
                    photo_bytes = buffer.read()
                    base64_string = base64.b64encode(photo_bytes).decode('utf-8')
                    media_info["base64"] = f"data:{doc.mime_type};base64,{base64_string}"
                except Exception as e:
                    media_info["base64_error"] = str(e)
                    
    elif isinstance(message.media, MessageMediaWebPage):
        webpage = message.media.webpage
        if hasattr(webpage, 'url'):
            media_info = {
                "type": "webpage",
                "url": webpage.url,
                "title": getattr(webpage, 'title', None),
                "description": getattr(webpage, 'description', None),
            }
    elif isinstance(message.media, MessageMediaContact):
        media_info = {
            "type": "contact",
            "phone_number": message.media.phone_number,
            "first_name": message.media.first_name,
            "last_name": message.media.last_name,
        }
    elif isinstance(message.media, MessageMediaGeo):
        geo = message.media.geo
        media_info = {
            "type": "geo",
            "lat": getattr(geo, 'lat', None),
            "long": getattr(geo, 'long', None),
        }
    elif isinstance(message.media, MessageMediaPoll):
        poll = message.media.poll
        media_info = {
            "type": "poll",
            "question": poll.question.text if hasattr(poll.question, 'text') else str(poll.question),
            "answers": [a.text.text if hasattr(a.text, 'text') else str(a.text) for a in poll.answers] if poll.answers else [],
        }
    
    return media_info


async def get_excluded_user_ids(client, entity):
    """Get set of user IDs to exclude from ranking (admins, creators, bots, roles)"""
    from telethon.tl.functions.channels import GetParticipantsRequest
    from telethon.tl.types import (
        User, ChannelParticipantsAdmins, 
        ChannelParticipantCreator, ChannelParticipantAdmin
    )
    
    excluded_ids = set()
    excluded_info = {}
    
    try:
        admins_result = await client(GetParticipantsRequest(
            channel=entity,
            filter=ChannelParticipantsAdmins(),
            offset=0,
            limit=200,
            hash=0
        ))
        
        for participant in admins_result.participants:
            user_id = participant.user_id
            
            if isinstance(participant, ChannelParticipantCreator):
                excluded_ids.add(user_id)
                rank = getattr(participant, 'rank', None)
                excluded_info[user_id] = f"Creator" + (f" ({rank})" if rank else "")
                
            elif isinstance(participant, ChannelParticipantAdmin):
                excluded_ids.add(user_id)
                rank = getattr(participant, 'rank', None)
                excluded_info[user_id] = f"Admin" + (f" ({rank})" if rank else "")
        
        for user in admins_result.users:
            if isinstance(user, User) and user.bot:
                excluded_ids.add(user.id)
                excluded_info[user.id] = "Bot"
                
    except Exception as e:
        print(f"Warning: Cannot get admin list: {e}")
    
    return excluded_ids, excluded_info


async def fetch_all_messages(client, entity, start_date, end_date):
    """Fetch all messages in a date range"""
    from telethon.tl.functions.messages import GetHistoryRequest
    from telethon.tl.types import MessageService
    
    all_messages = []
    offset_id = 0
    
    while True:
        await asyncio.sleep(0.3)
        
        try:
            history = await client(GetHistoryRequest(
                peer=entity,
                limit=100,
                offset_date=None,
                offset_id=offset_id,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0
            ))
        except Exception as e:
            if "wait" in str(e).lower():
                match = re.search(r'(\d+) seconds', str(e))
                if match:
                    wait_time = int(match.group(1))
                    await asyncio.sleep(min(wait_time, 60))
                    continue
            break
        
        if not history.messages:
            break
        
        user_cache = {}
        for user in history.users:
            user_cache[user.id] = user
        for chat in history.chats:
            user_cache[chat.id] = chat
        
        reached_start = False
        for msg in history.messages:
            if isinstance(msg, MessageService):
                continue
            
            if msg.date and msg.date > end_date:
                continue
            
            if msg.date and msg.date < start_date:
                reached_start = True
                break
            
            sender = None
            sender_id = None
            if msg.from_id:
                sender_id = getattr(msg.from_id, 'user_id', None) or getattr(msg.from_id, 'channel_id', None) or getattr(msg.from_id, 'chat_id', None)
                if sender_id and sender_id in user_cache:
                    sender = user_cache[sender_id]
            
            all_messages.append({
                "msg": msg,
                "sender": sender,
                "sender_id": sender_id
            })
        
        if reached_start:
            break
        
        if history.messages:
            offset_id = history.messages[-1].id
    
    return all_messages


def analyze_user_messages(messages):
    """Analyze messages and group by user"""
    user_stats = defaultdict(lambda: {"info": None, "messages": [], "count": 0})
    
    for item in messages:
        sender = item["sender"]
        sender_id = item["sender_id"]
        
        if sender_id:
            user_stats[sender_id]["info"] = get_sender_info(sender)
            user_stats[sender_id]["messages"].append(item["msg"])
            user_stats[sender_id]["count"] += 1
    
    return dict(user_stats)


def filter_and_rank_users(user_stats, excluded_ids=None, limit=None):
    """Filter out bots/admins and rank users by message count"""
    excluded_ids = excluded_ids or set()
    filtered_stats = {}
    excluded_bots = []
    
    for user_id, data in user_stats.items():
        info = data["info"]
        
        if user_id in excluded_ids:
            continue
        
        if info and info.get("is_bot"):
            excluded_bots.append(user_id)
            continue
        
        if info and info.get("type") == "channel":
            continue
            
        filtered_stats[user_id] = data
    
    # Sort by message count descending
    sorted_users = sorted(filtered_stats.items(), key=lambda x: x[1]["count"], reverse=True)
    
    user_list = []
    for idx, (user_id, data) in enumerate(sorted_users, 1):
        info = data["info"]
        if info:
            username = info.get("username") or None
            if info.get("type") == "user":
                name = f"{info.get('first_name', '') or ''} {info.get('last_name', '') or ''}".strip() or None
            else:
                name = info.get("title")
        else:
            username = None
            name = None
        
        user_list.append({
            "rank": idx,
            "user_id": user_id,
            "username": username,
            "name": name,
            "message_count": data["count"],
            "info": info
        })
    
    # Apply limit if specified
    if limit is not None:
        return user_list[:limit]
    
    return user_list


# --- Modal Functions ---

@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=1800,
    max_containers=1,
)
async def get_user_ranking(
    group: str,
    days: int,
    limit: int,
    start_date: str = None,
    end_date: str = None
):
    """
    Get user ranking by message count in a group.
    All parameters come from HTTP POST - no defaults except optional date overrides.
    """
    from telethon import TelegramClient
    
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_path = "/session/session_analytics"
    
    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            return {"error": "Session not authorized. Please run 'modal run modal_user_message.py' first."}
        
        # Parse dates - start_date/end_date override days if provided
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start_dt = datetime.now(timezone.utc) - timedelta(days=days)
        
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        else:
            end_dt = datetime.now(timezone.utc)
        
        # Get group entity
        try:
            entity = await client.get_entity(group)
        except Exception as e:
            return {"error": f"Cannot find group: {str(e)}"}
        
        group_info = {
            "id": entity.id,
            "title": getattr(entity, 'title', None),
            "username": getattr(entity, 'username', None),
        }
        
        # Fetch messages
        all_messages = await fetch_all_messages(client, entity, start_dt, end_dt)
        
        if not all_messages:
            return {
                "platform": "telegram",
                "type": "user_ranking",
                "group": group_info,
                "date_range": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                },
                "total_messages": 0,
                "total_users": 0,
                "excluded": [],
                "ranking": []
            }
        
        # Analyze by user
        user_stats = analyze_user_messages(all_messages)
        
        # Get excluded users
        excluded_ids, excluded_info = await get_excluded_user_ids(client, entity)
        
        # Build excluded list for response
        excluded_list = []
        for user_id, reason in excluded_info.items():
            if user_id in user_stats:
                info = user_stats[user_id]["info"]
                excluded_list.append({
                    "user_id": user_id,
                    "username": info.get("username") if info else None,
                    "reason": reason,
                    "message_count": user_stats[user_id]["count"]
                })
        
        # Filter and rank users with specified limit
        user_ranking = filter_and_rank_users(user_stats, excluded_ids, limit)
        
        result = {
            "platform": "telegram",
            "type": "user_ranking",
            "crawl_date": datetime.now(timezone.utc).isoformat(),
            "group": group_info,
            "date_range": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            },
            "total_messages": len(all_messages),
            "total_users": len(user_ranking),
            "excluded": excluded_list,
            "ranking": user_ranking
        }
        
        return json.loads(json.dumps(result, cls=DateTimeEncoder))
        
    finally:
        await client.disconnect()
        session_volume.commit()


@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=1800,
    max_containers=1,
)
async def get_user_messages(
    group: str,
    days: int,
    download_media: bool,
    user_id: int = None,
    username: str = None,
    start_date: str = None,
    end_date: str = None
):
    """
    Get all messages from a specific user in a group.
    All parameters come from HTTP POST - no defaults.
    """
    from telethon import TelegramClient
    from telethon.tl.types import MessageReplyHeader
    
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_path = "/session/session_analytics"
    
    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            return {"error": "Session not authorized."}
        
        # Parse dates
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start_dt = datetime.now(timezone.utc) - timedelta(days=days)
        
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        else:
            end_dt = datetime.now(timezone.utc)
        
        # Get group entity
        try:
            entity = await client.get_entity(group)
        except Exception as e:
            return {"error": f"Cannot find group: {str(e)}"}
        
        group_info = {
            "id": entity.id,
            "title": getattr(entity, 'title', None),
            "username": getattr(entity, 'username', None),
        }
        
        # Resolve username to user_id if needed
        target_user_id = user_id
        if not target_user_id and username:
            try:
                user_entity = await client.get_entity(username)
                target_user_id = user_entity.id
            except Exception as e:
                return {"error": f"Cannot find user: {str(e)}"}
        
        if not target_user_id:
            return {"error": "Either user_id or username is required"}
        
        # Fetch all messages
        all_messages = await fetch_all_messages(client, entity, start_dt, end_dt)
        
        # Filter messages by user
        user_stats = analyze_user_messages(all_messages)
        
        if target_user_id not in user_stats:
            return {
                "platform": "telegram",
                "type": "user_messages",
                "group": group_info,
                "user": {"id": target_user_id},
                "date_range": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                },
                "total_messages": 0,
                "messages": []
            }
        
        user_data = user_stats[target_user_id]
        user_info = user_data["info"]
        
        # Process messages with media
        messages_data = []
        for msg in user_data["messages"]:
            media_data = await get_media_info_with_base64(client, msg, download_media)
            
            message_data = {
                "message_id": msg.id,
                "date": msg.date.isoformat() if msg.date else None,
                "text": msg.message,
                "views": msg.views,
                "forwards": msg.forwards,
                "replies_count": msg.replies.replies if msg.replies else None,
                "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
                "is_pinned": msg.pinned,
                "media": media_data,
                "reply_to": {
                    "message_id": msg.reply_to.reply_to_msg_id if isinstance(msg.reply_to, MessageReplyHeader) else None,
                } if msg.reply_to else None,
                "forward_from": {
                    "date": msg.fwd_from.date.isoformat() if msg.fwd_from and msg.fwd_from.date else None,
                    "from_name": msg.fwd_from.from_name if msg.fwd_from else None,
                } if msg.fwd_from else None,
            }
            
            messages_data.append(message_data)
        
        result = {
            "platform": "telegram",
            "type": "user_messages",
            "crawl_date": datetime.now(timezone.utc).isoformat(),
            "group": group_info,
            "user": user_info,
            "date_range": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            },
            "total_messages": len(messages_data),
            "messages": messages_data,
        }
        
        return json.loads(json.dumps(result, cls=DateTimeEncoder))
        
    finally:
        await client.disconnect()
        session_volume.commit()


# --- Get Top Users Messages Function ---

@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=1800,
    max_containers=1,
)
async def get_top_users_messages(
    group: str,
    days: int,
    download_media: bool,
    top_n: int,
    ranking_limit: int = None,
    start_date: str = None,
    end_date: str = None
):
    """
    Get messages from top N users in the ranking automatically.
    This combines ranking and message fetching into one call.
    """
    from telethon import TelegramClient
    from telethon.tl.types import MessageReplyHeader
    
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_path = "/session/session_analytics"
    
    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            return {"error": "Session not authorized."}
        
        # Parse dates
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start_dt = datetime.now(timezone.utc) - timedelta(days=days)
        
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        else:
            end_dt = datetime.now(timezone.utc)
        
        # Get group entity
        try:
            entity = await client.get_entity(group)
        except Exception as e:
            return {"error": f"Cannot find group: {str(e)}"}
        
        group_info = {
            "id": entity.id,
            "title": getattr(entity, 'title', None),
            "username": getattr(entity, 'username', None),
        }
        
        # Fetch all messages
        all_messages = await fetch_all_messages(client, entity, start_dt, end_dt)
        
        if not all_messages:
            return {
                "platform": "telegram",
                "type": "top_users_messages",
                "crawl_date": datetime.now(timezone.utc).isoformat(),
                "group": group_info,
                "date_range": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                },
                "total_messages": 0,
                "top_n": top_n,
                "users": []
            }
        
        # Analyze by user
        user_stats = analyze_user_messages(all_messages)
        
        # Get excluded users (admins, bots)
        excluded_ids, excluded_info = await get_excluded_user_ids(client, entity)
        
        # Filter and rank users - get top N for ranking list
        # If ranking_limit is not specified, default to top_n (backward compatibility)
        limit_for_ranking = ranking_limit if ranking_limit is not None else top_n
        
        # We need at least top_n users for analysis, so ensure limit covers it
        if limit_for_ranking < top_n:
            limit_for_ranking = top_n
            
        full_user_ranking = filter_and_rank_users(user_stats, excluded_ids, limit_for_ranking)
        
        # detailed analysis only for top_n
        users_to_analyze = full_user_ranking[:top_n]
        
        # Get messages for each top user
        users_data = []
        for ranked_user in users_to_analyze:
            user_id = ranked_user["user_id"]
            
            if user_id not in user_stats:
                continue
            
            user_data = user_stats[user_id]
            user_info = user_data["info"]
            
            # Process messages with media
            messages_data = []
            for msg in user_data["messages"]:
                media_data = await get_media_info_with_base64(client, msg, download_media)
                
                message_data = {
                    "message_id": msg.id,
                    "date": msg.date.isoformat() if msg.date else None,
                    "text": msg.message,
                    "views": msg.views,
                    "forwards": msg.forwards,
                    "replies_count": msg.replies.replies if msg.replies else None,
                    "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
                    "is_pinned": msg.pinned,
                    "media": media_data,
                    "reply_to": {
                        "message_id": msg.reply_to.reply_to_msg_id if isinstance(msg.reply_to, MessageReplyHeader) else None,
                    } if msg.reply_to else None,
                    "forward_from": {
                        "date": msg.fwd_from.date.isoformat() if msg.fwd_from and msg.fwd_from.date else None,
                        "from_name": msg.fwd_from.from_name if msg.fwd_from else None,
                    } if msg.fwd_from else None,
                }
                
                messages_data.append(message_data)
            
            users_data.append({
                "rank": ranked_user["rank"],
                "user": user_info,
                "user_id": user_id,
                "username": ranked_user["username"],
                "name": ranked_user["name"],
                "total_messages": len(messages_data),
                "messages": messages_data,
            })
        
        result = {
            "platform": "telegram",
            "type": "top_users_messages",
            "crawl_date": datetime.now(timezone.utc).isoformat(),
            "group": group_info,
            "date_range": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            },
            "total_messages_in_period": len(all_messages),
            "total_messages_in_period": len(all_messages),
            "top_n_analyzed": top_n,
            "ranking_limit": limit_for_ranking,
            "users_count": len(users_data),
            "ranking": full_user_ranking,
            "users": users_data,
        }
        
        return json.loads(json.dumps(result, cls=DateTimeEncoder))
        
    finally:
        await client.disconnect()
        session_volume.commit()


# --- Web Endpoints ---

@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=1800,
)
@modal.fastapi_endpoint(method="POST")
async def top_users_messages(request: dict):
    """
    Web endpoint to get messages from top N users in ranking.
    
    Required parameters:
    - group: string
    - days: int
    - download_media: bool
    
    Optional parameters:
    - top_n: int (default: 3) - number of top users to get messages from
    - ranking_limit: int - number of users to include in the ranking list
    - start_date: string (YYYY-MM-DD) - overrides days
    - end_date: string (YYYY-MM-DD)
    """
    group = request.get("group")
    days = request.get("days")
    download_media = request.get("download_media")
    top_n = request.get("top_n", 3)  # Default to 3 users
    ranking_limit = request.get("ranking_limit")
    start_date = request.get("start_date")
    end_date = request.get("end_date")
    
    # Validate required parameters
    if not group:
        return {"error": "Missing required 'group' parameter"}
    if days is None:
        return {"error": "Missing required 'days' parameter"}
    if download_media is None:
        return {"error": "Missing required 'download_media' parameter"}
    
    result = await get_top_users_messages.remote.aio(
        group=group,
        days=int(days),
        download_media=bool(download_media),
        top_n=int(top_n),
        ranking_limit=int(ranking_limit) if ranking_limit is not None else None,
        start_date=start_date,
        end_date=end_date
    )
    return result


@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=1800,
)
@modal.fastapi_endpoint(method="POST")
async def user_ranking(request: dict):
    """
    Web endpoint to get user ranking.
    
    Required parameters (all from request body):
    - group: string
    - days: int
    - limit: int
    
    Optional parameters:
    - start_date: string (YYYY-MM-DD) - overrides days
    - end_date: string (YYYY-MM-DD)
    """
    group = request.get("group")
    days = request.get("days")
    limit = request.get("limit")
    start_date = request.get("start_date")
    end_date = request.get("end_date")
    
    # Validate required parameters
    if not group:
        return {"error": "Missing required 'group' parameter"}
    if days is None:
        return {"error": "Missing required 'days' parameter"}
    if limit is None:
        return {"error": "Missing required 'limit' parameter"}
    
    result = await get_user_ranking.remote.aio(
        group=group,
        days=int(days),
        limit=int(limit),
        start_date=start_date,
        end_date=end_date
    )
    return result


@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=1800,
)
@modal.fastapi_endpoint(method="POST")
async def user_messages(request: dict):
    """
    Web endpoint to get user messages.
    
    Required parameters (all from request body):
    - group: string
    - days: int
    - download_media: bool
    - user_id OR username: int/string
    
    Optional parameters:
    - start_date: string (YYYY-MM-DD)
    - end_date: string (YYYY-MM-DD)
    """
    group = request.get("group")
    user_id = request.get("user_id")
    username = request.get("username")
    days = request.get("days")
    download_media = request.get("download_media")
    start_date = request.get("start_date")
    end_date = request.get("end_date")
    
    # Validate required parameters
    if not group:
        return {"error": "Missing required 'group' parameter"}
    if days is None:
        return {"error": "Missing required 'days' parameter"}
    if download_media is None:
        return {"error": "Missing required 'download_media' parameter"}
    if not user_id and not username:
        return {"error": "Either 'user_id' or 'username' is required"}
    
    result = await get_user_messages.remote.aio(
        group=group,
        user_id=int(user_id) if user_id else None,
        username=username,
        days=int(days),
        download_media=bool(download_media),
        start_date=start_date,
        end_date=end_date
    )
    return result


# --- Session Management ---

@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
)
async def upload_session(session_data: bytes):
    """Upload session file to Modal volume."""
    session_path = "/session/session_analytics.session"
    with open(session_path, "wb") as f:
        f.write(session_data)
    session_volume.commit()
    return {"status": "Session uploaded successfully"}


# --- Local Entrypoint ---

@app.local_entrypoint()
def main():
    print("=== Telegram User Analytics - Session Creator ===")
    print("This will create a session locally and upload it to Modal.\n")
    
    from telethon import TelegramClient
    
    local_session_path = "session_analytics"
    
    async def create_and_upload():
        client = TelegramClient(local_session_path, API_ID, API_HASH)
        await client.start()
        me = await client.get_me()
        print(f"\nLogged in as: {me.first_name} (@{me.username})")
        await client.disconnect()
        
        session_file = f"{local_session_path}.session"
        if os.path.exists(session_file):
            with open(session_file, "rb") as f:
                session_data = f.read()
            
            print("\nUploading session to Modal...")
            result = upload_session.remote(session_data)
            print(f"Result: {result}")
            
            os.remove(session_file)
            print("Local session file cleaned up.")
        else:
            print("Error: Session file not found!")
    
    asyncio.run(create_and_upload())
    print("\nDone! You can now deploy with: modal deploy modal_user_message.py")
    print("\nEndpoints after deploy:")
    print("  - POST /user-ranking  : Get user ranking in a group")
    print("  - POST /user-messages : Get messages from a specific user")
