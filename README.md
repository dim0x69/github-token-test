# GITHUB_TOKEN Permissions Audit & Reference Framework

This repository provides both a **comprehensive conceptual overview** of `GITHUB_TOKEN` permission behaviors and a **programmatic, zero-dependency test suite** that you can run in your own GitHub repository to verify and report actual scopes in real-time.

---

## 1. Conceptual Overview: Token Permissions Matrix

By default, GitHub Actions generates a unique `GITHUB_TOKEN` for each workflow run. The permissions of this token depend heavily on the **repository default settings**, the **triggering event**, and whether the workflow was triggered by a **fork**.

### Scenarios & Defaults Matrix

| Trigger Scenario | Default Permissive Repo Settings | Default Restricted Repo Settings | Custom `permissions:` YAML Override |
| :--- | :--- | :--- | :--- |
| **Standard `push` / `workflow_dispatch`** | **Read/Write** on all scopes | **Read-only** on `contents` & `packages`, **None** on others | Strictly matches specified scopes; others set to **None** |
| **`pull_request` (Internal branch)** | **Read/Write** on all scopes | **Read-only** on `contents` & `packages`, **None** on others | Strictly matches specified scopes; others set to **None** |
| **`pull_request` (Public Fork)** | **Read-only** on all scopes (Security Hardening) | **Read-only** on `contents` & `packages`, **None** on others | Cannot elevate beyond **Read-only**; any `write` request is ignored/downgraded |
| **`pull_request_target` (from Fork)** | **Read/Write** on all base-ref scopes | **Read-only** on `contents` & `packages`, **None** on others | Full elevation capabilities (runs in base repo context) |
| **Dependabot PR** | **Read-only** on all scopes | **Read-only** on `contents` & `packages`, **None** on others | Can be elevated using `permissions:` YAML block |

---

## 2. GITHUB_TOKEN Permission Scopes

GitHub Actions allows granular control over 13 distinct permission scopes. When you use the `permissions:` block in your workflow, **all unspecified scopes are automatically set to `none`** (except `metadata` which always has `read` access).

| Scope | Read Capability | Write Capability |
| :--- | :--- | :--- |
| `contents` | Download code, checkouts, read releases | Push code, create branches/tags, create releases |
| `pull-requests` | View PR details, list commits | Add labels, comments, reviews, assignees, or merge PRs |
| `issues` | View issues, comments, labels | Create issues, add comments, edit labels, close issues |
| `actions` | View workflow history, runs | Trigger repository dispatches, cancel runs, delete runs |
| `checks` | View CI checks status | Create check suites or report new custom check statuses |
| `deployments` | List deployments, environments | Create deployments, trigger environment promotions |
| `statuses` | Read commit build statuses | Set commit statuses (yellow/green/red checkmarks) |
| `packages` | Download packages from GitHub Packages | Publish/delete packages |
| `security-events` | View CodeQL and Dependabot alerts | Upload SARIF results, update code scanning alerts |
| `id-token` | N/A | Request OpenID Connect (OIDC) JWTs for cloud authentication (AWS, GCP, etc.) |

---

## 3. How the Programmatic Tester Works

The included Python tester script [`test_permissions.py`](./test_permissions.py) is a zero-dependency audit tool that probes the GitHub REST API under different scopes. It determines authorization without polluting or mutating your repository:

- **Read Operations**: Queries listing endpoints (e.g. `GET /repos/{owner}/{repo}/contents`).
- **Write Operations (Non-destructive probes)**: 
  - To test `contents: write`, it tries to create a temporary test branch `refs/heads/temp-token-tester-probe` and immediately deletes it.
  - To test other write scopes (like `issues`, `pull-requests`, `actions`, `deployments`, `security-events`), it attempts dummy writes targeting a non-existent ID (e.g. Issue/PR `#999999`). 
  - **The HTTP Status Code Trick**: If the API returns `403 Forbidden`, the token **lacks the permission**. If the API returns `404 Not Found` or `422 Unprocessable Entity` for a dummy target, it means the token **possesses the permission** (the request successfully bypassed authorization, but the fake target was missing/invalid).
  - To test `id-token: write`, it checks for the presence of the system OIDC request variables (`ACTIONS_ID_TOKEN_REQUEST_URL`).

At the end of the run, the script writes a beautifully formatted Markdown table directly to the GitHub Action **Job Summary** (`$GITHUB_STEP_SUMMARY`).

---

## 4. Setting Up & Running the Tests

To run these tests programmatically in your own GitHub repository:

### Step 1: Create a New GitHub Repository
1. Go to your GitHub account and create a new repository (e.g., `github-token-test`).
2. Make it **Public** or **Private** (the tests work on both).

### Step 2: Push this Code to GitHub
Open your terminal inside this directory and run:

```bash
# Verify files are tracked
git add .
git commit -m "Initialize token permission audit framework"

# Link your remote repository and push (replace with your GitHub username)
git remote add origin https://github.com/<your-username>/github-token-test.git
git branch -M main
git push -u origin main
```

### Step 3: Trigger the Audits
1. **Default & Custom Scopes Audit**: 
   - Simply pushing to `main` will automatically trigger the standard and custom workflows.
   - You can also navigate to the **Actions** tab of your repository, select **Audit: Default GITHUB_TOKEN Permissions** or **Audit: Custom GITHUB_TOKEN Permissions**, and click **Run workflow**.
2. **Pull Request Audit**:
   - Create a new branch, make a small change, and submit a Pull Request to your own repository. This runs the `pull_request` audit.
3. **Forked Pull Request Audit (Crucial!)**:
   - Ask a friend to fork your repository, make a branch, and create a Pull Request from their fork back to your repository. This triggers the fork PR workflow, demonstrating how GitHub automatically restricts the token to **read-only**.

### Step 4: View the Reports
1. Go to your repository's **Actions** tab.
2. Select any completed workflow run.
3. Scroll down to the bottom of the run overview page to see the rendered **GITHUB_TOKEN Permissions Audit Report** table!
