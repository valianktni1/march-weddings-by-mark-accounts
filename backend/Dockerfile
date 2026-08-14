FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create upload directories
RUN mkdir -p uploads/invoices uploads/expenses uploads/bank_statements temp_backup temp_restore

RUN useradd --system --uid 10001 --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=3)" || exit 1

# Run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
