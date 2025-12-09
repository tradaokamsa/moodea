FROM apache/flink:1.18-scala_2.12-java11

WORKDIR /opt/flink

# Install Python dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Set Flink job classpath
ENV PYFLINK_CLIENT_EXECUTABLE=python3

# Run Flink job
# CMD ["flink", "run", "-py", "src/main.py"]

