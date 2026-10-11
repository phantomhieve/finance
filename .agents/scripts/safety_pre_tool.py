#!/usr/bin/env python3
"""
Antigravity PreToolUse hook for Vault.
Prevents inspection, modification, or dumping of prohibited secret files and credentials.
"""
import json
import re
import sys

# Secret file/folder patterns (allowed if ending in .example)
SECRET_PATH_REGEX = re.compile(
    r'(^|[/\\])'
    r'('
    r'\.env(\.[^/\\]+)?(?<!\.example)'
    r'|scripts/DEPLOY\.env(?<!\.example)'
    r'|\.deploy-keys'
    r'|credentials([/\\]|$)'
    r'|\.credentials([/\\]|$)'
    r'|investor_profile\.md(?<!\.example)'
    r'|google-service-account\.json'
    r'|backup-sa\.json'
    r'|.*\.pem$'
    r'|.*\.key$'
    r'|.*\.p12$'
    r'|.*id_rsa$'
    r'|.*id_ed25519$'
    r')',
    re.IGNORECASE
)

# Shell commands attempting to read secrets or dump credentials
SECRET_CMD_PATTERNS = [
    # Any command mentioning a secret file (excluding .example)
    r'(^|\s|/|\'|")\.env(\.[a-zA-Z0-9_-]+)?(?!\.example)(\s|/|\'|"|$)',
    r'(^|\s|/|\'|")DEPLOY\.env(?!\.example)(\s|/|\'|"|$)',
    r'\.deploy-keys',
    r'credentials/[a-zA-Z0-9_.-]+',
    r'portfolio/investor_profile\.md(?!\.example)',
    r'google-service-account\.json',
    r'backup-sa\.json',
    r'\.(pem|key|p12)($|\s)',
    # Environment variable dumping
    r'\bprintenv\b',
    r'(^|\s)env(\s|$)',
    r'(^|\s)export\s+-p\b',
    r'\becho\s+\$([a-zA-Z0-9_]*SECRET|[a-zA-Z0-9_]*KEY|[a-zA-Z0-9_]*PASS|[a-zA-Z0-9_]*TOKEN)',
    # Python one-liners reading secrets or dumping env
    r'os\.environ',
    r'os\.getenv',
    r'dumpdata\s+tracker\.User',
    r'dumpdata\s+tracker\.WebAuthn',
    r'dumpdata\s+oauth2_provider',
]

SECRET_CMD_REGEX = re.compile('|'.join(f'({p})' for p in SECRET_CMD_PATTERNS), re.IGNORECASE)

def is_secret_path(path: str) -> bool:
    if not path:
        return False
    if path.endswith('.example') or '.example.' in path:
        return False
    return bool(SECRET_PATH_REGEX.search(path))

def is_secret_command(cmd: str) -> bool:
    if not cmd:
        return False
    return bool(SECRET_CMD_REGEX.search(cmd))

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"decision": "allow"}))
        return

    tool_call = data.get("toolCall", {})
    name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    # 1. File inspection and editing tools
    if name in (
        "view_file", "read_file", "write_to_file",
        "replace_file_content", "multi_replace_file_content"
    ):
        path = args.get("AbsolutePath") or args.get("TargetFile") or ""
        if is_secret_path(path):
            print(json.dumps({
                "decision": "deny",
                "reason": (
                    f"Access to '{path}' is strictly blocked by Vault security policy. "
                    "Agents are forbidden from reading, writing, or inspecting secret files."
                )
            }))
            return

    # 2. Grep search tool
    if name == "grep_search":
        search_path = args.get("SearchPath", "")
        if is_secret_path(search_path):
            print(json.dumps({
                "decision": "deny",
                "reason": (
                    f"Searching in '{search_path}' is strictly blocked by Vault security policy. "
                    "Secrets and credential paths must not be queried."
                )
            }))
            return

    # 3. Shell commands
    if name == "run_command":
        cmd = args.get("CommandLine", "")
        if is_secret_command(cmd):
            print(json.dumps({
                "decision": "deny",
                "reason": (
                    "Execution of command referencing secrets or environment credentials is blocked. "
                    "Consult .env.example or settings.py instead of inspecting real secrets."
                )
            }))
            return

    print(json.dumps({"decision": "allow"}))

if __name__ == "__main__":
    main()
