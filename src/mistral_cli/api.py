"""HTTP client for the Mistral AI API."""

import json
from dataclasses import dataclass, field
from typing import Any, Generator, Optional, Union

import requests

from .config import get_api_key


@dataclass
class ToolCall:
    """Represents a tool call from the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    """Structured response from the chat API."""

    content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    raw: Optional[dict] = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if the response contains tool calls."""
        return len(self.tool_calls) > 0


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
        messages: Union[str, list[dict[str, Any]]],
        model: str = "mistral-tiny",
        stream: bool = False,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        return_full_response: bool = False,
        **kwargs: Any,
    ) -> Union[str, ChatResponse, Generator[str, None, None], list[str]]:
        """Send a chat request to Mistral API.

        Args:
            messages: The user prompt (str) or list of message dicts.
            model: The model to use.
            stream: Whether to stream the response.
            tools: Optional list of tool definitions for function calling.
            tool_choice: Optional tool choice strategy ('auto', 'none', or specific tool).
            return_full_response: If True, return ChatResponse object instead of string.
            **kwargs: Additional parameters (temperature, top_p, etc.)

        Returns:
            - If return_full_response=True: ChatResponse object with content and tool_calls.
            - If stream=True: Generator yielding content chunks.
            - Otherwise: The response content as a string.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Backward compatibility: if messages is a string, wrap it
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        data: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        # Add tools if provided
        if tools:
            data["tools"] = tools
            if tool_choice:
                data["tool_choice"] = tool_choice

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
                if return_full_response:
                    return ChatResponse(content=error_msg)
                return error_msg if not stream else [error_msg]

            if stream:
                return self._stream_response(response)
            else:
                response_json = response.json()
                return self._parse_response(response_json, return_full_response)

        except Exception as e:
            error_msg = f"Error: {e}"
            if return_full_response:
                return ChatResponse(content=error_msg)
            return error_msg if not stream else [f"Error: {e}"]

    def _parse_response(
        self, response_json: dict, return_full_response: bool
    ) -> Union[str, ChatResponse]:
        """Parse the API response into appropriate format.

        Args:
            response_json: The raw JSON response.
            return_full_response: Whether to return full ChatResponse.

        Returns:
            String content or ChatResponse object.
        """
        message = response_json["choices"][0]["message"]
        finish_reason = response_json["choices"][0].get("finish_reason")
        content = message.get("content")

        if not return_full_response:
            return content or ""

        # Parse tool calls if present
        tool_calls = []
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {}

                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=args,
                    )
                )

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw=response_json,
        )

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
