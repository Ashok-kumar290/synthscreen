import os
import json
import glob

def generate_docs():
    # Find all .md files, ignoring temp/ and hidden dirs
    md_files = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'temp']
        for file in files:
            if file.endswith('.md'):
                md_files.append(os.path.join(root, file))
    
    # Sort files to ensure stable ordering, perhaps README first
    md_files.sort(key=lambda x: (0 if os.path.basename(x).lower() == 'readme.md' else 1, x))
    
    docs_data = {}
    for filepath in md_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            # use relative path as key
            rel_path = os.path.relpath(filepath, '.')
            docs_data[rel_path] = f.read()

    # The HTML template
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Synthscreen Interactive Documentation</title>
    <!-- Use marked.js for Markdown to HTML conversion -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
            display: flex; 
            margin: 0; 
            height: 100vh; 
            overflow: hidden; 
            color: #24292e;
        }
        #sidebar { 
            width: 300px; 
            background: #f7f9fa; 
            border-right: 1px solid #e1e4e8; 
            padding: 20px; 
            overflow-y: auto; 
        }
        #content { 
            flex-grow: 1; 
            padding: 40px; 
            overflow-y: auto; 
            background: #ffffff;
        }
        .container {
            max-width: 900px; 
            margin: 0 auto; 
            line-height: 1.6;
        }
        h3.nav-title {
            margin-top: 0;
            color: #24292e;
            font-size: 16px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding-bottom: 10px;
            border-bottom: 1px solid #e1e4e8;
        }
        .sidebar-link { 
            display: block; 
            padding: 8px 12px; 
            color: #0366d6; 
            text-decoration: none; 
            border-radius: 6px; 
            margin-bottom: 5px; 
            font-size: 14px; 
            word-wrap: break-word;
        }
        .sidebar-link:hover { 
            background: #e1e4e8; 
        }
        .sidebar-link.active { 
            background: #0366d6; 
            color: white; 
            font-weight: 500;
        }
        
        /* Markdown Rendering Styles (Github-like) */
        #rendered-markdown h1, #rendered-markdown h2, #rendered-markdown h3 { 
            border-bottom: 1px solid #eaecef; 
            padding-bottom: 0.3em; 
            margin-top: 24px;
            margin-bottom: 16px;
        }
        #rendered-markdown pre { 
            background: #f6f8fa; 
            padding: 16px; 
            border-radius: 6px; 
            overflow: auto; 
            line-height: 1.45;
        }
        #rendered-markdown code { 
            font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace; 
            background: rgba(27,31,35,0.05); 
            border-radius: 3px; 
            padding: 0.2em 0.4em;
            font-size: 85%;
        }
        #rendered-markdown pre code {
            background: transparent;
            padding: 0;
        }
        #rendered-markdown img { 
            max-width: 100%; 
            box-sizing: content-box;
            background-color: #fff;
        }
        #rendered-markdown table { 
            border-collapse: collapse; 
            width: 100%; 
            margin-top: 0;
            margin-bottom: 16px; 
        }
        #rendered-markdown th, #rendered-markdown td { 
            border: 1px solid #dfe2e5; 
            padding: 6px 13px; 
        }
        #rendered-markdown th { 
            background-color: #f6f8fa; 
            font-weight: 600;
        }
        #rendered-markdown tr:nth-child(2n) {
            background-color: #f6f8fa;
        }
        #rendered-markdown blockquote {
            padding: 0 1em;
            color: #6a737d;
            border-left: 0.25em solid #dfe2e5;
            margin: 0 0 16px 0;
        }
    </style>
</head>
<body>
    <div id="sidebar">
        <h3 class="nav-title">Documents</h3>
        <div id="nav-links"></div>
    </div>
    <div id="content">
        <div class="container" id="rendered-markdown">Select a document from the sidebar to view.</div>
    </div>
    
    <script>
        const docsData = {{DOCS_JSON}};
        const navLinksContainer = document.getElementById('nav-links');
        const contentContainer = document.getElementById('rendered-markdown');
        
        let firstLink = null;
        
        for (const [filepath, content] of Object.entries(docsData)) {
            const a = document.createElement('a');
            a.href = '#';
            a.className = 'sidebar-link';
            a.textContent = filepath;
            a.onclick = (e) => {
                e.preventDefault();
                document.querySelectorAll('.sidebar-link').forEach(el => el.classList.remove('active'));
                a.classList.add('active');
                
                // Parse markdown and set HTML
                contentContainer.innerHTML = marked.parse(content);
                
                // Update URL hash for sharing/reloading
                window.location.hash = filepath;
                
                // Scroll to top
                document.getElementById('content').scrollTop = 0;
            };
            navLinksContainer.appendChild(a);
            
            // Look for requested hash
            if (window.location.hash.substring(1) === filepath) {
                firstLink = a;
            } else if (!firstLink && !window.location.hash) {
                firstLink = a;
            }
        }
        
        // Auto-click the correct link
        if (firstLink) {
            firstLink.click();
        } else if (navLinksContainer.firstChild) {
            navLinksContainer.firstChild.click();
        }
    </script>
</body>
</html>
"""
    
    # Inject JSON safely
    final_html = html_template.replace("{{DOCS_JSON}}", json.dumps(docs_data))
    
    out_path = os.path.join('docs', 'interactive_docs.html')
    os.makedirs('docs', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    print(f"Success! Interactive documentation generated at {out_path}")
    print(f"Included {len(docs_data)} markdown files.")

if __name__ == "__main__":
    generate_docs()
