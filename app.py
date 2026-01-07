import streamlit as st
from groq import Groq
from PIL import Image
import io
import base64
import json
import re
import os
from docx import Document
from docx.shared import Inches

def parse_recipe_json(response_text):
    """Parse JSON from AI response, with robust error handling."""
    text = response_text.strip()

    # Remove markdown code blocks
    if text.startswith("```json"):
        text = text[7:].split("```")[0].strip()
    elif text.startswith("```"):
        text = text[3:].split("```")[0].strip()

    # Extract JSON object - find the outermost braces
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")

    brace_count = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break

    if brace_count != 0:
        # Fallback: find last closing brace
        end = text.rfind('}') + 1

    if end <= start:
        raise ValueError("Invalid JSON structure")

    json_text = text[start:end]

    try:
        recipe = json.loads(json_text)
        # Clean up double numbering in steps
        if 'steps' in recipe and recipe['steps']:
            recipe['steps'] = [clean_step_numbering(step) for step in recipe['steps']]
        return recipe
    except json.JSONDecodeError as e:
        # Try to fix common issues
        # Remove trailing commas before closing braces/brackets
        json_text = json_text.replace(',}', '}').replace(',]', ']')

        # Try parsing again
        try:
            recipe = json.loads(json_text)
            # Clean up double numbering in steps
            if 'steps' in recipe and recipe['steps']:
                recipe['steps'] = [clean_step_numbering(step) for step in recipe['steps']]
            return recipe
        except json.JSONDecodeError:
            # As a last resort, try to extract basic structure manually
            title_match = re.search(r'"title"\s*:\s*"([^"]*)"', json_text, re.IGNORECASE)
            ingredients_match = re.search(r'"ingredients"\s*:\s*\[([^\]]*)\]', json_text, re.DOTALL)
            steps_match = re.search(r'"steps"\s*:\s*\[([^\]]*)\]', json_text, re.DOTALL)

            if title_match:
                recipe = {"title": title_match.group(1), "ingredients": [], "steps": []}

                if ingredients_match:
                    # Extract ingredients
                    ing_text = ingredients_match.group(1)
                    ingredients = re.findall(r'"([^"]*)"', ing_text)
                    recipe["ingredients"] = ingredients

                if steps_match:
                    # Extract steps
                    steps_text = steps_match.group(1)
                    steps = re.findall(r'"([^"]*)"', steps_text)
                    # Clean up double numbering
                    recipe["steps"] = [clean_step_numbering(step) for step in steps]

                return recipe

            raise e

def clean_step_numbering(step_text):
    """Clean up double numbering in step text (e.g., '1. 1. Do something' -> '1. Do something')."""
    if not step_text:
        return step_text

    # Pattern to match double numbering like "1. 1. " or "2. 2. "
    double_number_pattern = r'^(\d+)\.\s+\1\.\s+'
    cleaned = re.sub(double_number_pattern, r'\1. ', step_text.strip())

    return cleaned

def strip_step_numbering(step_text):
    """Remove numbering from the beginning of step text (e.g., '1. Do something' -> 'Do something')."""
    if not step_text:
        return step_text

    # Pattern to match single numbering like "1. ", "2. ", etc.
    single_number_pattern = r'^\d+\.\s+'
    cleaned = re.sub(single_number_pattern, '', step_text.strip())

    return cleaned

# Initialize Groq client
try:
    # Try Streamlit secrets first
    api_key = None
    try:
        if "GROQ_API_KEY" in st.secrets:
            api_key = st.secrets["GROQ_API_KEY"]
    except:
        pass  # Secrets not available, try other sources

    # Try environment variable
    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY")

    # Try config.py as last resort
    if not api_key:
        try:
            import config
            api_key = config.GROQ_API_KEY
        except ImportError:
            pass

    if not api_key:
        st.error("GROQ_API_KEY not found. Please set it in:")
        st.error("- config.py file")
        st.error("- GROQ_API_KEY environment variable")
        st.error("- Streamlit secrets (for cloud deployment)")
        st.stop()

    client = Groq(api_key=api_key)
except Exception as e:
    st.error(f"Failed to initialize Groq client: {e}")
    st.stop()

def generate_html_cookbook(recipes, title="My Personal Cookbook"):
    """Generate beautiful HTML cookbook from recipes."""
    css = """
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; color: #333; }
        .header { text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .recipe { background: white; margin: 20px 0; padding: 25px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); break-inside: avoid; }
        .recipe-title { font-size: 28px; font-weight: bold; color: #2c3e50; margin-bottom: 20px; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        .section-title { font-size: 20px; font-weight: bold; color: #34495e; margin: 20px 0 10px 0; }
        .ingredients { background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; }
        .ingredient { margin: 5px 0; padding-left: 20px; position: relative; }
        .ingredient:before { content: "•"; color: #3498db; font-weight: bold; position: absolute; left: 0; }
        .steps { counter-reset: step-counter; }
        .step { margin: 10px 0; padding-left: 30px; position: relative; line-height: 1.6; }
        .step:before { counter-increment: step-counter; content: counter(step-counter) "."; color: #e74c3c; font-weight: bold; position: absolute; left: 0; width: 25px; text-align: center; }
        @media print { body { background: white; } .recipe { break-inside: avoid; } }
        @media (max-width: 600px) { body { padding: 10px; } .recipe { padding: 15px; } .recipe-title { font-size: 24px; } }
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <p>Created with AI - Perfect for mobile and printing</p>
    </div>
"""

    for recipe in recipes:
        title = recipe.get('title', 'Untitled Recipe')
        ingredients = recipe.get('ingredients', [])
        steps = recipe.get('steps', [])

        html += f"""
    <div class="recipe">
        <div class="recipe-title">{title}</div>

        <div class="section-title">Ingredients</div>
        <div class="ingredients">"""

        if ingredients:
            for ing in ingredients:
                html += f'<div class="ingredient">{ing}</div>'
        else:
            html += '<div class="ingredient">No ingredients listed</div>'

        html += """
        </div>

        <div class="section-title">Instructions</div>
        <div class="steps">"""

        if steps:
            for step in steps:
                html += f'<div class="step">{step}</div>'
        else:
            html += '<div class="step">No steps listed</div>'

        html += """
        </div>
    </div>"""

    html += """
</body>
</html>"""

    return html

def generate_docx_cookbook(recipes):
    doc = Document()

    # Set margins for print-friendly layout
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    # Title page
    doc.add_heading('My Personal Cookbook', 0).alignment = 1  # Centered
    doc.add_paragraph('Created with AI • Edit me in Google Docs or Word • Add photos & cover!')
    doc.add_page_break()

    for recipe in recipes:
        title = recipe.get('title', 'Untitled Recipe')
        ingredients = recipe.get('ingredients', [])
        steps = recipe.get('steps', [])

        doc.add_heading(title, level=1)

        doc.add_heading('Ingredients', level=2)
        for ing in ingredients:
            doc.add_paragraph(ing, style='List Bullet')

        doc.add_heading('Instructions', level=2)
        for i, step in enumerate(steps, 1):
            # Remove existing numbering and manually add our own
            clean_step = strip_step_numbering(step)
            p = doc.add_paragraph()
            p.add_run(f"{i}. ").bold = True
            p.add_run(clean_step)

        doc.add_page_break()  # One recipe per page initially

    return doc

st.title("AI Cookbook Builder")

# Initialize session state
if "recipes" not in st.session_state:
    st.session_state.recipes = []
if "token_usage" not in st.session_state:
    st.session_state.token_usage = 0

st.markdown("Upload recipe photos or paste recipe text to extract and create beautiful cookbooks.")

uploaded_files = st.file_uploader("Recipe photos", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
text_input = st.text_area("Or paste recipe text")

if st.button("🔍 Extract Recipes", use_container_width=True):
    with st.spinner("Analyzing recipes..."):
        new_recipes = []
        total_tokens = 0

        # Improved vision extraction
        for file in uploaded_files:
            try:
                img = Image.open(file)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                max_size = (2048, 2048)  # Preserve text detail
                if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG", quality=95)
                base64_img = base64.b64encode(buffered.getvalue()).decode()
            except Exception as e:
                st.error(f"❌ Failed to process {file.name}. Try another image.")
                continue

            try:
                response = client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",  # Latest free vision model
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract recipe EXACTLY. Output ONLY valid JSON, no extra text/markdown. Preserve EVERY quantity, unit, fraction, and full original phrasing verbatim in ingredients (e.g., \"2½ cups (300g) unsalted butter, softened\"). Extract steps as they appear WITHOUT adding your own numbering. If steps are already numbered in the image, keep them as-is. Format precisely: {\"title\": \"Title\", \"ingredients\": [\"full ingredient line with quantity\", ...], \"steps\": [\"Full step text as appears in image\", ...]}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                        ]
                    }],
                    max_tokens=1500
                )
                recipe = parse_recipe_json(response.choices[0].message.content)
                if 'title' in recipe and recipe.get('ingredients'):
                    new_recipes.append(recipe)
                    total_tokens += response.usage.total_tokens
                else:
                    st.warning(f"Could not extract complete recipe from {file.name}")
            except Exception as e:
                st.error("❌ Image processing failed. Try a different image.")

        # Upgraded text extraction (free 70B model)
        if text_input:
            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",  # Latest free-tier 70B text model
                    messages=[{
                        "role": "user",
                        "content": "Extract recipe EXACTLY from this text. Output ONLY valid JSON, no extra text/markdown/explanation. Preserve EVERY quantity, unit, fraction, and full original phrasing verbatim in each ingredient (critical for accuracy — never simplify or omit). Extract steps as they appear in the original text WITHOUT adding your own numbering or prefixes. If steps are already numbered in the source, keep them as-is. Exact format:\n{\"title\": \"Recipe Title\", \"ingredients\": [\"full ingredient line with quantity\", ...], \"steps\": [\"Full step text as appears in source\", ...]}\n\nText:\n" + text_input
                    }],
                    max_tokens=1500
                )
                recipe = parse_recipe_json(response.choices[0].message.content)
                if 'title' in recipe and recipe.get('ingredients'):
                    new_recipes.append(recipe)
                    total_tokens += response.usage.total_tokens
                else:
                    st.warning("Could not extract complete recipe from text")
            except Exception as e:
                st.error("❌ Text processing failed. Please check your input.")

        st.session_state.recipes.extend(new_recipes)
        st.session_state.token_usage += total_tokens
        st.success(f"✅ Added {len(new_recipes)} recipe(s) to your collection!")

if st.session_state.recipes:
    st.markdown(f"**📚 {len(st.session_state.recipes)} recipes collected**")

    with st.expander("View recipes", expanded=False):
        for i, r in enumerate(st.session_state.recipes):
            st.markdown(f"**{r.get('title', 'Untitled')}** - {len(r.get('ingredients', []))} ingredients")

    # Cookbook customization
    col1, col2 = st.columns([2, 1])

    with col1:
        if "cookbook_title" not in st.session_state:
            st.session_state.cookbook_title = "My Personal Cookbook"

        cookbook_title = st.text_input(
            "Cookbook Title",
            value=st.session_state.cookbook_title
        )
        st.session_state.cookbook_title = cookbook_title

    with col2:
        if st.button("Generate & Download Cookbook"):
            if not st.session_state.recipes:
                st.error("No recipes yet!")
            else:
                # HTML preview (keep existing)
                html_content = generate_html_cookbook(st.session_state.recipes)
                html_bytes = html_content.encode('utf-8')
                st.download_button("Download Preview (HTML)", html_bytes, "preview_cookbook.html", "text/html")
                st.markdown("### Live Preview")
                st.html(html_content)

                # New: DOCX editable download
                doc = generate_docx_cookbook(st.session_state.recipes)
                docx_bytes = io.BytesIO()
                doc.save(docx_bytes)
                docx_bytes.seek(0)

                st.download_button(
                    "Download Editable Cookbook (DOCX)",
                    docx_bytes.getvalue(),
                    "my_editable_cookbook.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                st.success("DOCX ready! Edit → Export PDF → Print professionally.")

# Clean, minimal footer
st.markdown("---")
st.markdown("*Powered by AI • Free to use • Mobile-friendly*")
