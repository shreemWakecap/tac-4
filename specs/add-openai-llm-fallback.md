# Chore: Add OpenAI LLM Fallback with Provider Priority Configuration

## Chore Description
Add support for OpenAI as an alternative LLM provider throughout the ADW system, with configurable priority settings. Currently, the system depends on the Anthropic API which requires a paid balance. This change will:

1. Add `OPENAI_API_KEY`, `OPENAI_ENABLED`, and `ANTHROPIC_ENABLED` environment variables
2. Implement provider priority logic (Anthropic highest priority when enabled)
3. Update health checks to validate LLM configuration based on enabled providers
4. Create a unified LLM provider module for hooks
5. Ensure fallback behavior when the primary provider is unavailable

**Priority Logic:**
- If both providers are enabled and have API keys: Use Anthropic (highest priority)
- If only OpenAI is enabled and has API key: Use OpenAI
- If only Anthropic is enabled and has API key: Use Anthropic
- If neither is configured: Fail with clear error message

**Important Limitation:**
The `adws/agent.py` module uses Claude Code CLI which inherently requires Anthropic API. This cannot be replaced with OpenAI. The OpenAI fallback applies only to:
- Health check LLM validation (separate from Claude Code CLI test)
- Hooks LLM utilities (`generate_completion_message`, etc.)
- Server LLM processor for SQL generation

## Relevant Files
Use these files to resolve the chore:

- **`.env.sample`** - Root environment sample file. Needs `OPENAI_API_KEY` and provider enable flags added. Currently only has Anthropic-related vars.
- **`app/server/.env.sample`** - Server environment sample. Already has both API keys, may need enable flags added.
- **`adws/health_check.py`** - Health check script. Currently requires `ANTHROPIC_API_KEY`. Needs to support conditional validation based on enabled providers. Key function: `check_env_vars()` at line 62.
- **`adws/agent.py`** - Agent module. Uses `ANTHROPIC_API_KEY` in `get_claude_env()` at line 84. Needs to pass through OpenAI vars for other operations but Claude Code CLI still requires Anthropic.
- **`.claude/hooks/utils/llm/anth.py`** - Anthropic LLM utility for hooks. Has `prompt_llm()` and `generate_completion_message()` functions.
- **`.claude/hooks/utils/llm/oai.py`** - OpenAI LLM utility for hooks. Already implemented with same interface as `anth.py`.
- **`app/server/core/llm_processor.py`** - Server LLM processor. Already has both providers. The `generate_sql()` function at line 139 currently prioritizes OpenAI. Needs to respect enable flags.

### New Files
- **`.claude/hooks/utils/llm/provider.py`** - New unified LLM provider module that handles provider selection and fallback logic for hooks.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### Step 1: Update Root `.env.sample` with OpenAI and Provider Flags
- Add `OPENAI_API_KEY` variable with placeholder value
- Add `ANTHROPIC_ENABLED=true` flag (default enabled for backward compatibility)
- Add `OPENAI_ENABLED=false` flag (default disabled)
- Add comments explaining the priority logic
- Keep existing `ANTHROPIC_API_KEY` variable

Example addition:
```
# LLM Provider Configuration
# Priority: Anthropic (if enabled) > OpenAI (if enabled)
ANTHROPIC_ENABLED=true
OPENAI_ENABLED=false
OPENAI_API_KEY=your-openai-api-key-here
```

### Step 2: Update Server `.env.sample` with Provider Flags
- Add `ANTHROPIC_ENABLED=true` flag
- Add `OPENAI_ENABLED=true` flag (server already supports both)
- Add comment explaining that server can use either provider

### Step 3: Create Unified LLM Provider Module for Hooks
- Create `.claude/hooks/utils/llm/provider.py`
- Implement `get_enabled_provider()` function that returns the active provider based on:
  - Check if `ANTHROPIC_ENABLED` is `true` (or not set, for backward compatibility) AND `ANTHROPIC_API_KEY` exists -> return `"anthropic"`
  - Check if `OPENAI_ENABLED` is `true` AND `OPENAI_API_KEY` exists -> return `"openai"`
  - Return `None` if neither is configured
- Implement `prompt_llm(prompt_text)` function that:
  - Determines active provider using `get_enabled_provider()`
  - Calls appropriate provider module (`anth.prompt_llm` or `oai.prompt_llm`)
  - Returns response or None
- Implement `generate_completion_message()` function that uses the unified `prompt_llm`
- Add CLI test support with `--test` flag

### Step 4: Update Health Check Environment Validation
- Modify `check_env_vars()` in `adws/health_check.py`
- Change validation logic:
  - Read `ANTHROPIC_ENABLED` env var (default `true` for backward compatibility)
  - Read `OPENAI_ENABLED` env var (default `false`)
  - If `ANTHROPIC_ENABLED` is true, require `ANTHROPIC_API_KEY`
  - If `OPENAI_ENABLED` is true, require `OPENAI_API_KEY`
  - Validate that at least one provider is enabled and has a valid API key
- Update error messages to reflect the new provider configuration options
- Add provider enable flags to the details output
- Note: Keep Claude Code CLI check as-is since it specifically tests Anthropic (via Claude Code)

### Step 5: Update Agent Environment Setup
- Modify `get_claude_env()` in `adws/agent.py`
- Add `OPENAI_API_KEY` to the environment variables if set
- Add `OPENAI_ENABLED` and `ANTHROPIC_ENABLED` flags to environment
- Note: Claude Code CLI still requires Anthropic, but passing these through allows hooks and other operations to use OpenAI

### Step 6: Update Server LLM Processor Priority Logic
- Modify `generate_sql()` in `app/server/core/llm_processor.py`
- Update priority logic to check `ANTHROPIC_ENABLED` and `OPENAI_ENABLED` flags
- New priority order:
  1. If `ANTHROPIC_ENABLED=true` and `ANTHROPIC_API_KEY` exists -> use Anthropic
  2. If `OPENAI_ENABLED=true` and `OPENAI_API_KEY` exists -> use OpenAI
  3. Fall back to `request.llm_provider` preference
- Add clear error message if no provider is configured

### Step 7: Update Hooks to Use Unified Provider (Optional)
- Review hooks that currently import from `anth.py` directly
- Update imports to use the new `provider.py` module for automatic provider selection
- This enables hooks to work with either provider based on configuration

### Step 8: Run Validation Commands
- Run health check to verify provider detection works
- Run server tests to ensure LLM processor works with new flags
- Verify the unified provider module functions correctly

## Validation Commands
Execute every command to validate the chore is complete with zero regressions.

- `uv run adws/health_check.py` - Run health check to verify environment validation works with new provider flags. Should pass if at least one provider is configured.
- `cd app/server && uv run pytest` - Run server tests to validate LLM processor changes
- `uv run .claude/hooks/utils/llm/provider.py --test` - Test the new unified provider module

## Notes
- **Backward Compatibility**: If neither `ANTHROPIC_ENABLED` nor `OPENAI_ENABLED` is explicitly set, default to `ANTHROPIC_ENABLED=true` for backward compatibility with existing setups.
- **Claude Code Dependency**: The `adws/agent.py` uses Claude Code CLI which inherently requires Anthropic API. This cannot be replaced with OpenAI. However, the health check LLM validation and hook LLM operations can use OpenAI as fallback.
- **Server Already Supports Both**: The `app/server/core/llm_processor.py` already has implementations for both OpenAI and Anthropic. This chore adds the enable flags for explicit control and changes priority to respect Anthropic-first when both are enabled.
- **Hook LLM Usage**: The hooks in `.claude/hooks/` use LLM for generating completion messages. These can use either provider based on configuration via the new `provider.py` module.
- **Security Note**: The OpenAI API key provided by the user should be added to the actual `.env` file (not `.env.sample`). Never commit actual API keys to version control.
- **Testing Scenarios**: After implementation, test with:
  - Only `OPENAI_API_KEY` set and `OPENAI_ENABLED=true`, `ANTHROPIC_ENABLED=false`
  - Only `ANTHROPIC_API_KEY` set and `ANTHROPIC_ENABLED=true`
  - Both set with `ANTHROPIC_ENABLED=true` (should use Anthropic)
  - Both set with `ANTHROPIC_ENABLED=false`, `OPENAI_ENABLED=true` (should use OpenAI)
