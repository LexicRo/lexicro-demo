FROM python:3.13.13-slim-trixie

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user: this container proxies to a paid, keyed API and
# shares a host with the production API's Postgres. A container-breakout or
# arbitrary-write bug is strictly worse with root inside the container than
# without it, and there is no reason this process needs root at all.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin demo \
    && chown -R demo:demo /app
USER demo

EXPOSE 8002

CMD ["uvicorn", "app.main:create_default_app", "--factory", "--host", "0.0.0.0", "--port", "8002"]
