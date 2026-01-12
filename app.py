import streamlit as st
from groq import Groq
from PIL import Image
import io
import base64
import json
import re
import os
import requests
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Inches
from datetime import datetime


def parse_recipe_json(response_text):
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:].split("```")[0].strip()
    elif text.startswith("```"):
        text = text[3:].split("```")[0].strip()
    start = text.find('{')
    if start == -1:
        return None
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
        end = text.rfind('}') + 1
    json_text = text[start:end]
    try:
        recipe = json.loads(json_text)
        if 'steps' in recipe:
            recipe['steps'] = [clean_step_numbering(s) for s in recipe['steps']]
        return recipe
    except json.JSONDecodeError:
        json_text = json_text.replace(',}', '}').replace(',]', ']')
        try:
            recipe = json.loads(json_text)
            if 'steps' in recipe:
                recipe['steps'] = [clean_step_numbering(s) for s in recipe['steps']]
            return recipe
        except:
            return None


def clean_step_numbering(step_text):
    if not step_text:
        return step_text
    return re.sub(r'^(\d+)\.\s+\1\.\s+', r'\1. ', step_text.strip())


def strip_step_numbering(step_text):
    if not step_text:
        return step_text
    return re.sub(r'^\d+\.\s*', '', step_text.strip())


def extract_schema_recipe(soup):
    """Extract recipe from schema.org JSON-LD if available."""
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            content = script.string or ''
            if not content.strip():
                continue
            data = json.loads(content)
            candidates = []
            if isinstance(data, dict):
                if data.get('@type') == 'Recipe':
                    candidates.append(data)
                if '@graph' in data:
                    candidates.extend([item for item in data['@graph'] if item.get('@type') == 'Recipe'])
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        if item.get('@type') == 'Recipe':
                            candidates.append(item)
                        if '@graph' in item:
                            candidates.extend([g for g in item['@graph'] if g.get('@type') == 'Recipe'])
            
            for rec in candidates:
                title = rec.get('name', 'Untitled Recipe')
                ingredients = rec.get('recipeIngredient', [])
                if not isinstance(ingredients, list):
                    ingredients = []
                ingredients = [str(ing).strip() for ing in ingredients if ing]
                
                steps = []
                instructions = rec.get('recipeInstructions', [])
                if isinstance(instructions, list):
                    for step in instructions:
                        if isinstance(step, str):
                            steps.append(step.strip())
                        elif isinstance(step, dict):
                            text = step.get('text') or step.get('name') or ''
                            steps.append(text.strip())
                elif isinstance(instructions, str):
                    steps.append(instructions.strip())
                
                if title != 'Untitled Recipe' and ingredients:
                    return {
                        "title": title,
                        "ingredients": ingredients,
                        "steps": [s for s in steps if s]
                    }
        except:
            continue
    return None


# Groq client
try:
    api_key = None
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except:
        pass  # No secrets.toml, continue to other sources

    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        try:
            import config
            api_key = config.GROQ_API_KEY
        except:
            pass

    if not api_key:
        st.error("GROQ_API_KEY not found. Please set it in:")
        st.error("- config.py file")
        st.error("- GROQ_API_KEY environment variable")
        st.error("- Streamlit secrets (.streamlit/secrets.toml)")
        st.stop()

    client = Groq(api_key=api_key)
except Exception as e:
    st.error(f"Groq init failed: {e}")
    st.stop()


def generate_html_cookbook(recipes, title):
    css = """
        body { font-family: Georgia, serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #fdfdfd; color: #333; line-height: 1.6; }
        .header { text-align: center; padding: 60px 20px; background: linear-gradient(135deg, #f9e4d4 0%, #f7d0c0 100%); border-radius: 20px; margin-bottom: 50px; }
        .recipe { background: white; padding: 40px; margin: 40px 0; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }
        .recipe-title { font-size: 32px; color: #d35400; border-bottom: 3px solid #e74c3c; padding-bottom: 10px; }
        .section-title { font-size: 24px; color: #c0392b; margin: 30px 0 15px; }
        .ingredients { padding: 20px; background: #fef9e8; border-radius: 10px; }
        .ingredient { margin: 10px 0; padding-left: 10px; }
        .steps { padding-left: 10px; }
        .step { margin: 20px 0; }
        .step-number { font-weight: bold; color: #e74c3c; margin-right: 10px; }
        @media print { body { background: white; margin: 0; } .recipe { box-shadow: none; page-break-inside: avoid; } }
    """
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{title}</title>
<style>{css}</style></head><body>
<div class="header"><h1>{title}</h1><p>Our Family Recipes • {datetime.now().strftime('%B %Y')}</p></div>
"""
    for recipe in recipes:
        html += f'<div class="recipe"><div class="recipe-title">{recipe.get("title", "Untitled")}</div>'
        html += '<div class="section-title">Ingredients</div><div class="ingredients">'
        for ing in recipe.get("ingredients", []):
            html += f'<div class="ingredient">• {ing}</div>'
        html += '</div><div class="section-title">Instructions</div><div class="steps">'
        for i, step in enumerate(recipe.get("steps", []), 1):
            clean = strip_step_numbering(step)
            html += f'<div class="step"><span class="step-number">{i}.</span>{clean}</div>'
        html += '</div></div>'
    html += '</body></html>'
    return html


def generate_docx_cookbook(recipes, title, one_per_page):
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)

    # Cover
    doc.add_heading(title, 0).alignment = 1
    p = doc.add_paragraph('Our Family Recipes\n\nCollected with love')
    p.alignment = 1
    doc.add_paragraph(f"{datetime.now().strftime('%B %Y')}").alignment = 1
    doc.add_page_break()

    # Simple index
    doc.add_heading('Recipes', level=1)
    for i, recipe in enumerate(recipes, 1):
        doc.add_paragraph(f"{i}. {recipe.get('title', 'Untitled')}", style='List Number')
    doc.add_page_break()

    # Recipes
    for recipe in recipes:
        doc.add_heading(recipe.get('title', 'Untitled'), level=1)
        doc.add_heading('Ingredients', level=2)
        for ing in recipe.get('ingredients', []):
            doc.add_paragraph(ing, style='List Bullet')
        doc.add_heading('Instructions', level=2)
        for i, step in enumerate(recipe.get('steps', []), 1):
            clean = strip_step_numbering(step)
            p = doc.add_paragraph()
            p.add_run(f"{i}. ").bold = True
            p.add_run(clean)
        if one_per_page:
            doc.add_page_break()

    return doc


# App UI
st.set_page_config(page_title="Family Cookbook", layout="centered")
st.title("🍲 Our Family Cookbook")

st.markdown("""
**Create a beautiful printable cookbook from recipes your family sends you.**

Family can send:
- Recipe website links (most common – just paste them!)
- Photos of handwritten recipes (save to your device and upload)
- Copied recipe text

The app extracts everything perfectly.  
The final Word file is fully editable – add photos, rearrange, export PDF for printing/binding.
""")

if "recipes" not in st.session_state:
    st.session_state.recipes = []
if "cookbook_title" not in st.session_state:
    st.session_state.cookbook_title = "Our Family Cookbook"

cookbook_title = st.text_input("Cookbook title", value=st.session_state.cookbook_title)
st.session_state.cookbook_title = cookbook_title

st.markdown("### Add recipes")
col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Upload recipe photos", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
with col2:
    recipe_links = st.text_area("Paste recipe website links (one per line)")

text_input = st.text_area("Or paste recipe text")

if st.button("✨ Extract & Add Recipes", type="primary", use_container_width=True):
    if not (uploaded_files or recipe_links.strip() or text_input.strip()):
        st.warning("Please add something first.")
    else:
        with st.spinner("Extracting recipes..."):
            new_recipes = []

            # Process uploaded files (photos)
            for file in uploaded_files or []:
                try:
                    img = Image.open(file).convert('RGB')
                    buffered = io.BytesIO()
                    img.save(buffered, format="JPEG", quality=95)
                    base64_img = base64.b64encode(buffered.getvalue()).decode()
                    response = client.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        messages=[{"role": "user", "content": [
                            {"type": "text", "text": "Extract the recipe EXACTLY as JSON only. Preserve all quantities, units, and original text. Keep steps exactly as shown. Format: {\"title\": \"...\", \"ingredients\": [\"...\"], \"steps\": [\"...\"]}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                        ]}],
                        max_tokens=1500
                    )
                    recipe = parse_recipe_json(response.choices[0].message.content)
                    if recipe and recipe.get('title') and recipe.get('ingredients'):
                        new_recipes.append(recipe)
                except:
                    st.error(f"Failed to process {file.name}")

            # Process website links ONLY
            for url in [u.strip() for u in recipe_links.splitlines() if u.strip()]:
                try:
                    headers = {"User-Agent": "Mozilla/5.0 (compatible; FamilyCookbook/1.0)"}
                    resp = requests.get(url, headers=headers, timeout=15)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    
                    # First: structured schema
                    recipe = extract_schema_recipe(soup)
                    if recipe:
                        new_recipes.append(recipe)
                        continue
                    
                    # Fallback: clean text + LLM
                    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "advert"]):
                        tag.decompose()
                    page_text = soup.get_text(separator='\n', strip=True)
                    if len(page_text) > 15000:
                        page_text = page_text[:15000] + "\n\n... (truncated)"
                    
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": f"""Extract ONLY the main recipe from this webpage text as valid JSON. 
Preserve exact ingredient lines and step phrasing. 
Format: {{"title": "Recipe Name", "ingredients": ["full line 1", "full line 2"], "steps": ["step 1", "step 2"]}}

Text:
{page_text}"""}],
                        max_tokens=1500
                    )
                    recipe = parse_recipe_json(response.choices[0].message.content)
                    if recipe and recipe.get('title') and recipe.get('ingredients'):
                        new_recipes.append(recipe)
                except Exception as e:
                    st.warning(f"Could not extract recipe from: {url}")

            # Process text input
            if text_input.strip():
                try:
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": f"Extract the recipe EXACTLY as JSON only. Preserve everything. Format: {{\"title\": \"...\", \"ingredients\": [...], \"steps\": [...]}}\n\nText:\n{text_input}"}],
                        max_tokens=1500
                    )
                    recipe = parse_recipe_json(response.choices[0].message.content)
                    if recipe and recipe.get('title') and recipe.get('ingredients'):
                        new_recipes.append(recipe)
                except:
                    st.error("Text extraction failed")

            # Dedupe and add
            titles = {r['title'].lower() for r in st.session_state.recipes}
            added = 0
            for r in new_recipes:
                if r['title'].lower() not in titles:
                    st.session_state.recipes.append(r)
                    titles.add(r['title'].lower())
                    added += 1

            if added:
                st.success(f"Added {added} new recipe(s)!")
                st.session_state.recipes.sort(key=lambda r: r.get('title', '').lower())
                st.rerun()
            else:
                st.info("No new recipes added (possible duplicates or extraction issues).")

# Current collection display, backup, generate (unchanged from previous version)

if st.session_state.recipes:
    st.markdown(f"### Your recipes ({len(st.session_state.recipes)})")
    for i in range(len(st.session_state.recipes)-1, -1, -1):
        r = st.session_state.recipes[i]
        col1, col2 = st.columns([6,1])
        with col1:
            st.markdown(f"**{r.get('title', 'Untitled')}**")
        with col2:
            if st.button("Remove", key=f"rem_{i}"):
                st.session_state.recipes.pop(i)
                st.rerun()

    with st.expander("💾 Save/Load progress (for working over multiple days)"):
        col1, col2 = st.columns(2)
        with col1:
            json_data = json.dumps(st.session_state.recipes, indent=4, ensure_ascii=False)
            st.download_button(
                "Download backup",
                json_data,
                "cookbook_backup.json",
                "application/json"
            )
        with col2:
            backup_file = st.file_uploader("Upload backup", type="json", key="backup")
            if backup_file:
                try:
                    imported = json.load(backup_file)
                    st.session_state.recipes = imported
                    st.success("Progress restored!")
                    st.rerun()
                except:
                    st.error("Invalid backup file")

    st.markdown("### Generate your cookbook")
    one_per_page = st.checkbox("One recipe per page (recommended for printing)", value=True)

    if st.button("📖 Create Cookbook", type="primary", use_container_width=True):
        if not st.session_state.recipes:
            st.error("No recipes yet!")
        else:
            # DOCX
            doc = generate_docx_cookbook(st.session_state.recipes, cookbook_title, one_per_page)
            docx_io = io.BytesIO()
            doc.save(docx_io)
            docx_io.seek(0)

            st.download_button(
                "📄 Download Editable Word File (.docx)",
                docx_io.getvalue(),
                f"{cookbook_title.replace(' ', '_')}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )

            # HTML preview
            html = generate_html_cookbook(st.session_state.recipes, cookbook_title)
            st.markdown("#### 📱 Live Preview (great on phone too)")
            st.html(html)

            st.success("Cookbook ready! Open the .docx to customize and print ❤️")

st.caption("Made with love and AI • Simple, private, and free to use")
