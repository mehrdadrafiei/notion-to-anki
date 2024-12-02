FROM python:3.12-slim

WORKDIR /app

# Copy requirements directory first to leverage Docker cache
COPY requirements/ requirements/

# Install base and API requirements
RUN pip install --no-cache-dir -r requirements/base.txt

# Copy the application code
COPY . .

# Create output directory for flashcards
RUN mkdir -p output

ENV PORT=8000

# Command to run the application
CMD ["uvicorn", "src.api.main:app", "-ws", "wsproto", "--host", "0.0.0.0", "--port", "8000"]  

CMD uvicorn src.api.main:app --reload --ws wsproto --host 0.0.0.0 --port $PORT