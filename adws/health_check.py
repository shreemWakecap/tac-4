#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "python-dotenv",
#     "pydantic",
# ]
# ///

"""
Health Check Script for ADW System

Usage:
uv run adws/health_check.py <issue_number>

This script performs comprehensive health checks:
1. Validates all required environment variables
2. Checks git repository configuration
3. Tests Claude Code CLI functionality
4. Returns structured results
"""

import os
import sys
import json
import subprocess
import tempfile
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import argparse

from dotenv import load_dotenv
from pydantic import BaseModel

# Import git repo functions from github module
from github import get_repo_url, extract_repo_path, make_issue_comment

# Load environment variables
load_dotenv()


class CheckResult(BaseModel):
    """Individual check result."""

    success: bool
    error: Optional[str] = None
    warning: Optional[str] = None
    details: Dict[str, Any] = {}


class HealthCheckResult(BaseModel):
    """Structure for health check results."""

    success: bool
    timestamp: str
    checks: Dict[str, CheckResult]
    warnings: List[str] = []
    errors: List[str] = []


def check_env_vars() -> CheckResult:
    """Check required environment variables including LLM provider configuration."""
    # Read provider enable flags (default Anthropic=true for backward compatibility)
    anthropic_enabled = os.getenv("ANTHROPIC_ENABLED", "true").lower() == "true"
    openai_enabled = os.getenv("OPENAI_ENABLED", "false").lower() == "true"

    # Check API keys
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    # Always required vars
    base_required_vars = {
        "CLAUDE_CODE_PATH": "Path to Claude Code CLI (defaults to 'claude')",
    }

    optional_vars = {
        "GITHUB_PAT": "(Optional) GitHub Personal Access Token - only needed if you want ADW to use a different GitHub account than 'gh auth login'",
        "E2B_API_KEY": "(Optional) E2B API Key for sandbox environments",
        "CLOUDFLARED_TUNNEL_TOKEN": "(Optional) Cloudflare tunnel token for webhook exposure",
    }

    missing_required = []
    missing_optional = []

    # Check base required vars
    for var, desc in base_required_vars.items():
        if not os.getenv(var):
            if var == "CLAUDE_CODE_PATH":
                # This has a default, so not critical
                continue
            missing_required.append(f"{var} ({desc})")

    # Check LLM provider configuration
    # Only require API keys for enabled providers
    if anthropic_enabled and not anthropic_key:
        missing_required.append("ANTHROPIC_API_KEY (Anthropic API Key - required when ANTHROPIC_ENABLED=true)")

    # Check provider-specific requirements
    if openai_enabled and not openai_key:
        missing_required.append("OPENAI_API_KEY (OpenAI API Key - required when OPENAI_ENABLED=true)")

    # Validate at least one provider is properly configured for LLM operations
    anthropic_configured = anthropic_enabled and anthropic_key
    openai_configured = openai_enabled and openai_key

    if not anthropic_configured and not openai_configured:
        missing_required.append("No LLM provider configured. Enable at least one provider with its API key.")

    # Check optional vars
    for var, desc in optional_vars.items():
        if not os.getenv(var):
            missing_optional.append(f"{var} ({desc})")

    # Combine all errors
    all_errors = missing_required
    success = len(all_errors) == 0

    # Determine active provider
    active_provider = None
    if anthropic_configured:
        active_provider = "anthropic"
    elif openai_configured:
        active_provider = "openai"

    return CheckResult(
        success=success,
        error="Missing required environment variables or LLM provider configuration" if not success else None,
        details={
            "missing_required": all_errors,
            "missing_optional": missing_optional,
            "claude_code_path": os.getenv("CLAUDE_CODE_PATH", "claude"),
            "anthropic_enabled": anthropic_enabled,
            "openai_enabled": openai_enabled,
            "anthropic_key_set": bool(anthropic_key),
            "openai_key_set": bool(openai_key),
            "active_llm_provider": active_provider,
        },
    )


def check_git_repo() -> CheckResult:
    """Check git repository configuration using github module."""
    try:
        # Get repo URL using the github module function
        repo_url = get_repo_url()
        repo_path = extract_repo_path(repo_url)

        # Check if still using disler's repo
        is_disler_repo = "disler" in repo_path.lower()

        return CheckResult(
            success=True,
            warning=(
                "Repository still points to 'disler'. Please update to your own GitHub repository."
                if is_disler_repo
                else None
            ),
            details={
                "repo_url": repo_url,
                "repo_path": repo_path,
                "is_disler_repo": is_disler_repo,
            },
        )
    except ValueError as e:
        return CheckResult(success=False, error=str(e))


def check_claude_code() -> CheckResult:
    """Test Claude Code CLI functionality."""
    claude_path = os.getenv("CLAUDE_CODE_PATH", "claude")

    # On Windows, use shell=True for better command resolution
    use_shell = sys.platform == "win32"

    # First check if Claude Code is installed
    try:
        result = subprocess.run(
            [claude_path, "--version"], capture_output=True, text=True, shell=use_shell
        )
        if result.returncode != 0:
            return CheckResult(
                success=False,
                error=f"Claude Code CLI not functional at '{claude_path}'",
            )
    except FileNotFoundError:
        return CheckResult(
            success=False,
            error=f"Claude Code CLI not found at '{claude_path}'. Please install or set CLAUDE_CODE_PATH correctly.",
        )

    # Test with a simple prompt
    test_prompt = "What is 2+2? Just respond with the number, nothing else."

    # Prepare environment
    env = os.environ.copy()
    if os.getenv("GITHUB_PAT"):
        env["GH_TOKEN"] = os.getenv("GITHUB_PAT")

    try:
        # Create temporary file for output
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as tmp:
            output_file = tmp.name

        # Run Claude Code
        cmd = [
            claude_path,
            "-p",
            test_prompt,
            "--model",
            "claude-3-5-haiku-20241022",
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]

        with open(output_file, "w") as f:
            result = subprocess.run(
                cmd, stdout=f, stderr=subprocess.PIPE, text=True, env=env, timeout=60, shell=use_shell
            )

        # Parse output to verify it worked - don't rely solely on exit code
        # Claude may return non-zero even on success in some environments
        claude_responded = False
        response_text = ""

        try:
            with open(output_file, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            msg = json.loads(line)
                            if msg.get("type") == "result":
                                claude_responded = True
                                response_text = msg.get("result", "")
                                break
                        except json.JSONDecodeError:
                            continue
        finally:
            # Clean up temp file
            if os.path.exists(output_file):
                os.unlink(output_file)

        if not claude_responded and result.returncode != 0:
            return CheckResult(
                success=False,
                error=f"Claude Code test failed (exit {result.returncode}): {result.stderr}"
            )

        return CheckResult(
            success=claude_responded,
            details={
                "test_passed": "4" in response_text,
                "response": response_text[:100] if response_text else "No response",
            },
        )

    except subprocess.TimeoutExpired:
        return CheckResult(
            success=False, error="Claude Code test timed out after 60 seconds"
        )
    except Exception as e:
        return CheckResult(success=False, error=f"Claude Code test error: {str(e)}")


def is_wsl() -> bool:
    """Check if running inside WSL."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except FileNotFoundError:
        return False


def get_gh_path() -> Optional[str]:
    """Find the GitHub CLI executable path."""
    # Try 'gh' directly first
    try:
        result = subprocess.run(["gh", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            return "gh"
    except FileNotFoundError:
        pass

    # On Windows, check common installation paths
    if sys.platform == "win32":
        common_paths = [
            r"C:\Program Files\GitHub CLI\gh.exe",
            r"C:\Program Files (x86)\GitHub CLI\gh.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path

    # If running in WSL, try Windows GitHub CLI via /mnt/c path
    if is_wsl():
        wsl_windows_paths = [
            "/mnt/c/Program Files/GitHub CLI/gh.exe",
            "/mnt/c/Program Files (x86)/GitHub CLI/gh.exe",
        ]
        for path in wsl_windows_paths:
            if os.path.exists(path):
                return path

    return None


def get_gh_env() -> dict:
    """Get environment for running gh CLI, handling WSL config path."""
    env = os.environ.copy()

    # If GITHUB_PAT is set, use it
    if os.getenv("GITHUB_PAT"):
        env["GH_TOKEN"] = os.getenv("GITHUB_PAT")

    # If running in WSL, point to Windows gh config
    if is_wsl():
        # Get Windows username from the mount path
        try:
            import pwd
            # Try to find Windows user from common paths
            for path in ["/mnt/c/Users"]:
                if os.path.exists(path):
                    users = [u for u in os.listdir(path) if u not in ["Public", "Default", "Default User", "All Users"]]
                    if users:
                        win_user = users[0]
                        gh_config = f"/mnt/c/Users/{win_user}/AppData/Roaming/GitHub CLI"
                        if os.path.exists(gh_config):
                            env["GH_CONFIG_DIR"] = gh_config
                        break
        except Exception:
            pass

    return env


def check_github_cli() -> CheckResult:
    """Check if GitHub CLI is installed and authenticated."""
    gh_path = get_gh_path()

    if not gh_path:
        install_hint = "brew install gh" if sys.platform != "win32" else "winget install --id GitHub.cli"
        return CheckResult(
            success=False,
            error=f"GitHub CLI (gh) is not installed. Install with: {install_hint}",
            details={"installed": False},
        )

    # Check authentication status
    env = get_gh_env()

    try:
        result = subprocess.run(
            [gh_path, "auth", "status"], capture_output=True, text=True, env=env
        )

        authenticated = result.returncode == 0

        return CheckResult(
            success=authenticated,
            error="GitHub CLI not authenticated. Run: gh auth login" if not authenticated else None,
            details={"installed": True, "authenticated": authenticated, "path": gh_path},
        )
    except Exception as e:
        return CheckResult(
            success=False,
            error=f"GitHub CLI error: {str(e)}",
            details={"installed": True, "path": gh_path},
        )


def check_openai() -> CheckResult:
    """Test OpenAI API connectivity."""
    openai_key = os.getenv("OPENAI_API_KEY")

    if not openai_key:
        return CheckResult(
            success=False,
            error="OPENAI_API_KEY not set",
        )

    try:
        import urllib.request
        import urllib.error

        # Test with a simple API call to list models
        req = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={
                "Authorization": f"Bearer {openai_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200:
                return CheckResult(
                    success=True,
                    details={"api_connected": True},
                )
            else:
                return CheckResult(
                    success=False,
                    error=f"OpenAI API returned status {response.status}",
                )

    except urllib.error.HTTPError as e:
        if e.code == 401:
            return CheckResult(
                success=False,
                error="OpenAI API key is invalid (401 Unauthorized)",
            )
        return CheckResult(
            success=False,
            error=f"OpenAI API error: {e.code} {e.reason}",
        )
    except urllib.error.URLError as e:
        return CheckResult(
            success=False,
            error=f"OpenAI API connection failed: {str(e.reason)}",
        )
    except Exception as e:
        return CheckResult(
            success=False,
            error=f"OpenAI API test error: {str(e)}",
        )


def run_health_check() -> HealthCheckResult:
    """Run all health checks and return results."""
    result = HealthCheckResult(
        success=True, timestamp=datetime.now().isoformat(), checks={}
    )

    # Check environment variables
    env_check = check_env_vars()
    result.checks["environment"] = env_check
    if not env_check.success:
        result.success = False
        if env_check.error:
            result.errors.append(env_check.error)
        # Add specific missing vars to errors
        missing_required = env_check.details.get("missing_required", [])
        result.errors.extend(
            [f"Missing required env var: {var}" for var in missing_required]
        )
    # Don't add warnings for optional env vars - they're optional!

    # Check git repository
    git_check = check_git_repo()
    result.checks["git_repository"] = git_check
    if not git_check.success:
        result.success = False
        if git_check.error:
            result.errors.append(git_check.error)
    elif git_check.warning:
        result.warnings.append(git_check.warning)

    # Check GitHub CLI - treat as warning, not failure (system can work without it for basic tasks)
    gh_check = check_github_cli()
    result.checks["github_cli"] = gh_check
    if not gh_check.success:
        # Don't fail overall health check, just warn
        if gh_check.error:
            result.warnings.append(gh_check.error)

    # Get provider enable flags
    anthropic_enabled = os.getenv("ANTHROPIC_ENABLED", "true").lower() == "true"
    openai_enabled = os.getenv("OPENAI_ENABLED", "false").lower() == "true"

    # Check Claude Code (Anthropic) - only if enabled
    if anthropic_enabled:
        claude_check = check_claude_code()
        result.checks["claude_code"] = claude_check
        if not claude_check.success:
            if claude_check.error:
                result.warnings.append(claude_check.error)
    else:
        result.checks["claude_code"] = CheckResult(
            success=True,
            details={"enabled": False, "reason": "ANTHROPIC_ENABLED=false - Claude Code check disabled"},
        )

    # Check OpenAI - only if enabled
    if openai_enabled:
        openai_check = check_openai()
        result.checks["openai"] = openai_check
        if not openai_check.success:
            result.success = False
            if openai_check.error:
                result.errors.append(openai_check.error)
    else:
        result.checks["openai"] = CheckResult(
            success=True,
            details={"enabled": False, "reason": "OPENAI_ENABLED=false - OpenAI check disabled"},
        )

    return result


def main():
    """Main entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="ADW System Health Check")
    parser.add_argument(
        "issue_number",
        nargs="?",
        help="Optional GitHub issue number to post results to",
    )
    args = parser.parse_args()

    print("[HEALTH] Running ADW System Health Check...\n")

    result = run_health_check()

    # Print summary
    print(
        f"{'[OK]' if result.success else '[FAIL]'} Overall Status: {'HEALTHY' if result.success else 'UNHEALTHY'}"
    )
    print(f"[TIME] Timestamp: {result.timestamp}\n")

    # Print detailed results
    print("[CHECKS] Check Results:")
    print("-" * 50)

    for check_name, check_result in result.checks.items():
        status = "[OK]" if check_result.success else "[FAIL]"
        print(f"\n{status} {check_name.replace('_', ' ').title()}:")

        # Print check-specific details
        for key, value in check_result.details.items():
            if value is not None and key not in [
                "missing_required",
                "missing_optional",
            ]:
                print(f"   {key}: {value}")

        if check_result.error:
            print(f"   [FAIL] Error: {check_result.error}")
        if check_result.warning:
            print(f"   [WARN] Warning: {check_result.warning}")

    # Print warnings
    if result.warnings:
        print("\n[WARN] Warnings:")
        for warning in result.warnings:
            print(f"   - {warning}")

    # Print errors
    if result.errors:
        print("\n[FAIL] Errors:")
        for error in result.errors:
            print(f"   - {error}")

    # Print next steps
    if not result.success:
        print("\n[NEXT] Next Steps:")
        if any("ANTHROPIC_API_KEY" in e for e in result.errors):
            print("   1. Set ANTHROPIC_API_KEY in your .env file")
        if any("GITHUB_PAT" in e for e in result.errors):
            print("   2. Set GITHUB_PAT in your .env file")
        if any("GitHub CLI" in e for e in result.errors):
            print("   3. Install GitHub CLI: brew install gh")
            print("   4. Authenticate: gh auth login")
        if any("disler" in w for w in result.warnings):
            print(
                "   5. Fork/clone the repository and update git remote to your own repo"
            )

    # If issue number provided, post comment
    if args.issue_number:
        # Check if gh is available before trying to post
        gh_available = result.checks.get("github_cli", CheckResult(success=False)).success
        if not gh_available:
            print(f"\n[SKIP] Cannot post to issue #{args.issue_number} - GitHub CLI not installed")
        else:
            print(f"\n[POST] Posting health check results to issue #{args.issue_number}...")
            status_emoji = "[OK]" if result.success else "[FAIL]"
            comment = f"{status_emoji} Health check completed: {'HEALTHY' if result.success else 'UNHEALTHY'}"
            try:
                make_issue_comment(args.issue_number, comment)
                print(f"[OK] Posted health check comment to issue #{args.issue_number}")
            except Exception as e:
                print(f"[FAIL] Failed to post comment: {e}")

    # Return appropriate exit code
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
