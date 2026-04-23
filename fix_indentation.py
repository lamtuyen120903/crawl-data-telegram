def fix_indentation(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    inside_target_method = False
    new_lines = []
    
    for line in lines:
        if line.startswith('    @modal.method()'):
            inside_target_method = True
            new_lines.append(line)
            continue
            
        if inside_target_method:
            if line.startswith('    async def ') or line.startswith('        ') or line.strip() == '':
                # already correctly indented definitions or blank lines
                pass
            elif line.startswith('        client = self.client'):
                # already correctly indented
                pass
            elif line.startswith('    '):
                # it's indented by 4 spaces (old function body). Add 4 more spaces.
                line = '    ' + line
            elif line.startswith(')'):
                # end of def arguments
                line = '    ' + line
            elif line.startswith('    '):
                line = '    ' + line
                
            # Check for end of method
            # If we see the next decorator or class definition, we are out
            if line.startswith('@app') or line.startswith('class ') or line.startswith('# --- Web Endpoints ---'):
                inside_target_method = False
                
        new_lines.append(line)
        
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

fix_indentation('modal_user_message.py')
print("Indentation fixed")
