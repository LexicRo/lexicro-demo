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

> ## nginx MUST set `X-Real-IP`, or the per-IP throttle is forgeable
>
> The nginx vhost in front of this demo **must** contain:
> ```nginx
> proxy_set_header X-Real-IP $remote_addr;
> ```
>
> The app only trusts an inbound `X-Real-IP` header when the immediate TCP
> peer is loopback or private. Behind Docker on this host, that peer is
> *always* nginx — so that check is always satisfied, and the app has no
> way to tell from inside the container whether nginx is actually
> overwriting the header or just forwarding whatever the visitor sent.
> Correctness of the per-IP throttle depends entirely on this one nginx
> line existing.
>
> **Without it, any visitor can set their own `X-Real-IP` and bypass the
> per-IP throttle entirely**, leaving only the loose, whole-site
> `global_day` cap between one script and the demo key's daily budget.

To redeploy after a change, run `./deploy.sh` again on the host.

After the first build, confirm the image carries no secret:
```bash
docker run --rm --entrypoint sh lexicro-demo-demo -c 'ls -a /app' | grep -c "^\.env$"
```
Expected: `0`.

## Learn More

See the [LexicRo API guide](https://api.lexicro.com/guide) for detailed information about the API.
