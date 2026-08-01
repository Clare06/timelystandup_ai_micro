# TimelyStandup AI Microservice

This standalone microservice provides AI processing capabilities for the TimelyStandup platform. It exposes HTTP endpoints for analyzing standup videos, clarifying text questions, and summarizing developer responses.

## Prerequisites

- Python 3.12+
- FFmpeg (for video processing)
- Docker (optional)

## Configuration

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

Ensure `GEMINI_API_KEY` is set.

## Running Standalone Locally

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Start the service:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
   ```

## Running with Docker

Build the image and run the container:
```bash
docker build -t timelystandup-ai .
docker run -p 8001:8001 --env-file .env timelystandup-ai
```

## Running with Docker Compose

This service is typically run alongside `timelystandup-core` and the infrastructure services via a docker-compose setup. The AI service will be configured as a standard dependency.

## API Documentation

When the service is running, interactive API documentation is available at `http://localhost:8001/docs`.

### Example Request

```bash
curl -X POST http://localhost:8001/ai/text/clarify \
  -H "Content-Type: application/json" \
  -d '{"raw_questions": "What did you do today?"}'
```
