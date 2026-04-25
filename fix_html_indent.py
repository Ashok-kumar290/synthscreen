import re
from pathlib import Path

def dedent_html(file_path):
    p = Path(file_path)
    content = p.read_text()
    
    # Just remove all leading spaces before <div, <span, <p, <svg, <circle, </div
    content = re.sub(r'^[ \t]+(<(?:div|span|p|svg|circle|/div|/span|/p|/svg|h[1-6]|/h[1-6]|strong|/strong|section|/section|style|/style))', r'\1', content, flags=re.MULTILINE)
    
    p.write_text(content)

dedent_html("pages/1_Screening.py")
dedent_html("services/ui.py")
dedent_html("pages/3_Review.py")
dedent_html("pages/4_Analytics.py")
dedent_html("pages/5_Intelligence.py")
dedent_html("pages/2_Inbox.py")

