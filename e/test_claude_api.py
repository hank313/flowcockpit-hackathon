import os
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

client = Anthropic()

message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=300,
    messages=[
        {"role": "user", "content": "有兩個候選地點:A(室內,距離500公尺),B(室外有遮蔽,距離200公尺)。請用一句話幫我比較取捨。"}
    ]
)

print(message.content[0].text)
