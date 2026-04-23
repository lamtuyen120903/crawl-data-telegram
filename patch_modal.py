import re

with open("modal_user_message.py", "r", encoding="utf-8") as f:
    code = f.read()

# Replace get_user_ranking
code = re.sub(
    r'@app\.function\(\s*image=image,\s*secrets=\[secrets\],\s*volumes=\{"/session": session_volume\},\s*timeout=1800,\s*max_containers=1,\s*\)\s*async def get_user_ranking\(',
    '''@app.cls(
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
        import os
        
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
    async def get_user_ranking(self, ''',
    code, count=1
)

# Replace get_user_messages
code = re.sub(
    r'@app\.function\(\s*image=image,\s*secrets=\[secrets\],\s*volumes=\{"/session": session_volume\},\s*timeout=1800,\s*max_containers=1,\s*\)\s*async def get_user_messages\(',
    '''    @modal.method()
    async def get_user_messages(self, ''',
    code, count=1
)

# Replace get_top_users_messages
code = re.sub(
    r'@app\.function\(\s*image=image,\s*secrets=\[secrets\],\s*volumes=\{"/session": session_volume\},\s*timeout=1800,\s*max_containers=1,\s*\)\s*async def get_top_users_messages\(',
    '''    @modal.method()
    async def get_top_users_messages(self, ''',
    code, count=1
)

# For each function, replace the client initialization
# The pattern is from `from telethon import TelegramClient...` down to `await client.connect()`
# For get_user_ranking:
pattern = r'    from telethon import TelegramClient\s+api_id = int\(os\.environ\["API_ID"\]\)\s+api_hash = os\.environ\["API_HASH"\]\s+session_path = "/session/session_analytics"\s+client = TelegramClient\(session_path, api_id, api_hash\)\s+try:\s+await client\.connect\(\)'
code = re.sub(pattern, '    client = self.client\n    try:', code, count=1)

# For get_user_messages and get_top_users_messages (these have MessageReplyHeader):
pattern2 = r'    from telethon import TelegramClient\s+from telethon\.tl\.types import MessageReplyHeader\s+api_id = int\(os\.environ\["API_ID"\]\)\s+api_hash = os\.environ\["API_HASH"\]\s+session_path = "/session/session_analytics"\s+client = TelegramClient\(session_path, api_id, api_hash\)\s+try:\s+await client\.connect\(\)'
code = re.sub(pattern2, '    from telethon.tl.types import MessageReplyHeader\n    client = self.client\n    try:', code, count=2)

# Replace finally blocks
pattern_finally = r'    finally:\s+await client\.disconnect\(\)\s+session_volume\.commit\(\)'
code = re.sub(pattern_finally, '    finally:\n        pass', code)

# Update the FastAPI endpoints calls to instantiate the class
code = code.replace(
    'result = await get_user_ranking.remote.aio(',
    'service = TelegramAnalyticsService()\n    result = await service.get_user_ranking.remote.aio('
)

code = code.replace(
    'result = await get_user_messages.remote.aio(',
    'service = TelegramAnalyticsService()\n    result = await service.get_user_messages.remote.aio('
)

code = code.replace(
    'result = await get_top_users_messages.remote.aio(',
    'service = TelegramAnalyticsService()\n    result = await service.get_top_users_messages.remote.aio('
)

# Fix duplicate key total_messages_in_period
code = code.replace(
    '"total_messages_in_period": len(all_messages),\n            "total_messages_in_period": len(all_messages),',
    '"total_messages_in_period": len(all_messages),'
)

with open("modal_user_message.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Patch applied")
