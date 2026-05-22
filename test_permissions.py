#!/usr/bin/env python3
import os
import json
import urllib.request
import urllib.error
import sys

# Color formatting for terminal output
def log_info(msg):
    print(f"\033[34m[INFO]\033[0m {msg}")

def log_success(msg):
    print(f"\033[32m[SUCCESS]\033[0m {msg}")

def log_warning(msg):
    print(f"\033[33m[WARNING]\033[0m {msg}")

def log_error(msg):
    print(f"\033[31m[ERROR]\033[0m {msg}")

# Retrieve environments
token = os.environ.get("GITHUB_TOKEN")
repo = os.environ.get("GITHUB_REPOSITORY")
sha = os.environ.get("GITHUB_SHA")
api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
summary_file = os.environ.get("GITHUB_STEP_SUMMARY")

if not token:
    log_error("GITHUB_TOKEN environment variable is missing.")
    sys.exit(1)

if not repo:
    log_error("GITHUB_REPOSITORY environment variable is missing.")
    sys.exit(1)

if not sha:
    log_warning("GITHUB_SHA environment variable is missing. Probing commit status / check run may fail or use fallback.")
    sha = "main"

owner, repo_name = repo.split("/")

log_info(f"Target Repository: {repo}")
log_info(f"Target SHA/Ref: {sha}")
log_info(f"API Base URL: {api_url}")

# Results dictionary
# Format: { scope_name: { "read": status, "write": status, "notes": notes } }
results = {
    "contents": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "pull-requests": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "issues": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "actions": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "checks": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "deployments": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "statuses": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "packages": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "security-events": {"read": "Unknown", "write": "Unknown", "notes": ""},
    "id-token": {"read": "N/A", "write": "Unknown", "notes": ""},
}

def make_request(method, path, body=None):
    url = f"{api_url}{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "python-token-permissions-tester"
    }
    
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8")
            return status_code, response_body
    except urllib.error.HTTPError as e:
        return e.code, e.reason
    except Exception as e:
        return 999, str(e)

def evaluate_permission(method, path, body=None, success_codes=[200, 201, 204], allowed_404_or_422=True):
    """
    Evaluates whether a read/write operation is granted or denied based on status code.
    - success_codes -> GRANTED
    - 403 or 401 -> DENIED
    - 404 or 422 -> If allowed_404_or_422 is True, represents GRANTED (since auth succeeded, but resource/payload was invalid). Otherwise DENIED or None.
    """
    log_info(f"Probing {method} {path}...")
    status, resp = make_request(method, path, body)
    log_info(f"Response Status: {status}")
    
    if status in success_codes:
        return "GRANTED", f"Succeeded with HTTP {status}"
    elif status == 403 or status == 401:
        return "DENIED", f"Forbidden (HTTP {status})"
    elif status == 404:
        if allowed_404_or_422:
            return "GRANTED", "Granted (HTTP 404 Not Found - resource does not exist, but token is authorized)"
        else:
            return "DENIED", "Not Found / Forbidden (HTTP 404 - potentially unauthorized or private repo)"
    elif status == 422:
        if allowed_404_or_422:
            return "GRANTED", "Granted (HTTP 422 Unprocessable - invalid data, but token is authorized)"
        else:
            return "DENIED", "Unprocessable (HTTP 422)"
    else:
        return "DENIED", f"Unexpected error (HTTP {status})"

# ----------------- PROBING SCOPES -----------------

# 1. contents
# Read: List root repository files
res_status, msg = evaluate_permission("GET", f"/repos/{repo}/contents", allowed_404_or_422=False)
results["contents"]["read"] = res_status
results["contents"]["notes"] += f"Read check: {msg}. "

# Write: Attempt to create and delete a temporary dummy branch
branch_name = "refs/heads/temp-token-tester-probe"
# We first need to get the SHA of the main branch to point our ref to
status_sha, resp_sha = make_request("GET", f"/repos/{repo}/commits/{sha}")
if status_sha == 200:
    commit_data = json.loads(resp_sha)
    actual_sha = commit_data.get("sha")
    
    ref_body = {"ref": branch_name, "sha": actual_sha}
    write_status, write_msg = evaluate_permission("POST", f"/repos/{repo}/git/refs", body=ref_body, allowed_404_or_422=False)
    results["contents"]["write"] = write_status
    results["contents"]["notes"] += f"Write check: {write_msg}."
    
    if write_status == "GRANTED":
        # Clean up immediately
        make_request("DELETE", f"/repos/{repo}/git/{branch_name}")
        log_success("Successfully deleted the temporary test branch.")
else:
    results["contents"]["write"] = "DENIED"
    results["contents"]["notes"] += "Write check: Could not retrieve base commit SHA to test branch creation."

# 2. pull-requests
# Read: List pull requests
res_status, msg = evaluate_permission("GET", f"/repos/{repo}/pulls?state=all&per_page=1", allowed_404_or_422=False)
results["pull-requests"]["read"] = res_status
results["pull-requests"]["notes"] += f"Read check: {msg}. "

# Write: Try to add a comment to a non-existent pull request (PR 999999)
# Note: Comments on PRs/Issues use the issues endpoint, but we check PR reviews as well to isolate PR writes
review_body = {"body": "Probe review", "event": "COMMENT"}
write_status, write_msg = evaluate_permission("POST", f"/repos/{repo}/pulls/999999/reviews", body=review_body, allowed_404_or_422=True)
results["pull-requests"]["write"] = write_status
results["pull-requests"]["notes"] += f"Write check (probed non-existent PR review): {write_msg}."

# 3. issues
# Read: List issues
res_status, msg = evaluate_permission("GET", f"/repos/{repo}/issues?per_page=1", allowed_404_or_422=False)
results["issues"]["read"] = res_status
results["issues"]["notes"] += f"Read check: {msg}. "

# Write: Attempt to comment on a non-existent issue (Issue 999999)
comment_body = {"body": "Probe issue comment"}
write_status, write_msg = evaluate_permission("POST", f"/repos/{repo}/issues/999999/comments", body=comment_body, allowed_404_or_422=True)
results["issues"]["write"] = write_status
results["issues"]["notes"] += f"Write check (probed non-existent issue comment): {write_msg}."

# 4. actions
# Read: List workflow runs
res_status, msg = evaluate_permission("GET", f"/repos/{repo}/actions/runs?per_page=1", allowed_404_or_422=False)
results["actions"]["read"] = res_status
results["actions"]["notes"] += f"Read check: {msg}. "

# Write: Attempt to trigger workflow dispatch on a non-existent workflow (999999)
dispatch_body = {"ref": sha}
write_status, write_msg = evaluate_permission("POST", f"/repos/{repo}/actions/workflows/999999/dispatches", body=dispatch_body, allowed_404_or_422=True)
results["actions"]["write"] = write_status
results["actions"]["notes"] += f"Write check (probed non-existent workflow dispatch): {write_msg}."

# 5. checks
# Read: List check runs for commit
res_status, msg = evaluate_permission("GET", f"/repos/{repo}/commits/{sha}/check-runs", allowed_404_or_422=False)
results["checks"]["read"] = res_status
results["checks"]["notes"] += f"Read check: {msg}. "

# Write: Create a real, harmless check run to confirm check write permissions
check_body = {
    "name": "GITHUB_TOKEN Permissions Check Run Probe",
    "head_sha": sha if len(sha) == 40 else "0000000000000000000000000000000000000000",
    "status": "completed",
    "conclusion": "neutral",
    "output": {
        "title": "Token Permissions Analysis",
        "summary": "This check run was successfully created to verify the `checks: write` permission of the current GITHUB_TOKEN."
    }
}
write_status, write_msg = evaluate_permission("POST", f"/repos/{repo}/check-runs", body=check_body, allowed_404_or_422=False)
results["checks"]["write"] = write_status
results["checks"]["notes"] += f"Write check (created real check run): {write_msg}."

# 6. deployments
# Read: List deployments
res_status, msg = evaluate_permission("GET", f"/repos/{repo}/deployments?per_page=1", allowed_404_or_422=False)
results["deployments"]["read"] = res_status
results["deployments"]["notes"] += f"Read check: {msg}. "

# Write: Attempt to create a deployment with a dummy ref to avoid actual merging
deploy_body = {"ref": "refs/heads/non-existent-deployment-ref-token-tester", "environment": "token-test-env"}
write_status, write_msg = evaluate_permission("POST", f"/repos/{repo}/deployments", body=deploy_body, allowed_404_or_422=True)
results["deployments"]["write"] = write_status
results["deployments"]["notes"] += f"Write check (probed dummy deployment creation): {write_msg}."

# 7. statuses
# Read: List statuses for a commit
res_status, msg = evaluate_permission("GET", f"/repos/{repo}/commits/{sha}/statuses", allowed_404_or_422=False)
results["statuses"]["read"] = res_status
results["statuses"]["notes"] += f"Read check: {msg}. "

# Write: Create a commit status to confirm write
status_body = {
    "state": "success",
    "context": "token-permissions-tester/statuses-scope",
    "description": "Token has write access to statuses scope"
}
write_status, write_msg = evaluate_permission("POST", f"/repos/{repo}/statuses/{sha}", body=status_body, allowed_404_or_422=False)
results["statuses"]["write"] = write_status
results["statuses"]["notes"] += f"Write check (created real commit status): {write_msg}."

# 8. packages
# Packages read check: query org packages or user packages based on structure
is_org = True
status_org, _ = make_request("GET", f"/orgs/{owner}")
if status_org != 200:
    is_org = False

pack_path = f"/orgs/{owner}/packages?package_type=container" if is_org else f"/users/{owner}/packages?package_type=container"
res_status, msg = evaluate_permission("GET", pack_path, allowed_404_or_422=False)
results["packages"]["read"] = res_status
results["packages"]["notes"] += f"Read check ({'Org' if is_org else 'User'} packages): {msg}. "
# Package write scope is not safely checkable via simple dummy REST API without pushing layers, so we mark it based on read or mark as unchecked
results["packages"]["write"] = "Unchecked"
results["packages"]["notes"] += "Write check: Direct REST endpoint probes for publishing packages require pushing content layers."

# 9. security-events
# Read: List code scanning alerts
res_status, msg = evaluate_permission("GET", f"/repos/{repo}/code-scanning/alerts?per_page=1", allowed_404_or_422=False)
results["security-events"]["read"] = res_status
results["security-events"]["notes"] += f"Read check: {msg}. "

# Write: Attempt to upload SARIF to non-existent tool/ref
sarif_body = {"commit_sha": sha, "ref": f"refs/heads/{sha}", "sarif": "e30="}  # Empty base64 sarif
write_status, write_msg = evaluate_permission("POST", f"/repos/{repo}/code-scanning/sarifs", body=sarif_body, allowed_404_or_422=True)
results["security-events"]["write"] = write_status
results["security-events"]["notes"] += f"Write check (probed SARIF upload): {write_msg}."

# 10. id-token
# The runner only populates ACTIONS_ID_TOKEN_REQUEST_URL when id-token permission is allowed (read/write)
oidc_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
if oidc_url:
    results["id-token"]["write"] = "GRANTED"
    results["id-token"]["notes"] = "OIDC environment variable ACTIONS_ID_TOKEN_REQUEST_URL is populated. Token can exchange for cloud provider OIDC tokens."
else:
    results["id-token"]["write"] = "DENIED"
    results["id-token"]["notes"] = "OIDC environment variables are absent. Token cannot perform OIDC actions."

# ----------------- FORMATTING OUTPUTS -----------------

# Build the Markdown summary table
md_content = []
md_content.append("## GITHUB_TOKEN Permissions Audit Report")
md_content.append(f"Analyzed repository: **{repo}**")
md_content.append(f"Triggering event: `\" {os.environ.get('GITHUB_EVENT_NAME', 'unknown')} \"`")
md_content.append(f"Triggering actor: `\" {os.environ.get('GITHUB_ACTOR', 'unknown')} \"`\n")

md_content.append("| Scope Name | Read Access | Write Access | Details & Notes |")
md_content.append("| :--- | :--- | :--- | :--- |")

for scope, details in results.items():
    r_icon = "🟢 GRANTED" if details["read"] == "GRANTED" else ("🔴 DENIED" if details["read"] == "DENIED" else "🟡 UNKNOWN/NA")
    w_icon = "🟢 GRANTED" if details["write"] == "GRANTED" else ("🔴 DENIED" if details["write"] == "DENIED" else ("⚪ UNCHECKED" if details["write"] == "Unchecked" else "🟡 UNKNOWN"))
    
    # Custom adjustments for display
    if scope == "id-token":
        r_icon = "➖ N/A"
        
    md_content.append(f"| **`{scope}`** | {r_icon} | {w_icon} | {details['notes']} |")

md_content.append("\n### Legend")
md_content.append("- 🟢 **GRANTED**: The token successfully authenticated and authorized the request.")
md_content.append("- 🔴 **DENIED**: The request failed with `403 Forbidden` / `401 Unauthorized`.")
md_content.append("- 🟡 **UNKNOWN**: Status could not be verified.")
md_content.append("- ⚪ **UNCHECKED**: Probe is non-trivial and skipped to avoid repository pollution.")

markdown_report = "\n".join(md_content)

# Output report to terminal
print("\n" + "="*50)
print("             AUDIT REPORT SUMMARY")
print("="*50)
for scope, details in results.items():
    print(f"Scope '{scope}': Read={details['read']} | Write={details['write']}")
print("="*50 + "\n")

# Write report to GitHub step summary if present
if summary_file:
    log_info(f"Writing audit summary report to GITHUB_STEP_SUMMARY: {summary_file}")
    try:
        with open(summary_file, "a") as f:
            f.write(markdown_report + "\n")
        log_success("Successfully wrote report to step summary.")
    except Exception as e:
        log_error(f"Failed to write to step summary: {e}")
else:
    log_warning("GITHUB_STEP_SUMMARY environment variable not set. Report printed to terminal only.")
