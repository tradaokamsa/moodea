FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AUTO_BOOTSTRAP_SYNTHETIC=true \
    ARTIFACT_DIR=/app/data/artifacts \
    EVENT_DIR=/app/data/events

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir torch==2.2.2 \
    --extra-index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY 278k_labelled_uri.csv ./278k_labelled_uri.csv
COPY src ./src

RUN mkdir -p /app/data/artifacts /app/data/events

EXPOSE 8001

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
