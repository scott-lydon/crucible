FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .
ENV PORT=8090
EXPOSE 8090
# Hosted demo: paste a system prompt -> Crucible attacks it -> HTML report.
# Set OPENROUTER_API_KEY to enable real-model targets (offline sample bot needs no key).
CMD ["python", "-m", "crucible.webapp_demo"]
