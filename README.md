# LexicRo Demo

A small FastAPI application that demonstrates the LexicRo Romanian NLP API. The demo holds an API key server-side and proxies one endpoint to the LexicRo API.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file by copying from `.env.example` and filling in your credentials:
   ```bash
   cp .env.example .env
   ```

## Running Tests

Run the test suite with:
```bash
pytest -v
```

## Deploying

The demo runs as its own Compose project, alongside the API's Compose project on
the same Hetzner host, behind the same nginx.

1. Clone this repo to `/opt/lexicro-demo` on the host.
2. Copy `.env.example` to `.env` and fill in real values for
   `LEXICRO_API_BASE`, `LEXICRO_DEMO_KEY`, and `SESSION_SECRET`. `.env` is
   gitignored and must never be committed.
3. Run `./deploy.sh`. It builds the image from the current checkout, then
   starts (or restarts) the container. Building before `up -d` matters: the
   Dockerfile bakes the repo into the image, so skipping the build would
   leave a stale container running after a `git pull`.
4. The container listens on `127.0.0.1:8002` only — nginx is expected to
   terminate TLS and proxy to it. It is never reachable directly from
   outside the host.

To redeploy after a change, run `./deploy.sh` again on the host.

## Learn More

See the [LexicRo API guide](https://api.lexicro.com/guide) for detailed information about the API.
