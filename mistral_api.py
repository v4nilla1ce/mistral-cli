import os
import requests
from dotenv import load_dotenv

load_dotenv()

class MistralAPI:
    def __init__(self):
        self.api_key = os.getenv("MISTRAL_API_KEY")
        self.base_url = "https://api.mistral.ai/v1/chat/completions"

    def chat(self, prompt, model="mistral-tiny"):
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        response = requests.post(self.base_url, headers=headers, json=data)

        if response.status_code != 200:
            return f"API request failed with status {response.status_code}: {response.text}"

        try:
            response_json = response.json()
            return response_json["choices"][0]["message"]["content"]
        except KeyError as e:
            return f"Unexpected response format: {e}"
        except Exception as e:
            return f"Error parsing response: {e}"
