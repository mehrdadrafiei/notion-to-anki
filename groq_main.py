import os

from groq import Groq


API_KEY = "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"
client = Groq(api_key=API_KEY)

chat_completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "Explain the importance of fast language models",
        }
    ],
    model="llama3-8b-8192",
)

print(chat_completion.choices[0].message.content)