# FacadeGPT Backend

## API keys

Do not paste secrets into Python files.

Create `backend/.env` from `backend/.env.example`:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_key_here
DEEPSEEK_MODEL=deepseek-v4-pro
IMAGE_PROVIDER=dashscope
DASHSCOPE_API_KEY=your_dashscope_key_here
DASHSCOPE_IMAGE_MODEL=wanx2.1-t2i-turbo
```

This project can also auto-read local key files:

- `keys/ds.txt` -> DeepSeek API key
- `keys/*.csv` row named `apiKey` -> DashScope / 通义万相 API key

Restart the backend after changing environment variables.

## Knowledge base

Put PDF textbooks in `books/`, then run:

```powershell
cd backend
python scripts/ingest_books.py
```

You can also rebuild from the API:

```http
POST /api/knowledge/rebuild
{"use_api_embeddings": true}
```

If `OPENAI_API_KEY` is also configured, chunks can be embedded with the configured embedding model. DeepSeek is used for language generation, but this project keeps knowledge retrieval keyword-based unless an embedding provider is available.

Useful endpoints:

- `GET /api/knowledge/status`
- `GET /api/knowledge/search?q=facade shading daylight`
