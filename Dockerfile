FROM python:3.9-slim

WORKDIR /app

# Создаём директорию для базы данных
RUN mkdir -p /app/bot_data && chmod 777 /app/bot_data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
