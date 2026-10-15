FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY web ./web
RUN useradd -m -u 10001 warehouse && chown -R warehouse:warehouse /app
USER warehouse
EXPOSE 8000
CMD ["uvicorn","server.app:app","--host","0.0.0.0","--port","8000","--workers","1","--no-proxy-headers"]
