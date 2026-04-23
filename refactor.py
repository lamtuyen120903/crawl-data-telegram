def convert_to_class(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    out_lines = []
    in_class = False
    in_method = False
    
    class_def = """
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

"""

    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check for web endpoints which means end of our class section
        if "# --- Web Endpoints ---" in line:
            in_method = False
            in_class = False
            out_lines.append(line)
            i += 1
            continue
            
        # Look for the start of one of our target functions
        if "@app.function(" in line:
            # Check if this is one of our target functions
            j = i
            func_name = None
            while j < len(lines) and j < i + 10:
                if "async def get_user_ranking" in lines[j]: func_name = "get_user_ranking"; break
                if "async def get_user_messages" in lines[j]: func_name = "get_user_messages"; break
                if "async def get_top_users_messages" in lines[j]: func_name = "get_top_users_messages"; break
                j += 1
                
            if func_name:
                if not in_class:
                    out_lines.append(class_def)
                    in_class = True
                
                out_lines.append("    @modal.method()\n")
                
                def_line = lines[j]
                def_line = def_line.replace("async def " + func_name + "(", "async def " + func_name + "(self, ")
                out_lines.append("    " + def_line)
                
                in_method = True
                i = j + 1
                continue

        if in_method:
            if line.startswith(")"):  # End of def arguments
                out_lines.append("    " + line)
            elif line.startswith("    group:"): out_lines.append("    " + line)
            elif line.startswith("    days:"): out_lines.append("    " + line)
            elif line.startswith("    limit:"): out_lines.append("    " + line)
            elif line.startswith("    download_media:"): out_lines.append("    " + line)
            elif line.startswith("    top_n:"): out_lines.append("    " + line)
            elif line.startswith("    user_id:"): out_lines.append("    " + line)
            elif line.startswith("    username:"): out_lines.append("    " + line)
            elif line.startswith("    ranking_limit:"): out_lines.append("    " + line)
            elif line.startswith("    start_date:"): out_lines.append("    " + line)
            elif line.startswith("    end_date:"): out_lines.append("    " + line)
            elif line.startswith('    api_id = '): pass # skip
            elif line.startswith('    api_hash = '): pass # skip
            elif line.startswith('    session_path = '): pass # skip
            elif line.startswith('    client = TelegramClient'):
                out_lines.append("        client = self.client\n")
            elif line.startswith('    from telethon import TelegramClient'): pass # skip
            elif line.startswith('    from telethon.tl.types import MessageReplyHeader'):
                out_lines.append("        from telethon.tl.types import MessageReplyHeader\n")
            elif line.startswith('        await client.disconnect()'):
                out_lines.append("            pass  # disconnected in exit\n")
            elif line.startswith('        session_volume.commit()'): pass # skip
            else:
                if line.strip() == "":
                    out_lines.append(line)
                elif line.startswith("    try:") and "await client.connect()" in "".join(lines[i:i+3]):
                    out_lines.append("        try:\n")
                elif line.startswith("        await client.connect()"): pass # skip
                else:
                    out_lines.append("    " + line)
            i += 1
            continue

        if "get_user_ranking.remote.aio(" in line:
            out_lines.append(line.replace("get_user_ranking.remote.aio(", "TelegramAnalyticsService().get_user_ranking.remote.aio("))
        elif "get_user_messages.remote.aio(" in line:
            out_lines.append(line.replace("get_user_messages.remote.aio(", "TelegramAnalyticsService().get_user_messages.remote.aio("))
        elif "get_top_users_messages.remote.aio(" in line:
            out_lines.append(line.replace("get_top_users_messages.remote.aio(", "TelegramAnalyticsService().get_top_users_messages.remote.aio("))
        elif '"total_messages_in_period": len(all_messages),' in line and '"total_messages_in_period": len(all_messages),' in "".join(lines[i+1:i+2]):
            out_lines.append(line)
            i += 1
        else:
            out_lines.append(line)
            
        i += 1

    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

convert_to_class('modal_user_message.py')
