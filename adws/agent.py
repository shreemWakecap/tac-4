"""Claude Code agent module for executing prompts programmatically.

Supports multiple LLM providers:
- Anthropic (via Claude Code CLI) - default when ANTHROPIC_ENABLED=true
- OpenAI (via API) - used when OPENAI_ENABLED=true and Anthropic is disabled
"""

import subprocess
import sys
import os
import json
import re
from typing import Optional, List, Dict, Any, Tuple
from dotenv import load_dotenv
from data_types import (
    AgentPromptRequest,
    AgentPromptResponse,
    AgentTemplateRequest,
    ClaudeCodeResultMessage,
)
from llm_provider import (
    get_active_provider,
    is_anthropic_enabled,
    prompt_openai,
    get_openai_model_for_claude_model,
)

# Load environment variables
load_dotenv()

# Get Claude Code CLI path from environment
CLAUDE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")


def check_claude_installed() -> Optional[str]:
    """Check if Claude Code CLI is installed. Return error message if not.

    Only performs the check if Anthropic is enabled. If Anthropic is disabled,
    returns None (no error) since Claude CLI is not required.
    """
    # Skip check if Anthropic is disabled
    if not is_anthropic_enabled():
        return None

    try:
        result = subprocess.run(
            [CLAUDE_PATH, "--version"], capture_output=True, text=True
        )
        if result.returncode != 0:
            return f"Error: Claude Code CLI is not installed. Expected at: {CLAUDE_PATH}"
    except FileNotFoundError:
        return f"Error: Claude Code CLI is not installed. Expected at: {CLAUDE_PATH}"
    return None


def parse_jsonl_output(output_file: str) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Parse JSONL output file and return all messages and the result message.
    
    Returns:
        Tuple of (all_messages, result_message) where result_message is None if not found
    """
    try:
        with open(output_file, "r") as f:
            # Read all lines and parse each as JSON
            messages = [json.loads(line) for line in f if line.strip()]
            
            # Find the result message (should be the last one)
            result_message = None
            for message in reversed(messages):
                if message.get("type") == "result":
                    result_message = message
                    break
                    
            return messages, result_message
    except Exception as e:
        print(f"Error parsing JSONL file: {e}", file=sys.stderr)
        return [], None


def convert_jsonl_to_json(jsonl_file: str) -> str:
    """Convert JSONL file to JSON array file.
    
    Creates a .json file with the same name as the .jsonl file,
    containing all messages as a JSON array.
    
    Returns:
        Path to the created JSON file
    """
    # Create JSON filename by replacing .jsonl with .json
    json_file = jsonl_file.replace('.jsonl', '.json')
    
    # Parse the JSONL file
    messages, _ = parse_jsonl_output(jsonl_file)
    
    # Write as JSON array
    with open(json_file, 'w') as f:
        json.dump(messages, f, indent=2)
    
    print(f"Created JSON file: {json_file}")
    return json_file


def get_claude_env() -> Dict[str, str]:
    """Get environment variables for Claude Code execution.

    Returns a dictionary containing the parent environment merged with
    required environment variables from .env configuration.

    This ensures Windows-specific variables (APPDATA, LOCALAPPDATA, TEMP, etc.)
    are preserved while also including our custom configuration.

    Note: Claude Code CLI requires ANTHROPIC_API_KEY. OpenAI vars are passed through
    for hooks and other operations that may use OpenAI as an alternative provider.
    """
    # Start with the full parent environment to preserve Windows system vars
    env = os.environ.copy()

    # Override/add our configuration variables
    config_vars = {
        # Anthropic Configuration (required for Claude Code CLI)
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),

        # OpenAI Configuration (for hooks and other LLM operations)
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),

        # LLM Provider Enable Flags
        "ANTHROPIC_ENABLED": os.getenv("ANTHROPIC_ENABLED", "true"),
        "OPENAI_ENABLED": os.getenv("OPENAI_ENABLED", "false"),

        # Claude Code Configuration
        "CLAUDE_CODE_PATH": os.getenv("CLAUDE_CODE_PATH", "claude"),
        "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": os.getenv("CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR", "true"),

        # Agent Cloud Sandbox Environment (optional)
        "E2B_API_KEY": os.getenv("E2B_API_KEY"),
    }

    # Only add GitHub tokens if GITHUB_PAT exists
    github_pat = os.getenv("GITHUB_PAT")
    if github_pat:
        config_vars["GITHUB_PAT"] = github_pat
        config_vars["GH_TOKEN"] = github_pat  # Claude Code uses GH_TOKEN

    # Merge config vars into env (only non-None values)
    for k, v in config_vars.items():
        if v is not None:
            env[k] = v

    return env


def save_prompt(prompt: str, adw_id: str, agent_name: str = "ops") -> None:
    """Save a prompt to the appropriate logging directory."""
    # Extract slash command from prompt
    match = re.match(r'^(/\w+)', prompt)
    if not match:
        return
    
    slash_command = match.group(1)
    # Remove leading slash for filename
    command_name = slash_command[1:]
    
    # Create directory structure at project root (parent of adws)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_dir = os.path.join(project_root, "agents", adw_id, agent_name, "prompts")
    os.makedirs(prompt_dir, exist_ok=True)
    
    # Save prompt to file
    prompt_file = os.path.join(prompt_dir, f"{command_name}.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"Saved prompt to: {prompt_file}")


def execute_prompt_openai(request: AgentPromptRequest) -> AgentPromptResponse:
    """Execute a prompt using OpenAI API.

    This is used as an alternative to Claude Code CLI when OpenAI is the active provider.

    Note: OpenAI cannot execute slash commands or file operations that Claude Code CLI can.
    This function is primarily for LLM prompt execution only.
    """
    # Save prompt before execution
    save_prompt(request.prompt, request.adw_id, request.agent_name)

    # Create output directory if needed
    output_dir = os.path.dirname(request.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Map Claude model to OpenAI model
    openai_model = get_openai_model_for_claude_model(request.model)

    print(f"Executing prompt via OpenAI (model: {openai_model})")

    # Execute via OpenAI
    result = prompt_openai(
        prompt=request.prompt,
        model=openai_model,
        max_tokens=4096,
        temperature=0.7,
    )

    # Save output to file for consistency with Claude Code output
    output_data = {
        "type": "result",
        "subtype": "success" if result["success"] else "error",
        "is_error": not result["success"],
        "result": result["output"],
        "session_id": None,
        "provider": "openai",
        "model": openai_model,
        "usage": result.get("usage"),
    }

    with open(request.output_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(output_data, ensure_ascii=False) + "\n")

    print(f"Output saved to: {request.output_file}")

    # Also create JSON file for consistency
    json_file = request.output_file.replace('.jsonl', '.json')
    with open(json_file, 'w', encoding="utf-8") as f:
        json.dump([output_data], f, indent=2, ensure_ascii=False)
    print(f"Created JSON file: {json_file}")

    return AgentPromptResponse(
        output=result["output"],
        success=result["success"],
        session_id=None,
    )


def prompt_claude_code(request: AgentPromptRequest) -> AgentPromptResponse:
    """Execute Claude Code with the given prompt configuration.

    Routes to the appropriate provider based on configuration:
    - If provider is explicitly set, uses that provider
    - Otherwise, uses the active provider from environment config
    """
    # Determine which provider to use
    provider = request.provider
    if provider == "anthropic":
        # Double check if Anthropic is actually available
        active = get_active_provider()
        if active == "openai":
            # Anthropic was requested but only OpenAI is available
            print("Warning: Anthropic requested but not available, falling back to OpenAI")
            return execute_prompt_openai(request)

    elif provider == "openai":
        return execute_prompt_openai(request)

    # Default: use Anthropic (Claude Code CLI)
    # Check if Claude Code CLI is installed
    error_msg = check_claude_installed()
    if error_msg:
        # If Claude Code CLI is not available but OpenAI is, fall back to OpenAI
        if get_active_provider() == "openai":
            print("Warning: Claude Code CLI not available, falling back to OpenAI")
            return execute_prompt_openai(request)
        return AgentPromptResponse(output=error_msg, success=False, session_id=None)

    # Save prompt before execution
    save_prompt(request.prompt, request.adw_id, request.agent_name)

    # Create output directory if needed
    output_dir = os.path.dirname(request.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Build command - always use stream-json format and verbose
    cmd = [CLAUDE_PATH, "-p", request.prompt]
    cmd.extend(["--model", request.model])
    cmd.extend(["--output-format", "stream-json"])
    cmd.append("--verbose")

    # Add dangerous skip permissions flag if enabled
    if request.dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    # Set up environment with only required variables
    env = get_claude_env()

    try:
        # Execute Claude Code and pipe output to file
        with open(request.output_file, "w") as f:
            result = subprocess.run(
                cmd, stdout=f, stderr=subprocess.PIPE, text=True, env=env
            )

        if result.returncode == 0:
            print(f"Output saved to: {request.output_file}")
            
            # Parse the JSONL file
            messages, result_message = parse_jsonl_output(request.output_file)
            
            # Convert JSONL to JSON array file
            json_file = convert_jsonl_to_json(request.output_file)
            
            if result_message:
                # Extract session_id from result message
                session_id = result_message.get("session_id")
                
                # Check if there was an error in the result
                is_error = result_message.get("is_error", False)
                result_text = result_message.get("result", "")
                
                return AgentPromptResponse(
                    output=result_text, 
                    success=not is_error,
                    session_id=session_id
                )
            else:
                # No result message found, return raw output
                with open(request.output_file, "r") as f:
                    raw_output = f.read()
                return AgentPromptResponse(
                    output=raw_output, 
                    success=True,
                    session_id=None
                )
        else:
            error_msg = f"Claude Code error: {result.stderr}"
            print(error_msg, file=sys.stderr)
            return AgentPromptResponse(output=error_msg, success=False, session_id=None)

    except subprocess.TimeoutExpired:
        error_msg = "Error: Claude Code command timed out after 5 minutes"
        print(error_msg, file=sys.stderr)
        return AgentPromptResponse(output=error_msg, success=False, session_id=None)
    except Exception as e:
        error_msg = f"Error executing Claude Code: {e}"
        print(error_msg, file=sys.stderr)
        return AgentPromptResponse(output=error_msg, success=False, session_id=None)


def execute_template(request: AgentTemplateRequest) -> AgentPromptResponse:
    """Execute a Claude Code template with slash command and arguments.

    Note: Slash commands are a Claude Code CLI feature. When using OpenAI provider,
    the slash command and args are passed as a regular prompt. OpenAI won't be able
    to execute the actual CLI commands but can process the text.
    """
    # Construct prompt from slash command and args
    prompt = f"{request.slash_command} {' '.join(request.args)}"

    # Determine provider - use template's provider or detect from environment
    provider = request.provider
    if provider == "anthropic":
        active = get_active_provider()
        if active == "openai":
            provider = "openai"

    # Create output directory with adw_id at project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(project_root, "agents", request.adw_id, request.agent_name)
    os.makedirs(output_dir, exist_ok=True)

    # Build output file path
    output_file = os.path.join(output_dir, "raw_output.jsonl")

    # Create prompt request with specific parameters
    prompt_request = AgentPromptRequest(
        prompt=prompt,
        adw_id=request.adw_id,
        agent_name=request.agent_name,
        model=request.model,
        provider=provider,
        dangerously_skip_permissions=True,
        output_file=output_file,
    )

    # Execute and return response (prompt_claude_code now handles all parsing)
    return prompt_claude_code(prompt_request)
