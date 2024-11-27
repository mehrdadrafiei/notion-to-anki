# AI Notion2Anki

A FastAPI-based web application that automatically generates flashcards from Notion pages with optional AI-powered summarization using chatbots like Groq and Mistral AI.

* Demo: https://acute-ptarmigan-mehrdadr94-575a939c.koyeb.app

## Features

- **Notion Integration**: Extract content directly from Notion pages
- **AI Summarization**: Optional AI-powered summarization using Groq or Mistral
- **Real-time Progress**: WebSocket-based real-time progress tracking
- **Rate Limiting**: Built-in rate limiting to prevent API abuse
- **Task History**: Keep track of all flashcard generation tasks
- **Error Handling**: Comprehensive error handling and reporting
- **CSV Export**: Export flashcards in CSV format compatible with popular flashcard apps

## Prerequisites

- Python 3.12+
- Redis (for development)
- Redis Cluster (for production)
- Notion API Key
- Groq API Key (optional)
- Mistral API Key (optional)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd notion2anki
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

Required environment variables:
```
NOTION_API_KEY=your_notion_api_key
GROQ_API_KEY=your_groq_api_key
MISTRAL_API_KEY=your_mistral_api_key
REDIS_HOST=localhost
REDIS_PORT=6379
```

## Development

1. Start Redis:
```bash
docker-compose up -d redis
```

2. Run the development server:
```bash
python -m uvicorn src.api.main:app --reload --port 8000
```

## Testing

Run tests using pytest:
```bash
make test  # Run tests
make test-cov  # Run tests with coverage
make test-html  # Generate coverage HTML report
```

## API Endpoints

### Flashcard Generation
- `POST /generate-flashcards/`: Start flashcard generation
- `GET /task-status/{task_id}`: Get generation task status
- `GET /generation-history`: Get history of generation tasks
- `GET /preview-flashcards/{task_id}`: Preview generated flashcards
- `GET /download/{task_id}`: Download flashcards as CSV

### WebSocket
- `WS /ws/{task_id}`: Real-time task progress updates

### Health Check
- `GET /health`: System health status

## Production Deployment

1. Set up Redis Cluster:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

2. Configure environment variables for production.

3. Run with production server:
```bash
gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Error Handling

The application implements a comprehensive error handling system:
- Domain-specific exceptions for better error context
- Proper error logging and reporting
- Rate limiting error handling
- WebSocket error management

## Development Tools

- `pre-commit`: Code formatting and linting hooks
- `black`: Code formatting
- `isort`: Import sorting
- `pytest`: Testing framework

## Makefile Commands

- `make test`: Run tests
- `make test-cov`: Run tests with coverage report
- `make test-html`: Generate HTML coverage report
- `make clean`: Clean temporary files

## Contributing

1. Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

2. Install pre-commit hooks:
```bash
pre-commit install
```

3. Follow the existing code style and add tests for new features.

## License

## Acknowledgments

- FastAPI for the web framework
- Notion API for content extraction
- Groq and Mistral for AI summarization
