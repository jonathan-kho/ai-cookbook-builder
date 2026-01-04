# AI Personal Cookbook Builder

A free Streamlit web app that uses AI to extract recipes from images and text, then generates beautiful, mobile-friendly HTML cookbooks.

## Features

- **📸 Image Processing**: Upload recipe photos or handwritten notes - AI extracts recipes automatically
- **📝 Text Input**: Paste recipe text for instant processing
- **📱 HTML Generation**: Download beautiful, responsive cookbooks that work perfectly on mobile
- **📊 Token Tracking**: Monitor API usage costs
- **🔒 Privacy**: All processing happens client-side, recipes stay private

## Tech Stack

- **Frontend**: Streamlit
- **AI**: Groq API (LLaVA for vision, Llama for text)
- **HTML Generation**: Pure HTML with responsive CSS
- **Image Processing**: PIL/Pillow

## Quick Start

### Deploy to Streamlit Community Cloud (Recommended)

1. **Fork or clone this repo** to your GitHub
2. **Go to [share.streamlit.io](https://share.streamlit.io)**
3. **Connect your GitHub** and select this repository
4. **Deploy** with `app.py` as the main file
5. **Add your API key** in app settings:
   ```
   GROQ_API_KEY = "your-api-key-here"
   ```

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up API key** in `config.py`:
   ```python
   GROQ_API_KEY = "your-groq-api-key"
   ```

3. **Run locally:**
   ```bash
   streamlit run app.py
   ```

## Cost Estimate

- **~1-3k tokens** per image extraction
- **~$0.001-0.003** per recipe
- **10-recipe cookbook: <$0.03**

## Getting a Groq API Key

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up for a free account
3. Create an API key
4. Add it to your deployment

## Usage

1. **Upload recipe photos** or **paste recipe text**
2. **AI extracts** title, ingredients, and steps automatically
3. **Generate & download** your HTML cookbook (works great on mobile!)
4. **Share** the recipes with family and friends!

## Privacy

- No recipes are stored on servers
- All processing uses temporary API calls
- Your cookbook data stays private
