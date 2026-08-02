# TimelyStandup AI Microservice

This microservice provides specialized processing capabilities for the TimelyStandup platform. It handles media extraction and leverages Large Language Models to generate actionable summaries from developer standup data.

## 🏗 Architecture

Designed as an independent, stateless FastAPI application. It is meant to be called by the `timelystandup-core` worker or other workflow engines over HTTP. 
By isolating these heavyweight AI and FFmpeg tasks, the Core API remains responsive.
- **Media Processing:** Uses FFmpeg to extract audio from video files.
- **AI Integration:** Interfaces with the Gemini AI APIs (and easily extensible to other providers) to transcribe and summarize text and media.

## 🛠 Tech Stack
- **Framework:** FastAPI
- **LLM SDK:** Google GenAI (Gemini)
- **Media Tools:** FFmpeg
- **HTTP Client:** HTTPX

## 🚀 Setup Instructions

1. **System Requirements:**
   You must have `ffmpeg` installed on your host system if running outside of Docker.
2. **Environment Configuration:**
   Copy `.env.example` to `.env` and fill in the required values (importantly `GEMINI_API_KEY`).
   ```bash
   cp .env.example .env
   ```
3. **Local Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Start the Service:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
   ```
5. **Interactive Docs:**
   Access the Swagger UI at `http://localhost:8001/docs` to test endpoints like `/ai/text/clarify`.
