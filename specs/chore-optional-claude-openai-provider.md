# Chore: Make Claude Optional with OpenAI Alternative Across All ADW Scripts

## Chore Description
Currently, `health_check.py` has been updated to make Claude Code (Anthropic) optional based on `.env` configuration, with OpenAI as an alternative LLM provider. This chore extends that pattern to all other `adws/*.py` files, ensuring the entire ADW system can operate with either Claude Code (when ANTHROPIC_ENABLED=true) or OpenAI (when OPENAI_ENABLED=true) as the LLM backend.

The key changes implemented in `health_check.py` that need to be replicated:
1. Read `ANTHROPIC_ENABLED` and `OPENAI_ENABLED` flags from environment
2. Only require/check the API key for the enabled provider
3. Skip Claude Code CLI checks when Anthropic is disabled
4. Provide OpenAI as a functional alternative when enabled

## Relevant Files
Use these files to resolve the chore:

- **`adws/health_check.py`** - Reference implementation showing the pattern to follow. Contains `check_env_vars()` with provider flags, conditional `check_claude_code()` and `check_openai()` calls.

- **`adws/agent.py`** - Core agent execution module. Currently hardcoded to use Claude Code CLI. Needs to be updated to:
  - Check provider flags before executing Claude
  - Add OpenAI alternative execution path
  - Update `check_claude_installed()` to be conditional
  - Update `prompt_claude_code()` to optionally use OpenAI

- **`adws/adw_plan_build.py`** - Main ADW workflow script. Currently:
  - `check_env_vars()` requires `ANTHROPIC_API_KEY` unconditionally
  - Calls `execute_template()` which always uses Claude
  - Needs provider-aware environment checks
  - Needs to route to correct LLM provider

- **`adws/trigger_cron.py`** - Cron trigger that calls `adw_plan_build.py`. No direct LLM usage but should be reviewed for any hardcoded Claude assumptions.

- **`adws/trigger_webhook.py`** - Webhook trigger that calls `adw_plan_build.py`. No direct LLM usage but should be reviewed.

- **`adws/data_types.py`** - Data types for agent requests/responses. May need:
  - New field for `provider` in `AgentPromptRequest`
  - Update `model` field to support OpenAI model names

- **`adws/github.py`** - GitHub operations module. No LLM usage - no changes needed.

- **`adws/utils.py`** - Utility functions. No LLM usage - no changes needed.

### New Files
- **`adws/llm_provider.py`** - New module to centralize LLM provider logic, including:
  - Provider detection and selection
  - OpenAI API execution function
  - Provider-agnostic prompt execution interface

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### Step 1: Create the LLM Provider Module
Create a new `adws/llm_provider.py` module that centralizes all LLM provider logic:
- Add `get_active_provider()` function that reads env flags and returns "anthropic" or "openai"
- Add `is_anthropic_enabled()` and `is_openai_enabled()` helper functions
- Add `prompt_openai()` function that executes prompts via OpenAI API (similar to the pattern in health_check.py but for actual prompt execution)
- Add `get_openai_model_for_claude_model()` mapping function (e.g., "sonnet" -> "gpt-4o", "opus" -> "gpt-4o")

### Step 2: Update Data Types
Update `adws/data_types.py`:
- Add `provider: Literal["anthropic", "openai"] = "anthropic"` field to `AgentPromptRequest`
- Expand `model` field to include OpenAI model names or keep abstract names that get mapped

### Step 3: Update Agent Module
Update `adws/agent.py`:
- Import new `llm_provider` module
- Update `check_claude_installed()` to only run when Anthropic is enabled
- Add new `prompt_openai()` function that uses OpenAI API for prompt execution
- Update `prompt_claude_code()` to check provider and route to OpenAI if needed
- Update `execute_template()` to use the provider-aware execution

### Step 4: Update ADW Plan Build Script
Update `adws/adw_plan_build.py`:
- Update `check_env_vars()` to use provider-aware validation (only require the enabled provider's key)
- Import and use provider detection from `llm_provider.py`
- Ensure all agent calls respect the active provider

### Step 5: Review Trigger Scripts
Review and update if needed:
- `adws/trigger_cron.py` - Verify no hardcoded Claude assumptions
- `adws/trigger_webhook.py` - Verify no hardcoded Claude assumptions

### Step 6: Update Environment Configuration
- Verify `.env.sample` has proper documentation for provider flags
- Ensure `.env` on the system has correct provider configuration

### Step 7: Run Validation Commands
Execute every command to validate the chore is complete with zero regressions.

## Validation Commands
Execute every command to validate the chore is complete with zero regressions.

- `uv run adws/health_check.py` - Run health check to validate environment configuration and provider detection
- `uv run adws/health_check.py 2` - Run health check with issue number to test GitHub integration
- `python -c "from adws.llm_provider import get_active_provider; print(get_active_provider())"` - Verify provider detection works
- `python -c "from adws.agent import check_claude_installed; print(check_claude_installed())"` - Verify Claude check is conditional

## Notes

- The current `.env` has `ANTHROPIC_ENABLED=false` and `OPENAI_ENABLED=true`, so the system should be able to operate with OpenAI only after this chore is complete.
- Claude Code CLI will still be needed for certain operations (like running slash commands), so the OpenAI alternative is primarily for the LLM prompt execution parts.
- If Claude Code CLI is required for core functionality (slash commands), consider documenting which features require Claude Code specifically vs which can use OpenAI.
- The OpenAI prompt execution should return responses in a format compatible with the existing `AgentPromptResponse` data type.
- Model mapping suggestion:
  - `sonnet` -> `gpt-4o` (fast, capable)
  - `opus` -> `gpt-4o` (same, or could use `gpt-4-turbo` for longer context)
- Be mindful of response format differences between Claude Code JSONL output and OpenAI API responses - the agent module will need to normalize these.
