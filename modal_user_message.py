"""
Modal App - Telegram Group Analytics
Crawl group data: admin list, user ranking, top users' messages.

Single endpoint: POST /analyze
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

session_volume = modal.Volume.from_name("telegram-session-analytics", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "telethon",
    "cryptg",
    "fastapi[standard]",
    "requests",
)

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


async def get_admin_list(client, entity):
    """Get list of admins/creators in the group (excluding bots)"""
    from telethon.tl.functions.channels import GetParticipantsRequest
    from telethon.tl.types import (
        User, ChannelParticipantsAdmins,
        ChannelParticipantCreator, ChannelParticipantAdmin
    )

    excluded_ids = set()
    admin_list = []

    try:
        admins_result = await client(GetParticipantsRequest(
            channel=entity,
            filter=ChannelParticipantsAdmins(),
            offset=0,
            limit=200,
            hash=0
        ))

        users_map = {}
        for user in admins_result.users:
            if isinstance(user, User):
                users_map[user.id] = user

        for participant in admins_result.participants:
            user_id = participant.user_id
            excluded_ids.add(user_id)

            user_obj = users_map.get(user_id)
            is_creator = isinstance(participant, ChannelParticipantCreator)
            rank = getattr(participant, 'rank', None)

            if user_obj and not user_obj.bot:
                base_role = "Creator" if is_creator else "Admin"
                admin_list.append({
                    "user_id": user_id,
                    "username": user_obj.username,
                    "first_name": user_obj.first_name,
                    "last_name": user_obj.last_name,
                    "phone": user_obj.phone,
                    "role": rank if rank else base_role,
                    "base_role": base_role,
                })

        # Also exclude bots
        for user in admins_result.users:
            if isinstance(user, User) and user.bot:
                excluded_ids.add(user.id)

    except Exception as e:
        print(f"Warning: Cannot get admin list: {e}")

    return excluded_ids, admin_list


async def fetch_all_messages(client, entity, start_date, end_date, message_limit: int = 10000):
    """Fetch all messages in a date range, up to message_limit"""
    from telethon.tl.functions.messages import GetHistoryRequest
    from telethon.tl.types import MessageService

    all_messages = []
    offset_id = 0

    while True:
        if len(all_messages) >= message_limit:
            break

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

            if len(all_messages) >= message_limit:
                reached_start = True
                break

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


def filter_and_rank_users(user_stats, excluded_ids, limit):
    """Filter out bots/admins and rank users by message count"""
    filtered = {}

    for user_id, data in user_stats.items():
        info = data["info"]
        if user_id in excluded_ids:
            continue
        if info and info.get("is_bot"):
            continue
        if info and info.get("type") == "channel":
            continue
        filtered[user_id] = data

    sorted_users = sorted(filtered.items(), key=lambda x: x[1]["count"], reverse=True)

    user_list = []
    for idx, (user_id, data) in enumerate(sorted_users, 1):
        info = data["info"]
        if info:
            username = info.get("username")
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
        })

    return user_list[:limit]


async def get_media_info(client, message):
    """Extract media information (no base64 download)"""
    from telethon.tl.types import (
        MessageMediaPhoto, MessageMediaDocument,
        MessageMediaWebPage, MessageMediaContact,
        MessageMediaGeo, MessageMediaPoll
    )

    if not message.media:
        return None

    if isinstance(message.media, MessageMediaPhoto):
        return {"type": "photo", "photo_id": message.media.photo.id if message.media.photo else None}

    elif isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            info = {"type": "document", "mime_type": doc.mime_type, "size": doc.size, "file_name": None}
            for attr in doc.attributes:
                if hasattr(attr, 'file_name'):
                    info["file_name"] = attr.file_name
                if hasattr(attr, 'duration'):
                    info["duration"] = attr.duration
            return info

    elif isinstance(message.media, MessageMediaWebPage):
        wp = message.media.webpage
        if hasattr(wp, 'url'):
            return {"type": "webpage", "url": wp.url, "title": getattr(wp, 'title', None)}

    elif isinstance(message.media, MessageMediaContact):
        return {"type": "contact", "phone_number": message.media.phone_number}

    elif isinstance(message.media, MessageMediaGeo):
        geo = message.media.geo
        return {"type": "geo", "lat": getattr(geo, 'lat', None), "long": getattr(geo, 'long', None)}

    elif isinstance(message.media, MessageMediaPoll):
        poll = message.media.poll
        return {
            "type": "poll",
            "question": poll.question.text if hasattr(poll.question, 'text') else str(poll.question),
        }

    return {"type": "unknown"}


# --- Modal Service ---

@app.cls(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=1800,
    max_containers=1,
    allow_concurrent_inputs=100,
)
class TelegramAnalyticsService:
    @modal.enter()
    async def enter(self):
        from telethon import TelegramClient
        import shutil

        api_id = int(os.environ["API_ID"])
        api_hash = os.environ["API_HASH"]
        session_path = "/session/session_analytics"
        self.tmp_session = "/tmp/session_analytics"

        if os.path.exists(f"{session_path}.session"):
            shutil.copy2(f"{session_path}.session", f"{self.tmp_session}.session")

        self.client = TelegramClient(self.tmp_session, api_id, api_hash)
        await self.client.connect()

    @modal.exit()
    async def exit(self):
        if hasattr(self, 'client') and self.client:
            await self.client.disconnect()

    @modal.method()
    async def analyze_group(self,
        group: str,
        days: int,
        ranking_limit: int,
        top_n: int,
        message_limit: int = 10000,
    ):
        """
        Analyze a Telegram group. Returns:
        - admins: list of all admins/creators
        - ranking: top active users (default 50) with message count
        - top_users_messages: messages from top N users (default 3)
        """
        from telethon.tl.types import MessageReplyHeader

        client = self.client

        try:
            if not await client.is_user_authorized():
                return {"error": "Session not authorized. Run 'modal run modal_user_message.py' first."}

            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=days)

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

            # 1. Get admin list
            excluded_ids, admin_list = await get_admin_list(client, entity)

            # 2. Fetch all messages in period
            all_messages = await fetch_all_messages(client, entity, start_dt, end_dt, message_limit)

            if not all_messages:
                return {
                    "platform": "telegram",
                    "crawl_date": datetime.now(timezone.utc).isoformat(),
                    "group": group_info,
                    "date_range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
                    "total_messages": 0,
                    "admins": admin_list,
                    "ranking": [],
                    "top_users_messages": []
                }

            # 3. Analyze & rank users
            user_stats = analyze_user_messages(all_messages)
            ranking = filter_and_rank_users(user_stats, excluded_ids, ranking_limit)

            # 4. Get messages for top N users
            top_users = ranking[:top_n]
            top_users_messages = []

            for ranked_user in top_users:
                uid = ranked_user["user_id"]
                if uid not in user_stats:
                    continue

                user_data = user_stats[uid]
                messages_data = []
                for msg in user_data["messages"]:
                    media_data = await get_media_info(client, msg)

                    messages_data.append({
                        "message_id": msg.id,
                        "date": msg.date.isoformat() if msg.date else None,
                        "text": msg.message,
                        "views": msg.views,
                        "forwards": msg.forwards,
                        "replies_count": msg.replies.replies if msg.replies else None,
                        "is_pinned": msg.pinned,
                        "media": media_data,
                        "reply_to": {
                            "message_id": msg.reply_to.reply_to_msg_id if isinstance(msg.reply_to, MessageReplyHeader) else None,
                        } if msg.reply_to else None,
                    })

                top_users_messages.append({
                    "rank": ranked_user["rank"],
                    "user_id": uid,
                    "username": ranked_user["username"],
                    "name": ranked_user["name"],
                    "message_count": ranked_user["message_count"],
                    "messages": messages_data,
                })

            result = {
                "platform": "telegram",
                "crawl_date": datetime.now(timezone.utc).isoformat(),
                "group": group_info,
                "date_range": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                },
                "total_messages": len(all_messages),
                "admins": admin_list,
                "ranking": ranking,
                "top_users_messages": top_users_messages,
            }

            return json.loads(json.dumps(result, cls=DateTimeEncoder))

        finally:
            pass


# --- Web Endpoint ---

@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=1800,
)
@modal.fastapi_endpoint(method="POST")
async def analyze(request: dict):
    """
    POST /analyze - Analyze a Telegram group.

    Required:
      - group: str (group username or link)
      - days: int (number of days to look back from now)
      - ranking_limit: int - number of top users in ranking
      - top_n: int - number of top users to fetch messages for
    Optional:
      - message_limit: int - max messages to fetch (default 10000)
    """
    group = request.get("group")
    days = request.get("days")
    ranking_limit = request.get("ranking_limit")
    top_n = request.get("top_n")
    message_limit = request.get("message_limit", 10000)

    if not group:
        return {"error": "Missing required 'group' parameter"}
    if days is None:
        return {"error": "Missing required 'days' parameter"}
    if ranking_limit is None:
        return {"error": "Missing required 'ranking_limit' parameter"}
    if top_n is None:
        return {"error": "Missing required 'top_n' parameter"}

    result = await TelegramAnalyticsService().analyze_group.remote.aio(
        group=group,
        days=int(days),
        ranking_limit=int(ranking_limit),
        top_n=int(top_n),
        message_limit=int(message_limit),
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
    print("\nDone! Deploy with: modal deploy modal_user_message.py")
    print("\nEndpoint: POST /analyze")
