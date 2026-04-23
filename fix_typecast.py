import re

def safe_int(val, default):
    return f"int({val}) if {val} else {default}"

with open("modal_user_message.py", "r", encoding="utf-8") as f:
    text = f.read()

# Replace days=int(days) -> days=int(days) if days else 0
text = text.replace("days=int(days),", "days=int(days) if days else 0,")
# For backward compatibility maybe it's better to raise an error if days is empty?
# Wait, if days is "", then `if days is None:` check passes.
# We should update the check to `if not days:` assuming days=0 is invalid anyway.
# Let's fix the validation instead of just the cast!

validation_old_1 = """    if days is None:
        return {"error": "Missing required 'days' parameter"}"""

validation_new_1 = """    if not days and days != 0:
        return {"error": "Missing required 'days' parameter (cannot be empty)"}"""

text = text.replace(validation_old_1, validation_new_1)

validation_old_2 = """    if limit is None:
        return {"error": "Missing required 'limit' parameter"}"""

validation_new_2 = """    if not limit and limit != 0:
        return {"error": "Missing required 'limit' parameter (cannot be empty)"}"""

text = text.replace(validation_old_2, validation_new_2)

validation_old_3 = """    if download_media is None:
        return {"error": "Missing required 'download_media' parameter"}"""
        
validation_new_3 = """    if download_media is None or download_media == "":
        return {"error": "Missing required 'download_media' parameter"}"""

text = text.replace(validation_old_3, validation_new_3)


# Also cast safely
text = text.replace("limit=int(limit)", "limit=int(limit) if limit else 0")
text = text.replace("top_n=int(top_n)", "top_n=int(top_n) if top_n else 3")

with open("modal_user_message.py", "w", encoding="utf-8") as f:
    f.write(text)

