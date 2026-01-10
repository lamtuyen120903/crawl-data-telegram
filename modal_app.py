import modal
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import Channel

# --- Modal App Setup ---
app = modal.App("telegram-crawler")

# Volume for persistent Telegram session storage
session_volume = modal.Volume.from_name("telegram-session", create_if_missing=True)

# Docker image with required dependencies
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "telethon",
    "cryptg",
    "fastapi[standard]",
)

# Secrets (API_ID and API_HASH)
secrets = modal.Secret.from_name("telegram-secrets")

# Constants
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


# --- Modal Functions ---

@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=600,
)
async def crawl_channels(keywords: str, days: int = 10, limit_per_keyword: int = 10):
    """Main function to search, get info, and crawl channels."""
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_path = "/session/telegram_session"
    
    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            return {"error": "Session not authorized. Please run 'modal run modal_app.py' first."}
        
        # --- Search for channels ---
        keyword_list = [k.strip() for k in keywords.split(",")]
        all_usernames = set()
        
        for kw in keyword_list:
            try:
                result = await client(SearchRequest(q=kw, limit=100))
                for chat in result.chats:
                    if isinstance(chat, Channel) and chat.username:
                        all_usernames.add(chat.username)
            except Exception as e:
                print(f"Search error for '{kw}': {e}")
        
        # Limit the total channels to process
        all_usernames = list(all_usernames)[:int(limit_per_keyword)]
        
        if not all_usernames:
            return {
                "platform": "telegram",
                "type": "auto_batch",
                "keywords": keywords,
                "total_channels": 0,
                "data": []
            }
        
        # --- Process each channel ---
        batch_results = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=int(days))
        
        for username in all_usernames:
            try:
                entity = await client.get_entity(username)
                
                if not isinstance(entity, Channel):
                    continue
                
                # Get channel info
                full_channel = await client(GetFullChannelRequest(channel=entity))
                chats = full_channel.chats
                chat_info = chats[0] if chats else entity
                full_info = full_channel.full_chat
                
                info_data = {
                    "platform": "telegram",
                    "type": "channel_details",
                    "id": chat_info.id,
                    "title": chat_info.title,
                    "username": chat_info.username,
                    "date": chat_info.date,
                    "verified": chat_info.verified,
                    "about": full_info.about,
                    "participants_count": full_info.participants_count,
                }
                
                # Crawl messages
                all_items = []
                offset_id = 0
                
                while True:
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
                    
                    if not history.messages:
                        break
                    
                    for msg in history.messages:
                        if not msg.date or msg.date < cutoff_date:
                            offset_id = None
                            break
                        
                        if not msg.message:
                            continue
                        
                        reactions = []
                        if msg.reactions:
                            for r in msg.reactions.results:
                                reactions.append({
                                    "emoticon": r.reaction.emoticon if hasattr(r.reaction, 'emoticon') else str(r.reaction),
                                    "count": r.count
                                })
                        
                        all_items.append({
                            "channel": username,
                            "message_id": msg.id,
                            "caption": msg.message,
                            "date": msg.date.isoformat(),
                            "views": msg.views,
                            "forwards": msg.forwards,
                            "replies": msg.replies.replies if msg.replies else 0,
                            "reaction_total": sum(r["count"] for r in reactions)
                        })
                    
                    if offset_id is None:
                        break
                    
                    offset_id = history.messages[-1].id
                
                crawl_data = {
                    "platform": "telegram",
                    "type": "crawl",
                    "channel": username,
                    "from_date": cutoff_date.isoformat(),
                    "total_items": len(all_items),
                    "items": all_items
                }
                
                batch_results.append({
                    "channel": username,
                    "info": info_data,
                    "crawl": crawl_data
                })
                
            except Exception as e:
                print(f"Error processing {username}: {e}")
        
        final_payload = {
            "platform": "telegram",
            "type": "auto_batch",
            "keywords": keywords,
            "total_channels": len(batch_results),
            "data": batch_results
        }
        
        return json.loads(json.dumps(final_payload, cls=DateTimeEncoder))
        
    finally:
        await client.disconnect()
        session_volume.commit()


@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
)
async def upload_session(session_data: bytes):
    """Upload session file to Modal volume."""
    session_path = "/session/telegram_session.session"
    with open(session_path, "wb") as f:
        f.write(session_data)
    session_volume.commit()
    return {"status": "Session uploaded successfully"}


@app.function(
    image=image,
    secrets=[secrets],
    volumes={"/session": session_volume},
    timeout=600,
)
@modal.fastapi_endpoint(method="POST")
async def crawl(request: dict):
    """Web endpoint for crawling channels."""
    keywords = request.get("keywords", "")
    days = request.get("days", 10)
    limit = request.get("limit", 10)
    
    if not keywords:
        return {"error": "Missing 'keywords' parameter"}
    
    result = await crawl_channels.remote.aio(keywords=keywords, days=days, limit_per_keyword=limit)
    return result


# Local entrypoint for creating and uploading session
@app.local_entrypoint()
def main():
    print("=== Telegram Session Creator ===")
    print("This will create a session locally and upload it to Modal.\n")
    
    local_session_path = "modal_telegram_session"
    
    async def create_and_upload():
        client = TelegramClient(local_session_path, API_ID, API_HASH)
        await client.start()
        print(f"\nLogged in as: {await client.get_me()}")
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
    print("\nDone! You can now deploy with: modal deploy modal_app.py")
