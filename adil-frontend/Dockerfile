# Project Adil - Frontend Container
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy application
COPY . .

# Set Chainlit host
ENV CHAINLIT_HOST=0.0.0.0

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]

