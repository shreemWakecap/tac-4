#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "anthropic",
#     "openai",
#     "python-dotenv",
# ]
# ///

"""
Unified LLM Provider Module

This module provides a unified interface for LLM operations that automatically
selects the appropriate provider (Anthropic or OpenAI) based on configuration.

Priority Logic:
1. If ANTHROPIC_ENABLED=true (or not set) AND ANTHROPIC_API_KEY exists -> use Anthropic
2. If OPENAI_ENABLED=true AND OPENAI_API_KEY exists -> use OpenAI
3. If neither is configured -> return None
"""

import os
import sys
from typing import Optional
from dotenv import load_dotenv


def get_enabled_provider() -> Optional[str]:
    """
    Determine which LLM provider to use based on environment configuration.

    Priority Logic:
    1. If ANTHROPIC_ENABLED=true (or not set for backward compatibility) AND ANTHROPIC_API_KEY exists -> "anthropic"
    2. If OPENAI_ENABLED=true AND OPENAI_API_KEY exists -> "openai"
    3. Otherwise -> None

    Returns:
        str: "anthropic", "openai", or None if no provider is configured
    """
    load_dotenv()

    # Check Anthropic - default to true for backward compatibility
    anthropic_enabled = os.getenv("ANTHROPIC_ENABLED", "true").lower() == "true"
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if anthropic_enabled and anthropic_key:
        return "anthropic"

    # Check OpenAI - default to false
    openai_enabled = os.getenv("OPENAI_ENABLED", "false").lower() == "true"
    openai_key = os.getenv("OPENAI_API_KEY")

    if openai_enabled and openai_key:
        return "openai"

    return None


def _import_anth():
    """Import anthropic module, handling both package and standalone contexts."""
    try:
        from . import anth
        return anth
    except ImportError:
        # Running as standalone script
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location("anth", Path(__file__).parent / "anth.py")
        anth = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(anth)
        return anth


def _import_oai():
    """Import openai module, handling both package and standalone contexts."""
    try:
        from . import oai
        return oai
    except ImportError:
        # Running as standalone script
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location("oai", Path(__file__).parent / "oai.py")
        oai = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oai)
        return oai


def prompt_llm(prompt_text: str) -> Optional[str]:
    """
    Unified LLM prompting method that uses the configured provider.

    Args:
        prompt_text (str): The prompt to send to the model

    Returns:
        str: The model's response text, or None if error or no provider configured
    """
    provider = get_enabled_provider()

    if provider == "anthropic":
        anth = _import_anth()
        return anth.prompt_llm(prompt_text)
    elif provider == "openai":
        oai = _import_oai()
        return oai.prompt_llm(prompt_text)
    else:
        return None


def generate_completion_message() -> Optional[str]:
    """
    Generate a completion message using the configured LLM provider.

    Returns:
        str: A natural language completion message, or None if error
    """
    provider = get_enabled_provider()

    if provider == "anthropic":
        anth = _import_anth()
        return anth.generate_completion_message()
    elif provider == "openai":
        oai = _import_oai()
        return oai.generate_completion_message()
    else:
        return None


def main():
    """Command line interface for testing."""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--test":
            # Test provider detection
            provider = get_enabled_provider()
            print(f"Detected provider: {provider or 'None (no provider configured)'}")

            if provider:
                # Test a simple prompt
                response = prompt_llm("Say 'Hello' and nothing else.")
                if response:
                    print(f"Test response: {response}")
                    print("Provider test: PASSED")
                else:
                    print("Provider test: FAILED - no response")
            else:
                print("Provider test: SKIPPED - no provider configured")
                print("\nTo configure a provider, set in your .env:")
                print("  For Anthropic: ANTHROPIC_ENABLED=true and ANTHROPIC_API_KEY=...")
                print("  For OpenAI: OPENAI_ENABLED=true and OPENAI_API_KEY=...")

        elif sys.argv[1] == "--completion":
            message = generate_completion_message()
            if message:
                print(message)
            else:
                print("Error generating completion message (no provider configured)")

        elif sys.argv[1] == "--provider":
            provider = get_enabled_provider()
            print(provider or "none")

        else:
            prompt_text = " ".join(sys.argv[1:])
            response = prompt_llm(prompt_text)
            if response:
                print(response)
            else:
                print("Error: No LLM provider configured or API call failed")
    else:
        print("Usage:")
        print("  ./provider.py --test          Test provider detection and connectivity")
        print("  ./provider.py --provider      Print active provider name")
        print("  ./provider.py --completion    Generate a completion message")
        print("  ./provider.py 'prompt'        Send a prompt to the LLM")


if __name__ == "__main__":
    main()
