# 🚀 GitAPI: GitHub Data Extraction Module
> Last updated: 2025-12-20
> Maintained by [LLM4Free](https://github.com/OEvortex/LLM4Free)

LLM4Free's GitAPI module provides a powerful, lightweight GitHub data extraction toolkit within the LLM4Free Python package. It offers comprehensive tools for retrieving GitHub repository, user, organization, gist, and trending data without requiring authentication for public data access.

## Table of Contents

1. [Core Components](#core-components)
2. [Features](#features)
3. [Installation](#installation)
4. [Quick Examples](#quick-examples)
5. [Available Classes](#available-classes)
6. [Error Handling](#error-handling)
7. [Integration Guide](#integration-guide)

## Core Components

### [`gitapi.py`](../llm4free/Extra/GitToolkit/gitapi/__init__.py:1)

The main GitHub API module that provides comprehensive GitHub data extraction capabilities.

```python
from llm4free.Extra.GitToolkit.gitapi import Repository, User, GitSearch, Gist, Organization, Trending

# Initialize and use GitHub data extraction
repo = Repository("OE-LUCIFER", "LLM4Free")
info = repo.get_info()
print(f"Stars: {info['stargazers_count']}")
```

**Key Features:**
- Repository operations (metadata, commits, issues, releases)
- User operations (profile, repositories, followers)
- Search operations (repositories, users, topics)
- Gist operations (public gists, specific gist retrieval)
- Organization operations (details, repositories)
- Trending data (repositories, developers)
- Comprehensive error handling

## Features

### Repository Operations
- Repository metadata, README, license, topics
- Commit history and comparison
- Pull requests and issues
- Releases, branches, and tags
- Contributors, stargazers, watchers, forks
- GitHub Actions workflows
- Repository events and statistics

### User Operations
- Profile information and social accounts
- Repository listing and starred repos
- Follower/Following data
- Organizations and packages
- Events, gists, and SSH/GPG keys

### Search Operations
- Search repositories by query, language, stars
- Search users by name, location, followers
- Search topics, commits, issues, and labels

### Gist Operations
- Get gist by ID with full content
- List public gists
- Gist commits, forks, and revisions
- Gist comments

### Organization Operations
- Organization details and metadata
- Organization repositories
- Public members and events

### Trending
- Trending repositories by language/time
- Trending developers

### Error Handling
- Rate limit detection
- Resource not found handling
- Request retry mechanism
- Custom error types

## Installation

Install as part of the LLM4Free package:

```bash
pip install llm4free
```

Or install with UV package manager:

```bash
uv add llm4free
```

## Quick Examples

### Repository Operations

```python
from llm4free.Extra.GitToolkit.gitapi import Repository

repo = Repository("OE-LUCIFER", "LLM4Free")

# Get basic info
info = repo.get_info()
print(f"Stars: {info['stargazers_count']}")

# Get README
readme = repo.get_readme()
print(f"README: {readme['name']}")

# Get topics
topics = repo.get_topics()
print(f"Topics: {topics['names']}")

# Compare branches
diff = repo.compare("main", "dev")
print(f"Commits ahead: {diff['ahead_by']}")
```

### User Operations

```python
from llm4free.Extra.GitToolkit.gitapi import User

user = User("OE-LUCIFER")

# Get profile
profile = user.get_profile()
print(f"Followers: {profile['followers']}")

# Get social accounts
socials = user.get_social_accounts()
for account in socials:
    print(f"{account['provider']}: {account['url']}")
```

### Search Operations

```python
from llm4free.Extra.GitToolkit.gitapi import GitSearch

search = GitSearch()

# Search repositories
repos = search.search_repositories("llm4free language:python stars:>100")
print(f"Found {repos['total_count']} repos")

# Search users
users = search.search_users("location:india followers:>1000")
print(f"Found {users['total_count']} users")

# Search topics
topics = search.search_topics("machine-learning")
for topic in topics['items'][:5]:
    print(f"Topic: {topic['name']}")
```

### Gist Operations

```python
from llm4free.Extra.GitToolkit.gitapi import Gist

gist = Gist()

# List public gists
public = gist.list_public(per_page=5)
for g in public:
    print(f"Gist: {g['id']} - {g['description']}")

# Get specific gist
data = gist.get("gist_id_here")
print(f"Files: {list(data['files'].keys())}")
```

### Organization Operations

```python
from llm4free.Extra.GitToolkit.gitapi import Organization

org = Organization("microsoft")

# Get org info
info = org.get_info()
print(f"Organization: {info['name']}")
print(f"Public repos: {info['public_repos']}")

# Get org repos
repos = org.get_repos(per_page=10)
for repo in repos:
    print(f"Repo: {repo['name']}")
```

### Trending

```python
from llm4free.Extra.GitToolkit.gitapi import Trending

trending = Trending()

# Get trending repos
repos = trending.get_repositories(language="python", since="weekly")
for repo in repos[:5]:
    print(f"{repo['full_name']} - ⭐ {repo['stars']}")

# Get trending developers
devs = trending.get_developers(language="python")
for dev in devs[:5]:
    print(f"{dev['username']} - {dev.get('name', 'N/A')}")
```

## Available Classes

### Repository Class

The `Repository` class provides comprehensive access to GitHub repository data.

**Methods:**
- `get_info()` - Get basic repository information
- `get_readme(ref=None)` - Get repository README content (API returns base64-encoded `content`)
- `get_license()` - Get repository license information
- `get_topics()` - Get repository topics
- `get_commits(page=1, per_page=30, sha=None)` - Get commit history
- `get_commit(sha)` - Get specific commit details
- `compare(base, head)` - Compare branches
- `get_pull_requests(state="all", page=1, per_page=30)` - Get pull requests
- `get_pull_request(pr_number)` - Get a specific pull request
- `get_pull_request_commits(pr_number)` - Get commits in a pull request
- `get_pull_request_files(pr_number)` - Get files changed in a pull request
- `get_issues(state="all", page=1, per_page=30, labels=None)` - Get issues
- `get_issue(issue_number)` - Get a specific issue
- `get_issue_comments(issue_number)` - Get issue comments
- `get_labels()` - Get labels
- `get_milestones(state="all")` - Get milestones
- `get_releases(page=1, per_page=30)` - Get releases
- `get_release(release_id)` - Get a specific release
- `get_latest_release()` - Get the latest release
- `get_branches(page=1, per_page=30)` - Get branches
- `get_branch(branch)` - Get a specific branch
- `get_tags()` - Get tags
- `get_contributors(page=1, per_page=30)` - Get contributors
- `get_collaborators()` - Get collaborators
- `get_teams()` - Get repository teams
- `get_stargazers(page=1, per_page=30)` - Get stargazers
- `get_watchers(page=1, per_page=30)` - Get watchers
- `get_forks(sort="newest", page=1, per_page=30)` - Get forks
- `get_contents(path="", ref=None)` - Get repository contents
- `get_languages()` - Get repository languages
- `get_events(page=1, per_page=30)` - Get repository events
- `get_workflows()` - Get GitHub Actions workflows
- `get_workflow_runs(workflow_id)` - Get workflow runs
- `get_deployments()` - Get deployments
- `get_traffic()` - Get traffic statistics
- `get_community_profile()` - Get community profile
- `get_code_frequency()` - Get code frequency statistics
- `get_commit_activity()` - Get commit activity statistics

### User Class

The `User` class provides access to GitHub user data.

**Methods:**
- `get_profile()` - Get user profile information
- `get_repositories(page=1, per_page=30, repo_type="all")` - Get user repositories
- `get_starred(page=1, per_page=30)` - Get starred repositories
- `get_followers(page=1, per_page=30)` - Get followers
- `get_following(page=1, per_page=30)` - Get following
- `get_gists(page=1, per_page=30)` - Get user gists
- `get_organizations()` - Get organizations
- `get_public_events(page=1, per_page=30)` - Get public events
- `get_received_events(page=1, per_page=30)` - Get received events
- `get_keys()` - Get SSH keys
- `get_gpg_keys()` - Get GPG keys
- `get_social_accounts()` - Get social accounts
- `get_packages(package_type="container", page=1, per_page=30)` - Get packages

### GitSearch Class

The `GitSearch` class provides GitHub search functionality.

**Methods:**
- `search_repositories(query, sort=None, order="desc", page=1, per_page=30)` - Search repositories by query
- `search_users(query, sort=None, order="desc", page=1, per_page=30)` - Search users
- `search_topics(query, page=1, per_page=30)` - Search topics
- `search_commits(query, sort=None, order="desc", page=1, per_page=30)` - Search commits
- `search_issues(query, sort=None, order="desc", page=1, per_page=30)` - Search issues/PRs
- `search_labels(query, sort=None, order="desc", page=1, per_page=30)` - Search labels

### Gist Class

The `Gist` class provides access to GitHub gists.

**Methods:**
- `get(gist_id)` - Get gist by ID
- `list_public(since=None, page=1, per_page=30)` - List public gists
- `list_for_user(username, since=None, page=1, per_page=30)` - List user's gists
- `get_commits(gist_id, page=1, per_page=30)` - Get gist commits
- `get_forks(gist_id, page=1, per_page=30)` - Get gist forks
- `get_revision(gist_id, sha)` - Get gist revision
- `get_comments(gist_id, page=1, per_page=30)` - Get gist comments

### Organization Class

The `Organization` class provides access to GitHub organization data.

**Methods:**
- `get_info()` - Get organization details
- `get_repos(repo_type="all", sort="created", direction="desc", page=1, per_page=30)` - Get organization repositories
- `get_public_members(page=1, per_page=30)` - Get public members
- `get_events(page=1, per_page=30)` - Get organization events

### Trending Class

The `Trending` class provides access to GitHub trending data.

**Methods:**
- `get_repositories(language="", since="daily", spoken_language="")` - Get trending repositories
- `get_developers(language="", since="daily")` - Get trending developers

## Error Handling

GitAPI includes comprehensive error handling for GitHub API interactions.

```python
from llm4free.Extra.GitToolkit.gitapi import Repository, NotFoundError, RateLimitError

try:
    repo = Repository("nonexistent", "repo")
    info = repo.get_info()
except NotFoundError:
    print("Repository not found")
except RateLimitError:
    print("Rate limit exceeded, try again later")
except Exception as e:
    print(f"An error occurred: {e}")
```

### Exception Types

| Exception | Description |
|-----------|-------------|
| `GitError` | Base exception for all GitHub API errors |
| `RateLimitError` | Raised after retries are exhausted on HTTP 429 |
| `NotFoundError` | Raised when a resource returns HTTP 404 |
| `RequestError` | Raised for other HTTP/network errors (including HTTP 403) |

> [!NOTE]
> The toolkit does not send an authentication token, so GitHub's unauthenticated rate limit applies. HTTP 403 (the status GitHub commonly uses for an exhausted rate limit) is surfaced as `RequestError`, not `RateLimitError`.

## Integration Guide

### With LLM4Free Providers

```python
from llm4free import Client
from llm4free.Extra.GitToolkit.gitapi import Repository

# Get repository data
repo = Repository("OE-LUCIFER", "LLM4Free")
repo_info = repo.get_info()

# Use with the unified client (ChatGPT is a no-auth provider)
client = Client()
response = client.chat.completions.create(
    model="ChatGPT/GPT-6-free",
    messages=[{"role": "user", "content": f"Analyze this GitHub repository: {repo_info}"}],
)
print(response.choices[0].message.content)
```

### With FastAPI

```python
from fastapi import FastAPI, HTTPException
from llm4free.Extra.GitToolkit.gitapi import Repository, NotFoundError

app = FastAPI()

@app.get("/repo/{owner}/{repo}")
async def get_repo_info(owner: str, repo: str):
    """Get GitHub repository information"""
    try:
        repository = Repository(owner, repo)
        info = repository.get_info()
        return {
            "name": info["name"],
            "full_name": info["full_name"],
            "description": info["description"],
            "stars": info["stargazers_count"],
            "forks": info["forks_count"],
            "open_issues": info["open_issues_count"]
        }
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Repository not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### With Async Applications

```python
import asyncio
from llm4free.Extra.GitToolkit.gitapi import Repository

async def get_multiple_repos():
    """Get information from multiple repositories asynchronously"""
    repos = [
        ("OE-LUCIFER", "LLM4Free"),
        ("python", "cpython"),
        ("django", "django")
    ]
    
    results = []
    for owner, repo_name in repos:
        try:
            repo = Repository(owner, repo_name)
            info = repo.get_info()
            results.append({
                "repo": f"{owner}/{repo_name}",
                "stars": info["stargazers_count"],
                "forks": info["forks_count"]
            })
        except Exception as e:
            results.append({
                "repo": f"{owner}/{repo_name}",
                "error": str(e)
            })
    
    return results

# Run the async function
repo_data = asyncio.run(get_multiple_repos())
for data in repo_data:
    print(f"{data['repo']}: {data.get('stars', 'Error')}")
```

### With Data Analysis

```python
import pandas as pd
from llm4free.Extra.GitToolkit.gitapi import Repository, GitSearch

# Get repository statistics
repo = Repository("OE-LUCIFER", "LLM4Free")
contributors = repo.get_contributors()

# Convert to DataFrame
contributors_df = pd.DataFrame([
    {
        "login": c["login"],
        "contributions": c["contributions"],
        "avatar_url": c["avatar_url"]
    }
    for c in contributors
])

print(f"Top contributors:")
print(contributors_df.sort_values("contributions", ascending=False).head(5))

# Search and analyze repositories
search = GitSearch()
results = search.search_repositories("llm4free language:python")

repos_df = pd.DataFrame([
    {
        "name": r["name"],
        "stars": r["stargazers_count"],
        "forks": r["forks_count"],
        "updated": r["updated_at"]
    }
    for r in results["items"]
])

print(f"\nLLM4Free-related repositories:")
print(repos_df.sort_values("stars", ascending=False).head(10))
```

### With CLI Applications

```python
import click
from llm4free.Extra.GitToolkit.gitapi import Repository, User, GitSearch

@click.group()
def cli():
    """GitHub Data CLI"""
    pass

@cli.command()
@click.argument('owner')
@click.argument('repo')
def repo_info(owner, repo):
    """Get repository information"""
    try:
        repository = Repository(owner, repo)
        info = repository.get_info()
        
        click.echo(f"Repository: {info['full_name']}")
        click.echo(f"Description: {info['description']}")
        click.echo(f"Stars: {info['stargazers_count']}")
        click.echo(f"Forks: {info['forks_count']}")
        click.echo(f"Open Issues: {info['open_issues_count']}")
        click.echo(f"License: {info['license']['name'] if info['license'] else 'None'}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

@cli.command()
@click.argument('username')
def user_info(username):
    """Get user information"""
    try:
        user = User(username)
        profile = user.get_profile()
        
        click.echo(f"User: {profile['login']}")
        click.echo(f"Name: {profile['name']}")
        click.echo(f"Followers: {profile['followers']}")
        click.echo(f"Following: {profile['following']}")
        click.echo(f"Public Repos: {profile['public_repos']}")
        click.echo(f"Bio: {profile['bio']}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

@cli.command()
@click.argument('query')
def search_repos(query):
    """Search repositories"""
    try:
        search = GitSearch()
        results = search.search_repositories(query)
        
        click.echo(f"Found {results['total_count']} repositories:")
        for repo in results['items'][:10]:
            click.echo(f"  {repo['full_name']} - ⭐ {repo['stargazers_count']}")
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

if __name__ == '__main__':
    cli()
```

## Usage Tips

> [!TIP]
> - **Rate Limits**: GitHub API has rate limits for unauthenticated requests (60 requests per hour per IP)
> - **Authentication**: Not supported by this toolkit; every request is unauthenticated. Use a separate authenticated GitHub client if you need higher limits
> - **Error Handling**: Always wrap GitHub API calls in try-catch blocks to handle rate limits and network issues
> - **Pagination**: Use `page` and `per_page` parameters to control the results returned
> - **Caching**: Consider caching results for frequently accessed data to reduce API calls
> - **Batch Operations**: These helpers are synchronous; run them in a thread pool if you need concurrency

## Configuration Best Practices

```python
from llm4free.Extra.GitToolkit.gitapi import Repository, RateLimitError, RequestError

# Repository(owner, repo) is the complete constructor - there is no token argument
repo = Repository("owner", "repo")

# Use with retry logic for resilience
import time

max_retries = 3
retry_delay = 60  # seconds

for attempt in range(max_retries):
    try:
        info = repo.get_info()
        break
    except (RateLimitError, RequestError):
        if attempt < max_retries - 1:
            print(f"Request failed, retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
        else:
            raise
```

## Advanced Features

### Custom Query Parameters

```python
from llm4free.Extra.GitToolkit.gitapi import Repository

repo = Repository("OE-LUCIFER", "LLM4Free")

# Get commits with custom parameters
commits = repo.get_commits(
    sha="main",
    per_page=50,
    page=2
)

# Get issues with filters
issues = repo.get_issues(
    state="open",
    labels="bug,enhancement",
    per_page=50
)
```

### Data Transformation

```python
from llm4free.Extra.GitToolkit.gitapi import Repository
import json

repo = Repository("OE-LUCIFER", "LLM4Free")

# Get repository data and transform it
def transform_repo_data(repo_data):
    """Transform repository data into a custom format"""
    return {
        "name": repo_data["name"],
        "full_name": repo_data["full_name"],
        "description": repo_data["description"],
        "metrics": {
            "stars": repo_data["stargazers_count"],
            "forks": repo_data["forks_count"],
            "watchers": repo_data["watchers_count"],
            "issues": repo_data["open_issues_count"]
        },
        "dates": {
            "created": repo_data["created_at"],
            "updated": repo_data["updated_at"],
            "pushed": repo_data["pushed_at"]
        },
        "owner": {
            "login": repo_data["owner"]["login"],
            "type": repo_data["owner"]["type"]
        }
    }

info = repo.get_info()
transformed = transform_repo_data(info)
print(json.dumps(transformed, indent=2))
```

### Integration with Other Tools

```python
import base64
from llm4free.Extra.GitToolkit.gitapi import Repository
from llm4free.sanitize import sanitize_stream

# Get repository README and process it
repo = Repository("OE-LUCIFER", "LLM4Free")
readme = repo.get_readme()

# The GitHub contents API returns base64-encoded content
decoded = base64.b64decode(readme["content"]).decode("utf-8")

# Split/sanitize the decoded text
clean_content = list(sanitize_stream(
    decoded,
    intro_value="",
    to_json=False,
    strip_chars="\n\r\t"
))

print("Cleaned README content:")
for line in clean_content:
    print(line)
```

<div align="center">
  <p>
    <a href="https://github.com/OEvortex/LLM4Free"><img alt="GitHub Repository" src="https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github&logoColor=white"></a>
    <a href="https://t.me/PyscoutAI"><img alt="Telegram Group" src="https://img.shields.io/badge/Telegram%20Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"></a>
  </p>
</div>

*This documentation covers the comprehensive functionality of the [`llm4free.Extra.GitToolkit.gitapi`](../llm4free/Extra/GitToolkit/gitapi/__init__.py:1) module. For the most up-to-date information, refer to the source code and inline documentation.*
