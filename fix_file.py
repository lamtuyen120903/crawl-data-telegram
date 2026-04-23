import re

def fix_indentation(filename):
    with open(filename, "r") as f:
        code = f.read()

    def fix_func(func_name, code):
        
        # Matches the def ... ): segment
        pattern = f'    @modal\\.method\\(\\)\\n    async def {func_name}\\(.*?\\):\\n'
        match = re.search(pattern, code, re.DOTALL)
        if not match: 
            print(f"Match failed for {func_name}")
            return code
        
        start_idx = match.end()
        # Find the end of the function (either the next @modal.method or # --- Session Management)
        # We know the next sections after the 3 methods are the Web Endpoints
        end_match = re.search(r'\\n# --- Web Endpoints', code[start_idx:])
        
        if end_match:
            end_idx = start_idx + end_match.start()
        else:
            # Maybe it's the next function
            next_func = re.search(r'\\n    @modal\\.method', code[start_idx:])
            if next_func:
                end_idx = start_idx + next_func.start()
            else:
                return code
        
        body = code[start_idx:end_idx]
        
        # Add 4 spaces to every line in the body that isn't empty
        fixed_body = ""
        for line in body.split('\\n'):
            if line.strip():
                fixed_body += '    ' + line + '\\n'
            else:
                fixed_body += '\\n'
                
        # Also, wait! If there are remaining finally: blocks, they were 4 spaces.
        return code[:start_idx] + fixed_body.rstrip('\\n') + code[end_idx:]

    code = fix_func("get_user_ranking", code)
    code = fix_func("get_user_messages", code)
    code = fix_func("get_top_users_messages", code)

    with open(filename, "w") as f:
        f.write(code)

fix_indentation("modal_user_message.py")
print("Indentation fixed.")
