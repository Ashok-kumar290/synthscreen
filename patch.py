import sys
import glob

def patch_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    if "render_global_sidebar" in content:
        return
        
    lines = content.split('\n')
    new_lines = []
    has_imported = False
    
    for line in lines:
        if line.startswith("from services.") and "ui" in line and not has_imported:
            new_lines.append("from services.sidebar import render_global_sidebar")
            has_imported = True
        new_lines.append(line)
        if line.startswith("apply_page_style()"):
            new_lines.append("render_global_sidebar()")
            
    with open(filepath, 'w') as f:
        f.write('\n'.join(new_lines))

for f in glob.glob("pages/*.py"):
    if "Archive" not in f:
        patch_file(f)
