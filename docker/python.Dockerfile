FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from tep import ControlMode, TEPSimulator; print('TEP package import OK')"
COPY src ./src
COPY examples ./examples
COPY semantic ./semantic
COPY scripts ./scripts
COPY frontend/public ./frontend/public
COPY tests/fixtures ./tests/fixtures
COPY reports ./reports
CMD ["python", "-m", "process_sim.api.server"]
