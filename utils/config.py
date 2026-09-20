"""
FasalMitra — configuration

API keys are read from environment variables first, so you can set
them in your shell or a .env file without touching this file:

    export GROQ_API_KEY="gsk_..."
    export ANTHROPIC_API_KEY="sk-ant-..."

If you prefer to hardcode a key directly (e.g. for a local demo),
paste it into the fallback string below. The env var always wins.
Get a free Groq key at https://console.groq.com/keys
"""

import os

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
