import re
from pathlib import Path

def replace_newlines(file_path):
    p = Path(file_path)
    content = p.read_text()
    
    # Replace st.markdown(..., unsafe_allow_html=True) with a flattened string
    # We can just look for st.markdown(xxx, unsafe_allow_html=True) 
    # But since xxx could be a variable, let's just do a string replacement.
    
    # In pages/1_Screening.py:
    content = content.replace("st.markdown(\n        f\"\"\"", 'card_html = f"""')
    content = content.replace("        \"\"\",\n        unsafe_allow_html=True\n    )", '    st.markdown(card_html.replace("\\n", " "), unsafe_allow_html=True)')
    
    content = content.replace("st.markdown(summary_html, unsafe_allow_html=True)", 'st.markdown(summary_html.replace("\\n", " "), unsafe_allow_html=True)')
    
    p.write_text(content)

replace_newlines("pages/1_Screening.py")

def fix_review(file_path):
    p = Path(file_path)
    content = p.read_text()
    content = content.replace("st.markdown(render_verdict_strip(case), unsafe_allow_html=True)", 'st.markdown(render_verdict_strip(case).replace("\\n", " "), unsafe_allow_html=True)')
    
    # Also fix the case card
    content = content.replace("st.markdown(\n        f\"\"\"", 'card_html = f"""')
    content = content.replace("        \"\"\",\n        unsafe_allow_html=True,\n    )", '    st.markdown(card_html.replace("\\n", " "), unsafe_allow_html=True)')
    
    p.write_text(content)

fix_review("pages/3_Review.py")

def fix_ui(file_path):
    p = Path(file_path)
    content = p.read_text()
    content = content.replace("st.markdown(\n        f\"\"\"", 'html_str = f"""')
    content = content.replace("        \"\"\",\n        unsafe_allow_html=True,\n    )", '    st.markdown(html_str.replace("\\n", " "), unsafe_allow_html=True)')
    
    content = content.replace('st.markdown(\n        f"""', 'html_str = f"""')
    content = content.replace('        """,\n        unsafe_allow_html=True\n    )', '    st.markdown(html_str.replace("\\n", " "), unsafe_allow_html=True)')

    # there are other st.markdowns
    content = content.replace('st.markdown(f"<div', 'st.markdown((f"<div')
    content = content.replace('unsafe_allow_html=True)', 'unsafe_allow_html=True)')
    
    p.write_text(content)

fix_ui("services/ui.py")

