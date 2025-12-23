"""LLM Provider module - centralizes LLM provider logic for ADW system.

This module provides:
- Provider detection and selection based on .env configuration
- OpenAI API execution function for prompt completion
- Provider-agnostic prompt execution interface
"""

import os
import json
from typing import Literal, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Type for active provider
LLMProvider = Literal["anthropic", "openai"]


def is_anthropic_enabled() -> bool:
    """Check if Anthropic provider is enabled in environment."""
    return os.getenv("ANTHROPIC_ENABLED", "true").lower() == "true"


def is_openai_enabled() -> bool:
    """Check if OpenAI provider is enabled in environment."""
    return os.getenv("OPENAI_ENABLED", "false").lower() == "true"


def get_anthropic_api_key() -> Optional[str]:
    """Get Anthropic API key from environment."""
    return os.getenv("ANTHROPIC_API_KEY")


def get_openai_api_key() -> Optional[str]:
    """Get OpenAI API key from environment."""
    return os.getenv("OPENAI_API_KEY")


def get_active_provider() -> Optional[LLMProvider]:
    """Determine the active LLM provider based on environment configuration.

    Priority: Anthropic (if enabled and configured) > OpenAI (if enabled and configured)

    Returns:
        "anthropic" or "openai" if a provider is properly configured, None otherwise.
    """
    # Check Anthropic first (higher priority)
    if is_anthropic_enabled() and get_anthropic_api_key():
        return "anthropic"

    # Check OpenAI as fallback
    if is_openai_enabled() and get_openai_api_key():
        return "openai"

    return None


def get_openai_model_for_claude_model(claude_model: str) -> str:
    """Map Claude model names to equivalent OpenAI model names.

    Args:
        claude_model: Claude model name (e.g., "sonnet", "opus", or full model ID)

    Returns:
        Corresponding OpenAI model name
    """
    model_mapping = {
        # Abstract names
        "sonnet": "gpt-4o",
        "opus": "gpt-4o",
        "haiku": "gpt-4o-mini",
        # Full Claude model IDs
        "claude-3-5-sonnet-20241022": "gpt-4o",
        "claude-3-5-haiku-20241022": "gpt-4o-mini",
        "claude-3-opus-20240229": "gpt-4o",
        "claude-sonnet-4-20250514": "gpt-4o",
        "claude-opus-4-5-20251101": "gpt-4o",
    }

    return model_mapping.get(claude_model, "gpt-4o")


def prompt_openai(
    prompt: str,
    model: str = "gpt-4o",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """Execute a prompt using OpenAI API.

    Args:
        prompt: The prompt to send to OpenAI
        model: OpenAI model to use (default: gpt-4o)
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature

    Returns:
        Dict containing:
            - success: bool indicating if the request succeeded
            - output: The response text or error message
            - usage: Token usage information (if successful)
    """
    import urllib.request
    import urllib.error

    openai_key = get_openai_api_key()

    if not openai_key:
        return {
            "success": False,
            "output": "OPENAI_API_KEY not set",
            "usage": None,
        }

    try:
        # Prepare the request
        data = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))

            # Extract the response text
            choices = result.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content", "")

                return {
                    "success": True,
                    "output": content,
                    "usage": result.get("usage"),
                }
            else:
                return {
                    "success": False,
                    "output": "No response from OpenAI API",
                    "usage": None,
                }

    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass

        if e.code == 401:
            return {
                "success": False,
                "output": "OpenAI API key is invalid (401 Unauthorized)",
                "usage": None,
            }
        return {
            "success": False,
            "output": f"OpenAI API error: {e.code} {e.reason} - {error_body}",
            "usage": None,
        }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "output": f"OpenAI API connection failed: {str(e.reason)}",
            "usage": None,
        }
    except Exception as e:
        return {
            "success": False,
            "output": f"OpenAI API error: {str(e)}",
            "usage": None,
        }


def check_provider_configured() -> tuple[bool, str]:
    """Check if at least one LLM provider is properly configured.

    Returns:
        Tuple of (is_configured, error_message)
    """
    active = get_active_provider()

    if active:
        return True, f"Active provider: {active}"

    # Build helpful error message
    errors = []

    if is_anthropic_enabled():
        if not get_anthropic_api_key():
            errors.append("ANTHROPIC_ENABLED=true but ANTHROPIC_API_KEY is not set")

    if is_openai_enabled():
        if not get_openai_api_key():
            errors.append("OPENAI_ENABLED=true but OPENAI_API_KEY is not set")

    if not is_anthropic_enabled() and not is_openai_enabled():
        errors.append("No LLM provider enabled. Set ANTHROPIC_ENABLED=true or OPENAI_ENABLED=true")

    return False, "; ".join(errors) if errors else "No LLM provider configured"
