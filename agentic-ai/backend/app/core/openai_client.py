# openai_client.py
from openai import AsyncOpenAI
from app.core.settings import settings
from dotenv import load_dotenv
import os

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Async client (matches your `await ...` usage)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

DEFAULT_MODEL = settings.OPENAI_MODEL
REQUEST_TIMEOUT = settings.OPENAI_REQUEST_TIMEOUT
