"""HTTP client for the Mistral AI API."""

import json
from typing import Any, Generator, Optional, Union

import requests

from .config import get_api_key


class MistralAPI:
    """Client for interacting with the Mistral AI chat completions API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the API client.

        Args:
            api_key: Optional API key. If not provided, will be loaded from
                     config using the standard precedence.
        """
        self.api_key = get_api_key(api_key)
        self.base_url = "https://api.mistral.ai/v1/chat/completions"

    def chat(
        self,
        messages: Union[str, list[dict[str, str]]],
        model: str = "mistral-tiny",
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[str, Generator[str, None, None], list[str]]:
        """Send a chat request to Mistral API.

        Args:
            messages: The user prompt (str) or list of message dicts.
            model: The model to use.
            stream: Whether to stream the response.
            **kwargs: Additional parameters (temperature, top_p, etc.)

        Returns:
            The response content (str), a generator yielding chunks (if streaming),
            or a list with an error message on failure.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
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
            response = requests.post(
                self.base_url, headers=headers, json=data, stream=stream
            )

            if response.status_code != 200:
                error_msg = (
                    f"API request failed with status {response.status_code}: "
                    f"{response.text}"
                )
                return error_msg if not stream else [error_msg]

            if stream:
                return self._stream_response(response)
            else:
                response_json = response.json()
                return response_json["choices"][0]["message"]["content"]

        except Exception as e:
            return f"Error: {e}" if not stream else [f"Error: {e}"]

    def _stream_response(
        self, response: requests.Response
    ) -> Generator[str, None, None]:
        """Parse SSE stream from Mistral API.

        Args:
            response: The streaming response object.

        Yields:
            Content chunks as they arrive.
        """
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]  # Remove "data: " prefix
                    if line == "[DONE]":
                        break
                    try:
                        json_data = json.loads(line)
                        delta = json_data["choices"][0]["delta"]
                        if "content" in delta:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError):
                        pass
