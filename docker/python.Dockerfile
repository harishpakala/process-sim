FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY examples ./examples
COPY semantic ./semantic
COPY scripts ./scripts
COPY frontend/public ./frontend/public
COPY tests/fixtures ./tests/fixtures
COPY reports ./reports
CMD ["python", "-m", "process_sim.api.server"]
