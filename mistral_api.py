import os
import requests
from dotenv import load_dotenv

load_dotenv()

class MistralAPI:
    def __init__(self):
        self.api_key = os.getenv("MISTRAL_API_KEY")
        self.base_url = "https://api.mistral.ai/v1/chat/completions"

    def chat(self, prompt, model="mistral-large"):
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        response = requests.post(self.base_url, headers=headers, json=data)
        return response.json()["choices"][0]["message"]["content"]
