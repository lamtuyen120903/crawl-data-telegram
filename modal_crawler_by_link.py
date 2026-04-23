import modal
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import Channel

# --- Modal App Setup ---
# Using a different app name to distinguish from the search-based crawler
app = modal.App("telegram-single-channel-crawler")

# Volume for persistent Telegram session storage (Shared with the other app)
session_volume = modal.Volume.from_name("telegram-session-link", create_if_missing=True)

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
async def crawl_channel_by_link(link: str, days: int = 30, download_media: bool = False):
    """Crawl a specific channel by its link or username."""
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_path = "/session/session_link"
    
    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            return {"error": "Session not authorized. Please run the auth flow first."}
        
        # --- Resolve Channel ---
        try:
            # get_entity handles URLs (https://t.me/...) and usernames (@...) automatically
            entity = await client.get_entity(link)
        except Exception as e:
            return {"error": f"Could not find channel '{link}': {str(e)}"}

        if not isinstance(entity, Channel):
             return {"error": f"Entity '{link}' is not a channel."}
        
        # --- Process Channel ---
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=int(days))
        
        try:
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
            
            # Prepare media directory if downloading
            if download_media:
                media_base_path = f"/session/media/{chat_info.username}"
                os.makedirs(media_base_path, exist_ok=True)
            
            while True:
                history = await client(GetHistoryRequest(
                    peer=entity,
                    limit=300,
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
                    
                    if not msg.message and not msg.media:
                        continue
                    
                    reactions = []
                    if msg.reactions:
                        for r in msg.reactions.results:
                            reactions.append({
                                "emoticon": r.reaction.emoticon if hasattr(r.reaction, 'emoticon') else str(r.reaction),
                                "count": r.count
                            })
                    
                    message_link = f"https://t.me/{chat_info.username}/{msg.id}"
                    image_links = []
                    local_media_path = None
                    
                    if msg.photo:
                        image_links.append(message_link)

                    if download_media and (msg.photo or msg.file):
                         try:
                            # Create a unique filename based on message ID
                            file_name = f"{msg.id}"
                            # Start download
                            downloaded_path = await client.download_media(msg, file=os.path.join(media_base_path, file_name))
                            if downloaded_path:
                                local_media_path = downloaded_path
                         except Exception as e:
                             print(f"Failed to download media for message {msg.id}: {e}")

                    all_items.append({
                        "channel": chat_info.username,
                        "message_id": msg.id,
                        "caption": msg.message or "",
                        "date": msg.date.isoformat(),
                        "views": msg.views,
                        "forwards": msg.forwards,
                        "replies": msg.replies.replies if msg.replies else 0,
                        "reaction_total": sum(r["count"] for r in reactions),
                        "message_link": message_link,
                        "image_links": image_links,
                        "local_media_path": local_media_path
                    })
                
                if offset_id is None:
                    break
                
                offset_id = history.messages[-1].id
            
            crawl_data = {
                "platform": "telegram",
                "type": "crawl",
                "channel": chat_info.username,
                "from_date": cutoff_date.isoformat(),
                "total_items": len(all_items),
                "items": all_items
            }
            
            result_payload = {
                "platform": "telegram",
                "type": "single_channel_crawl",
                "input_link": link,
                "data": {
                    "info": info_data,
                    "crawl": crawl_data
                }
            }
            
            return json.loads(json.dumps(result_payload, cls=DateTimeEncoder))
            
        except Exception as e:
            return {"error": f"Error interacting with channel '{link}': {str(e)}"}
        
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
    session_path = "/session/session_link.session"
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
    """Web endpoint for crawling a specific channel by link."""
    link = request.get("link")
    days_input = request.get("days")
    download_media = request.get("download_media", False)

    # Validate 'days'
    try:
        if days_input is None or days_input == "":
             days = 30
        else:
             days = int(days_input)
    except ValueError:
        return {"error": "'days' parameter must be a number"}
    
    if not link:
        return {"error": "Missing 'link' parameter"}
    
    result = await crawl_channel_by_link.remote.aio(link=link, days=days, download_media=download_media)
    return result


# Local entrypoint for creating and uploading session
# This isn't strictly necessary if the session is already uploaded via the other app,
# but keeping it here makes this app self-contained.
@app.local_entrypoint()
def main():
    print("=== Telegram Session Creator (Single Channel App) ===")
    print("This will create a session locally and upload it to Modal.\n")
    
    local_session_path = "session_link"
    
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
    print("\nDone! You can now deploy with: modal deploy modal_crawler_by_link.py")
