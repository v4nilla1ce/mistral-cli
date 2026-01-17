import os
import requests
from dotenv import load_dotenv

load_dotenv()

class MistralAPI:
    def __init__(self):
        self.api_key = os.getenv("MISTRAL_API_KEY")
        self.base_url = "https://api.mistral.ai/v1/chat/completions"

    def chat(self, messages, model="mistral-tiny", stream=False, **kwargs):
        """
        Send a chat request to Mistral API.
        
        Args:
            messages (str or list): The user prompt (str) or list of message dicts.
            model (str): The model to use.
            stream (bool): Whether to stream the response.
            **kwargs: Additional parameters (temperature, top_p, etc.)
            
        Returns:
            str or generator: The response content or a generator yielding chunks.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Backward compatibility: if messages is a string, wrap it
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
            
        data = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        data.update(kwargs)
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data, stream=stream)
            
            if response.status_code != 200:
                error_msg = f"API request failed with status {response.status_code}: {response.text}"
                return error_msg if not stream else [error_msg] # safe fallback

            if stream:
                return self._stream_response(response)
            else:
                response_json = response.json()
                return response_json["choices"][0]["message"]["content"]
                
        except Exception as e:
            return f"Error: {e}" if not stream else [f"Error: {e}"]

    def _stream_response(self, response):
        import json
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith("data: "):
                    line = line[6:]  # Remove "data: " prefix
                    if line == "[DONE]":
                        break
                    try:
                        json_data = json.loads(line)
                        delta = json_data["choices"][0]["delta"]
                        if "content" in delta:
                            yield delta["content"]
                    except:
                        pass
