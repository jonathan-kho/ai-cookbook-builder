import streamlit as st
from groq import Groq
from PIL import Image
import io
import base64
import json
import re
from fpdf import FPDF
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

st.title("Free AI Personal Cookbook Builder v0.1")

if "recipes" not in st.session_state:
    st.session_state.recipes = []
if "token_usage" not in st.session_state:
    st.session_state.token_usage = 0

uploaded_files = st.file_uploader("Upload recipe images/photos/handwritten notes (multiple OK)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
text_input = st.text_area("Or paste recipe text here")

if st.button("Extract Recipe(s)"):
    with st.spinner("Extracting with AI..."):
        new_recipes = []
        total_tokens = 0

        # Vision for images
        for file in uploaded_files:
            img = Image.open(file)
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")
            base64_img = base64.b64encode(buffered.getvalue()).decode()

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
            try:
                recipe = parse_recipe_json(response.choices[0].message.content)
                new_recipes.append(recipe)
                total_tokens += response.usage.total_tokens
            except Exception as e:
                st.error(f"Failed to extract recipe from image: {str(e)[:100]}")

        # Text-only model for pasted text
        if text_input:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",  # Fast text model
                messages=[{"role": "user", "content": f"Extract the recipe from this text and output ONLY a JSON object with this exact format, no extra text, no markdown:\n\n{{\"title\": \"Recipe Title Here\", \"ingredients\": [\"ingredient 1\", \"ingredient 2\", \"etc\"], \"steps\": [\"1. First step\", \"2. Second step\", \"etc\"]}}\n\nRecipe text to extract from:\n{text_input}"}],
                max_tokens=800  # Increased for complex recipes
            )
            try:
                recipe = parse_recipe_json(response.choices[0].message.content)
                new_recipes.append(recipe)
                total_tokens += response.usage.total_tokens
            except Exception as e:
                st.error(f"Failed to extract recipe from text: {str(e)[:100]}")

        st.session_state.recipes.extend(new_recipes)
        st.session_state.token_usage += total_tokens
        st.success(f"Added {len(new_recipes)} recipe(s)! Total recipes: {len(st.session_state.recipes)}")
        st.info(f"Tokens used this extraction: {total_tokens} | Cumulative: {st.session_state.token_usage}")

if st.session_state.recipes:
    st.write("Current recipes in cookbook:")
    for i, r in enumerate(st.session_state.recipes):
        st.write(f"**{r.get('title', 'Untitled')}** - {len(r.get('ingredients', []))} ingredients")

    if st.button("Generate & Download PDF Cookbook"):
        def clean_text(text):
            """Clean text for PDF - remove all non-ASCII and control chars."""
            if not text:
                return ""
            # Replace common Unicode chars
            replacements = {
                '°': '°', '½': '1/2', '¼': '1/4', '¾': '3/4',
                '–': '-', '—': '-', '"': '"', '"': '"',
                ''': "'", ''': "'", '…': '...',
                '\t': ' ', '\n': ' ', '\r': ' '  # Replace tabs/newlines with spaces
            }
            for old, new in replacements.items():
                text = text.replace(old, new)
            # Keep only printable ASCII, no control characters
            text = ''.join(c for c in text if ord(c) >= 32 and ord(c) < 127)
            return text.strip()

        def wrap_text_for_pdf(text, max_line_length=60):
            """Wrap text into lines short enough for PDF rendering."""
            if not text or len(text) <= max_line_length:
                return text

            words = text.split()
            lines = []
            current_line = ""

            for word in words:
                # If word itself is too long, break it
                if len(word) > max_line_length:
                    if current_line:
                        lines.append(current_line)
                        current_line = ""
                    # Break long word into chunks
                    for i in range(0, len(word), max_line_length):
                        lines.append(word[i:i+max_line_length])
                elif len(current_line + " " + word) <= max_line_length:
                    current_line += (" " + word) if current_line else word
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word

            if current_line:
                lines.append(current_line)

            return "\n".join(lines)

        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.set_margins(20, 20, 20)  # Wider margins
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        # Use explicit page width minus margins for safe rendering
        page_width = 210 - 40  # A4 width minus margins in mm

        pdf.cell(page_width, 10, "My Personal Cookbook", ln=1, align='C')
        pdf.ln(10)

        for recipe in st.session_state.recipes:
            # Title
            pdf.set_font("Arial", 'B', 14)
            title = clean_text(recipe.get('title', 'Untitled'))
            pdf.cell(page_width, 10, title, ln=1)

            # Ingredients
            pdf.set_font("Arial", '', 12)
            pdf.cell(page_width, 10, "Ingredients:", ln=1)
            for ing in recipe.get('ingredients', []):
                ing = clean_text(ing)
                # Use explicit width for safety
                pdf.cell(page_width, 8, f"- {ing}", ln=1)

            # Steps
            pdf.cell(page_width, 10, "Steps:", ln=1)
            for i, step in enumerate(recipe.get('steps', []), 1):
                step = clean_text(step)
                wrapped_step = wrap_text_for_pdf(step, max_line_length=50)  # Even shorter

                # Split into smaller chunks and render each with explicit width
                step_lines = wrapped_step.split('\n')
                for j, line in enumerate(step_lines):
                    if line.strip():
                        prefix = f"{i}. " if j == 0 else "    "
                        safe_line = f"{prefix}{line}"
                        # Use cell instead of multi_cell for guaranteed safety
                        pdf.cell(page_width, 8, safe_line, ln=1)
            pdf.ln(10)

        # Generate PDF
        pdf_bytes = bytes(pdf.output(dest='S'))  # Convert bytearray to bytes
        st.download_button("Download Cookbook PDF", pdf_bytes, "my_cookbook.pdf", "application/pdf")
        st.success("PDF ready!")

st.caption("v0.1 - Free via Groq API (rate limits apply). For testing only.")
st.info(f"Total tokens used in session: {st.session_state.token_usage}")
