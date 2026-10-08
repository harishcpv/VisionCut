Markdown

\# 🎥 VisionCut AI Studio



VisionCut AI is a robust, local, multi-lingual video automation platform built with Python, Streamlit, FFmpeg, and multi-modal AI agents. It transforms raw mobile footage into viral, hook-optimized short- or long-form videos complete with AI voiceovers, dynamic visual text hooks, subscribe call-to-actions, and precise full-length timeline preservation.



\---



\## 🚀 Key Features



\* \*\*Local Master Architecture:\*\* Processes multi-minute and long-form video files locally using hardware-accelerated `imageio-ffmpeg` without truncation.

\* \*\*Autonomous Script \& Hook Generation:\*\* Integrates with Gemini and OpenRouter to analyze raw footage and generate tailored titles, descriptions, viral hooks, and end-screen CTAs.

\* \*\*Multi-Lingual Voiceover \& Subtitles:\*\* Powered by `edge-tts` for natural-sounding multi-lingual voice synthesis across English, Telugu, and Hindi.

\* \*\*Dynamic Engagement Engine:\*\* Automatically burns top-screen viral hooks (first 3 seconds) and bottom-screen subscribe CTAs (last 3 seconds) directly onto video streams using custom font rendering.

\* \*\*Streamlit Web Dashboard:\*\* Clean, interactive UI for effortless file uploading, target language selection, and one-click rendering and downloading.



\---



\## 🛠️ Tech Stack



\* \*\*Frontend / UI:\*\* Streamlit

\* \*\*AI \& LLMs:\*\* Google GenAI SDK (`gemini-3.8-flash`), OpenRouter API (`OpenAI` SDK)

\* \*\*Video/Audio Processing:\*\* FFmpeg \& `ffmpeg-python`, `imageio-ffmpeg`

\* \*\*Text-to-Speech:\*\* `edge-tts`

\* \*\*Data Validation:\*\* Pydantic (`schema.py`)



\---



\## ⚙️ Installation \& Setup



1\. \*\*Clone the Repository:\*\*

&#x20;  ```bash

&#x20;  git clone \[https://github.com/YOUR\_USERNAME/VisionCut.git](https://github.com/YOUR\_USERNAME/VisionCut.git)

&#x20;  cd VisionCut

Install Dependencies:



Bash

pip install streamlit ffmpeg-python imageio-ffmpeg edge-tts google-genai openai python-dotenv pydantic

Configure Environment Variables:

Create a .env file in the root directory and add your API keys:



Code snippet

GEMINI\_API\_KEY=your\_gemini\_api\_key\_here

OPENROUTER\_API\_KEY=your\_openrouter\_api\_key\_here

Run the Application:



Bash

python -m streamlit run app.py

Built with passion for automated content creation.





\---



\### Step 3: Initialize Git and Push to GitHub

Open your terminal inside your project folder (`C:\\Users\\Haris\\OneDrive\\Desktop\\VisionCut`) and run these commands:



```bash

\# 1. Initialize git repository

git init



\# 2. Add all project files (ignoring items in .gitignore)

git add .



\# 3. Commit your files with a clean message

git commit -m "Initial commit: VisionCut AI multi-lingual video automation studio"



\# 4. (Optional) Connect to your GitHub repository

\# Create a new empty repository on GitHub named "VisionCut", then run:

git branch -M main

git remote add origin https://github.com/YOUR\_GITHUB\_USERNAME/VisionCut.git

git push -u origin main

(Just remember to replace YOUR\_GITHUB\_USERNAME with your actual GitHub username before running the final push command!)

