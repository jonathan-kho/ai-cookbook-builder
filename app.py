import streamlit as st
from groq import Groq
from PIL import Image
import io
import base64
import json
import re
import os

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
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        # Try to fix common issues
        # Remove trailing commas before closing braces/brackets
        json_text = json_text.replace(',}', '}').replace(',]', ']')

        # Try parsing again
        try:
            return json.loads(json_text)
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
                    recipe["steps"] = steps

                return recipe

            raise e

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

def generate_html_cookbook(recipes):
    """Generate beautiful HTML cookbook from recipes."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Personal Cookbook</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        .header {
            text-align: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .recipe {
            background: white;
            margin: 20px 0;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            break-inside: avoid;
        }
        .recipe-title {
            font-size: 28px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 20px;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        .section-title {
            font-size: 20px;
            font-weight: bold;
            color: #34495e;
            margin: 20px 0 10px 0;
        }
        .ingredients {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
        }
        .ingredient {
            margin: 5px 0;
            padding-left: 20px;
            position: relative;
        }
        .ingredient:before {
            content: "•";
            color: #3498db;
            font-weight: bold;
            position: absolute;
            left: 0;
        }
        .steps {
            counter-reset: step-counter;
        }
        .step {
            margin: 10px 0;
            padding-left: 30px;
            position: relative;
            line-height: 1.6;
        }
        .step:before {
            counter-increment: step-counter;
            content: counter(step-counter) ".";
            color: #e74c3c;
            font-weight: bold;
            position: absolute;
            left: 0;
            width: 25px;
            text-align: center;
        }
        @media print {
            body { background: white; }
            .recipe { break-inside: avoid; }
        }
        @media (max-width: 600px) {
            body { padding: 10px; }
            .recipe { padding: 15px; }
            .recipe-title { font-size: 24px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>My Personal Cookbook</h1>
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

st.title("Free AI Personal Cookbook Builder v0.1")

if "recipes" not in st.session_state or not isinstance(st.session_state.recipes, list):
    st.session_state.recipes = []
if "token_usage" not in st.session_state or not isinstance(st.session_state.token_usage, (int, float)):
    st.session_state.token_usage = 0

uploaded_files = st.file_uploader("Upload recipe images/photos/handwritten notes (multiple OK)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
text_input = st.text_area("Or paste recipe text here")

if st.button("Extract Recipe(s)"):
    with st.spinner("Extracting with AI..."):
        new_recipes = []
        total_tokens = 0

        # Vision for images
        for file in uploaded_files:
            try:
                # Validate and process image
                img = Image.open(file)
                # Convert to RGB if necessary (handles PNG with transparency)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # Resize large images to prevent API limits (max ~4MB base64)
                max_size = (1024, 1024)
                if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG", quality=85)
                base64_img = base64.b64encode(buffered.getvalue()).decode()
            except Exception as img_error:
                st.error(f"Failed to process image {file.name}: {str(img_error)[:50]}")
                continue

            try:
                response = client.chat.completions.create(
                    model="llava-v1.5-7b-4096-preview",  # Groq vision model
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract the recipe from this image and output ONLY valid JSON with no extra text or explanation. Format: {\"title\": \"Recipe Title\", \"ingredients\": [\"ingredient 1\", \"ingredient 2\"], \"steps\": [\"1. First step\", \"2. Second step\"]}. Read all text carefully."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                        ]
                    }],
                    max_tokens=500
                )
            except Exception as api_error:
                st.error(f"API error processing image {file.name}: {str(api_error)[:100]}")
                continue
            try:
                recipe = parse_recipe_json(response.choices[0].message.content)
                # Validate recipe structure
                if isinstance(recipe, dict) and 'title' in recipe:
                    new_recipes.append(recipe)
                    total_tokens += response.usage.total_tokens
                else:
                    st.error(f"Invalid recipe format from image {file.name}")
            except Exception as e:
                st.error(f"Failed to extract recipe from image: {str(e)[:100]}")

        # Text-only model for pasted text
        if text_input:
            try:
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",  # Fast text model
                    messages=[{"role": "user", "content": f"Extract the recipe from this text and output ONLY a JSON object with this exact format, no extra text, no markdown:\n\n{{\"title\": \"Recipe Title Here\", \"ingredients\": [\"ingredient 1\", \"ingredient 2\", \"etc\"], \"steps\": [\"1. First step\", \"2. Second step\", \"etc\"]}}\n\nRecipe text to extract from:\n{text_input}"}],
                    max_tokens=800  # Increased for complex recipes
                )
            except Exception as api_error:
                st.error(f"API error processing text: {str(api_error)[:100]}")
                text_input = None  # Skip text processing
            try:
                recipe = parse_recipe_json(response.choices[0].message.content)
                # Validate recipe structure
                if isinstance(recipe, dict) and 'title' in recipe:
                    new_recipes.append(recipe)
                    total_tokens += response.usage.total_tokens
                else:
                    st.error("Invalid recipe format from text")
            except Exception as e:
                st.error(f"Failed to extract recipe from text: {str(e)[:100]}")

        # Only add valid recipes
        valid_recipes = [r for r in new_recipes if isinstance(r, dict) and 'title' in r]
        st.session_state.recipes.extend(valid_recipes)
        st.session_state.token_usage += total_tokens
        st.success(f"Added {len(valid_recipes)} recipe(s)! Total recipes: {len(st.session_state.recipes)}")
        st.info(f"Tokens used this extraction: {total_tokens} | Cumulative: {st.session_state.token_usage}")

if st.session_state.recipes:
    st.write("Current recipes in cookbook:")
    for i, r in enumerate(st.session_state.recipes):
        st.write(f"**{r.get('title', 'Untitled')}** - {len(r.get('ingredients', []))} ingredients")

    if st.button("Generate & Download Cookbook"):
        # Check if we have recipes
        if not st.session_state.recipes:
            st.error("No recipes to generate cookbook from. Please extract some recipes first.")
        else:
            st.write(f"Found {len(st.session_state.recipes)} recipes to process")

            # Generate beautiful HTML cookbook
            html_content = generate_html_cookbook(st.session_state.recipes)

            # Convert to bytes for download
            html_bytes = html_content.encode('utf-8')

            st.download_button(
                "Download Cookbook (HTML)",
                html_bytes,
                "my_cookbook.html",
                "text/html"
            )
            st.success("Cookbook ready! Download as HTML for perfect mobile viewing.")

            # Also show preview
            st.markdown("### Preview:")
            st.html(html_content)

st.caption("v0.1 - Free via Groq API (rate limits apply). For testing only.")
st.info(f"Total tokens used in session: {st.session_state.token_usage}")
