from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
from mistral_common.protocol.instruct.messages import UserMessage
from mistral_common.protocol.instruct.request import ChatCompletionRequest
import logging

# Initialize tokenizer globally
_tokenizer = None

def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        try:
            _tokenizer = MistralTokenizer.v3()
        except Exception as e:
            logging.error(f"Failed to load tokenizer: {e}")
    return _tokenizer

def count_tokens(prompt, model="mistral-small"):
    """
    Count tokens for a single UserMessage prompt.
    Returns 0 on failure.
    """
    tokenizer = get_tokenizer()
    if not tokenizer:
        return 0
        
    try:
        # We simulate the request structure Mistral API expects
        request = ChatCompletionRequest(
            messages=[UserMessage(content=prompt)],
            model=model
        )
        encoded = tokenizer.encode_chat_completion(request)
        return len(encoded.tokens)
    except Exception as e:
        logging.error(f"Token counting error: {e}")
        return 0
