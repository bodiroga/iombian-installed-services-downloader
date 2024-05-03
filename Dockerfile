FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update && apt-get install build-essential -y
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
COPY src ./
CMD ["python", "/app/main.py"]
