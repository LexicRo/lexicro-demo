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

## Learn More

See the [LexicRo API guide](https://api.lexicro.com/guide) for detailed information about the API.
