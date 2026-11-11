FROM node:20-bookworm-slim
WORKDIR /app
COPY backend/package*.json ./backend/
RUN npm install --omit=dev
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY . .
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHON_EXECUTABLE="/opt/venv/bin/python"
ENV PYTHONUNBUFFERED="1"
EXPOSE 3001
CMD ["node", "backend/server.js"]
