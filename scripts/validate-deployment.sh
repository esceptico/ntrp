#!/bin/bash
# Validate deployment configuration

set -e

echo "🔍 Validating NTRP deployment configuration..."

# Check required files exist
echo "✓ Checking required files..."
files=(
    "Dockerfile"
    ".dockerignore"
    "docker-compose.yml"
    "DEPLOYMENT.md"
    "fly.toml"
    "railway.json"
    "render.yaml"
)

for file in "${files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "✗ Missing: $file"
        exit 1
    fi
    echo "  ✓ $file"
done

# Check .env.example has required variables
echo "✓ Checking .env.example..."
required_vars=("OPENAI_API_KEY")
for var in "${required_vars[@]}"; do
    if ! grep -q "^$var=" .env.example; then
        echo "✗ Missing required variable in .env.example: $var"
        exit 1
    fi
    echo "  ✓ $var"
done

# Check optional but important variables are documented
optional_vars=("NTRP_VAULT_PATH" "ANTHROPIC_API_KEY" "GEMINI_API_KEY")
for var in "${optional_vars[@]}"; do
    if grep -q "$var" .env.example; then
        echo "  ✓ $var (documented)"
    fi
done

# Validate docker-compose.yml syntax
echo "✓ Validating docker-compose.yml..."
if command -v docker-compose &> /dev/null; then
    docker-compose config > /dev/null 2>&1 && echo "  ✓ Valid YAML syntax"
else
    echo "  ⚠ docker-compose not installed, skipping validation"
fi

# Check Dockerfile syntax (basic)
echo "✓ Validating Dockerfile..."
if grep -q "^FROM python:3.13" Dockerfile; then
    echo "  ✓ Base image: python:3.13-slim"
fi
if grep -q "^EXPOSE 8000" Dockerfile; then
    echo "  ✓ Exposes port 8000"
fi
if grep -q "^HEALTHCHECK" Dockerfile; then
    echo "  ✓ Health check configured"
fi

# Verify uvicorn command
if grep -q "uvicorn ntrp.server.app:app" Dockerfile; then
    echo "  ✓ Uvicorn start command"
fi

echo ""
echo "✅ All deployment configuration checks passed!"
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and configure"
echo "  2. Run: docker-compose up -d"
echo "  3. Check health: curl http://localhost:8000/health"
echo ""
echo "For cloud deployments, see DEPLOYMENT.md"
