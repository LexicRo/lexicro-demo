#!/bin/bash
set -euo pipefail

cd /opt/lexicro-demo
git pull

# Build BEFORE up. The Dockerfile COPYs the repo into the image and nothing
# bind-mounts source over it, so without this the running container is
# whatever the last build produced -- not what git pull just fetched.
# lexicro/deploy.sh carries the full account of what that cost.
docker compose build
docker compose up -d

echo "Deployed successfully"
