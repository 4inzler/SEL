# LocalAI Setup Guide

This guide explains how to run SEL with LocalAI instead of OpenRouter, allowing you to self-host completely free without any API costs.

## What is LocalAI?

[LocalAI](https://localai.io/) is a free, open-source alternative to OpenAI that:
- ✅ Runs 100% locally on your own hardware
- ✅ No API costs or usage limits
- ✅ OpenAI-compatible API (drop-in replacement)
- ✅ Supports multiple open-source models (Llama, Mistral, etc.)
- ✅ Includes vision models (LLaVA for image understanding)

## Requirements

### Hardware
- **Minimum**: 8GB RAM, 4+ CPU cores
- **Recommended**: 16GB+ RAM, GPU with 8GB+ VRAM
- **Optimal**: 32GB+ RAM, GPU with 16GB+ VRAM

### Software
- Docker and Docker Compose (easiest method)
- OR: LocalAI binary for your platform

## Quick Start with Docker

### 1. Install LocalAI

Create a `docker-compose-localai.yml` file:

```yaml
version: '3.8'

services:
  localai:
    image: quay.io/go-skynet/local-ai:latest
    ports:
      - "8080:8080"
    environment:
      - THREADS=4
      - CONTEXT_SIZE=4096
    volumes:
      - ./localai-models:/models
      - ./localai-data:/data
    restart: unless-stopped
```

Start LocalAI:
```bash
docker-compose -f docker-compose-localai.yml up -d
```

### 2. Download Models

LocalAI will auto-download models on first use, or you can pre-download:

```bash
# Main conversation model (7B parameter model, ~4GB)
curl -L https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf \
  -o ./localai-models/mistral-7b-instruct.gguf

# Utility model (smaller, faster, ~800MB)
curl -L https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf \
  -o ./localai-models/llama-2-7b-chat.gguf

# Vision model for image understanding (~4GB)
curl -L https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/ggml-model-q4_k.gguf \
  -o ./localai-models/llava-7b.gguf
```

### 3. Create Model Configuration Files

Create `./localai-models/mistral-7b.yaml`:
```yaml
name: mistral-7b
parameters:
  model: mistral-7b-instruct.gguf
  temperature: 0.8
  top_p: 0.9
  top_k: 40
context_size: 4096
threads: 4
```

Create `./localai-models/llama-7b.yaml`:
```yaml
name: llama-7b
parameters:
  model: llama-2-7b-chat.gguf
  temperature: 0.3
  top_p: 0.9
  top_k: 40
context_size: 2048
threads: 4
```

Create `./localai-models/llava.yaml`:
```yaml
name: llava
parameters:
  model: llava-7b.gguf
  mmproj: llava-mmproj.gguf
context_size: 2048
threads: 4
```

## Configure SEL for LocalAI

Update your `.env` file:

```env
# Switch to LocalAI provider
LLM_PROVIDER=localai

# LocalAI Configuration
LOCALAI_BASE_URL=http://localhost:8080
LOCALAI_MAIN_MODEL=mistral-7b
LOCALAI_UTIL_MODEL=llama-7b
LOCALAI_VISION_MODEL=llava
LOCALAI_MAIN_TEMP=0.8
LOCALAI_UTIL_TEMP=0.3

# Keep other settings the same
DISCORD_BOT_TOKEN=your_token_here
# ... etc
```

## Start SEL

```bash
# Start LocalAI
docker-compose -f docker-compose-localai.yml up -d

# Wait for models to load (check logs)
docker logs localai -f

# Start SEL
cd project_echo
poetry run python -m sel_bot.main
```

You should see:
```
============================================================
LLM Provider: LocalAI (self-hosted)
  Base URL: http://localhost:8080
  Main Model: mistral-7b
  Util Model: llama-7b
  Vision Model: llava
============================================================
```

## Recommended Models

### For Limited Hardware (8-16GB RAM)
- **Main**: `phi-2` (2.7B params, ~2GB) - Fast and capable
- **Util**: `tinyllama` (1.1B params, ~600MB) - Very fast
- **Vision**: Skip or use cloud fallback

### For Medium Hardware (16-32GB RAM)
- **Main**: `mistral-7b-instruct` (7B params, ~4GB) - Recommended
- **Util**: `llama-2-7b-chat` (7B params, ~4GB)
- **Vision**: `llava-7b` (7B params, ~4GB)

### For High-End Hardware (32GB+ RAM, GPU)
- **Main**: `llama-3-70b` (70B params, ~40GB) - Very capable
- **Util**: `mistral-7b-instruct` (7B params, ~4GB)
- **Vision**: `llava-13b` (13B params, ~7GB)

## Performance Tips

### 1. Use GPU Acceleration
Add to `docker-compose-localai.yml`:
```yaml
services:
  localai:
    # ... other config
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### 2. Adjust Context Size
Smaller context = faster responses:
```env
CONTEXT_SIZE=2048  # Instead of 4096
```

### 3. Use Quantized Models
- Q4_K_M: Good balance (recommended)
- Q5_K_M: Better quality, slower
- Q8_0: Best quality, slowest

### 4. Pre-warm Models
Load models on startup to avoid first-message delay:
```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral-7b","messages":[{"role":"user","content":"hello"}]}'
```

## Troubleshooting

### LocalAI not responding
```bash
# Check if running
docker ps | grep localai

# Check logs
docker logs localai

# Restart
docker restart localai
```

### Out of memory errors
- Use smaller models (phi-2, tinyllama)
- Reduce context_size in model YAML
- Lower threads count
- Close other applications

### Slow responses
- Use quantized models (Q4_K_M)
- Enable GPU acceleration
- Reduce context window
- Use smaller models for utility tasks

### SEL can't connect
```bash
# Test LocalAI directly
curl http://localhost:8080/v1/models

# Check firewall
# Make sure port 8080 is accessible
```

## Switching Back to OpenRouter

Simply change your `.env`:
```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
```

## Cost Comparison

### OpenRouter (Cloud)
- ~$0.50-$2.00 per day for active bot
- No hardware requirements
- Fast and reliable
- Access to latest models

### LocalAI (Self-Hosted)
- $0 API costs forever
- One-time hardware investment
- Full control and privacy
- Requires technical setup

## Additional Resources

- [LocalAI Documentation](https://localai.io/docs/)
- [Model Downloads (Hugging Face)](https://huggingface.co/models?library=gguf)
- [GGUF Model Guide](https://github.com/ggerganov/llama.cpp/blob/master/examples/quantize/README.md)
- [LocalAI Discord](https://discord.gg/localai)

## Example: Minimal Setup

For testing or low-resource systems:

```env
# .env
LLM_PROVIDER=localai
LOCALAI_BASE_URL=http://localhost:8080
LOCALAI_MAIN_MODEL=phi-2
LOCALAI_UTIL_MODEL=tinyllama
LOCALAI_VISION_MODEL=bakllava
```

Download models:
```bash
# Phi-2 (2.7B, ~2GB)
curl -L https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf \
  -o ./localai-models/phi-2.gguf

# TinyLlama (1.1B, ~600MB)
curl -L https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
  -o ./localai-models/tinyllama.gguf
```

This setup needs only ~4GB RAM and will work on most systems!
