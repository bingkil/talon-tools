# Credentials & Authentication

talon-tools uses a **dependency-inversion** pattern for credentials. Tools declare what they need; the host program provides the storage.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Host Program (e.g. Talon)                              │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  CredentialProvider implementation              │    │
│  │  (encrypted store, keyring, env vars, etc.)     │    │
│  └──────────────────────┬──────────────────────────┘    │
│                         │ init(provider)                 │
└─────────────────────────┼───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│  talon_tools.credentials  (contract module)             │
│                                                         │
│  get(key) ──────────► provider.get(key)                 │
│  set_credential(k,v) ─► provider.set(k, v)             │
│  keys() ────────────► provider.keys()                   │
│  list_credentials() ─► registry of all tool needs       │
│  validate(tool, reqs) ► check + register                │
└─────────────────────────────────────────────────────────┘
                          ▲
┌─────────────────────────┼───────────────────────────────┐
│  Tool modules (google, atlassian, spotify, etc.)        │
│                                                         │
│  CREDENTIALS = [CredentialRequirement(...), ...]        │
│  build_tools():                                         │
│      validate("tool_name", CREDENTIALS)                 │
│      token = get("MY_TOKEN")                            │
│      ...                                                │
└─────────────────────────────────────────────────────────┘
```

## Key Principles

1. **talon-tools never owns credential storage.** It defines the interface; the host implements persistence.
2. **All credentials flow through `get()` / `set_credential()`.** No direct file I/O, no keyring calls, no env var parsing in tool code.
3. **Tools declare requirements.** Each tool exports a `CREDENTIALS` list so the host can discover what's needed.
4. **Static and OAuth tokens use the same API.** A JIRA API token and a Google OAuth refresh token are both just `get("KEY")` / `set_credential("KEY", value)`.

---

## Contract API Reference

### `get(key, default=MISSING) → str`

Read a credential. Delegates to the injected provider, falls back to env vars if no provider is configured.

```python
from talon_tools.credentials import get

url = get("JIRA_URL")                    # raises KeyError if missing
token = get("OPTIONAL_KEY", "")          # returns "" if missing
```

### `set_credential(key, value) → None`

Write a credential. Delegates to the provider's `set()` method. Used during onboarding and OAuth token refresh.

```python
from talon_tools.credentials import set_credential

# During onboarding
set_credential("JIRA_URL", "https://company.atlassian.net")
set_credential("JIRA_API_TOKEN", "ATATT3xFfGF0...")

# After OAuth refresh
set_credential("GOOGLE_TOKEN", refreshed_creds.to_json())
```

### `keys() → set[str]`

Return all known credential keys from the provider (useful for discovery).

```python
from talon_tools.credentials import keys

all_keys = keys()  # {"JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", ...}
```

### `validate(tool, requirements) → None`

Check that all required credentials are available. Raises `MissingCredentialsError` if any are missing. Also registers the requirements in the internal registry for `list_credentials()`.

```python
from talon_tools.credentials import CredentialRequirement, validate

CREDENTIALS = [
    CredentialRequirement("JIRA_URL", "Jira instance URL"),
    CredentialRequirement("JIRA_API_TOKEN", "Jira API token"),
]

def build_tools():
    validate("atlassian", CREDENTIALS)  # raises if missing
    ...
```

### `list_credentials(tool=None) → dict | list`

Discover credential requirements. Used by onboarding programs.

```python
from talon_tools.credentials import list_credentials

# All tools
all_reqs = list_credentials()
# {"atlassian": [...], "google": [...], "spotify": [...]}

# Single tool
jira_reqs = list_credentials("atlassian")
# [CredentialRequirement("JIRA_URL", ...), CredentialRequirement("JIRA_API_TOKEN", ...)]
```

### `register(tool, requirements) → None`

Manually register requirements without validation. Useful at module load time.

```python
from talon_tools.credentials import register, CredentialRequirement

CREDENTIALS = [CredentialRequirement("MY_KEY", "description")]
register("my_tool", CREDENTIALS)
```

### `init(provider) → None`

Inject a credential provider. Called once by the host program at startup.

```python
from talon_tools import credentials

credentials.init(my_provider)  # my_provider implements CredentialProvider protocol
```

### `reset() → None`

Clear the provider (falls back to env vars only). Useful in tests.

---

## Types

### `CredentialRequirement`

```python
@dataclass
class CredentialRequirement:
    key: str            # e.g. "JIRA_URL"
    description: str    # human-readable explanation
    required: bool      # True = tool fails without it; False = optional
    hint: str           # URL or instruction to obtain it
```

### `CredentialProvider` (Protocol)

```python
class CredentialProvider(Protocol):
    def get(self, key: str, default: Any = ...) -> str: ...
    def keys(self) -> set[str]: ...
```

The provider may optionally implement `set(key, value)` to support writes.

### `MissingCredentialsError`

Raised by `validate()` when required credentials are absent. Contains `.tool` (str) and `.missing` (list of `CredentialRequirement`).

---

## Writing a Tool

Every tool module must:

1. Declare `CREDENTIALS` — the list of credentials it needs.
2. Call `validate()` at the top of `build_tools()`.
3. Use `get()` to read credentials at runtime.
4. Use `set_credential()` if it needs to persist tokens (OAuth refresh).

### Example: Static credentials (JIRA)

```python
"""Atlassian/Jira tool."""
from talon_tools import Tool, ToolResult
from talon_tools.credentials import get as cred, CredentialRequirement, validate

CREDENTIALS = [
    CredentialRequirement("JIRA_URL", "Jira instance URL (e.g. https://company.atlassian.net)"),
    CredentialRequirement("JIRA_USERNAME", "Jira username (email)"),
    CredentialRequirement("JIRA_API_TOKEN", "Jira API token",
                          hint="https://id.atlassian.com/manage-profile/security/api-tokens"),
]


def build_tools() -> list[Tool]:
    validate("atlassian", CREDENTIALS)

    url = cred("JIRA_URL")
    username = cred("JIRA_USERNAME")
    token = cred("JIRA_API_TOKEN")

    async def search_issues(args):
        # use url, username, token to call Jira API
        ...

    return [Tool(name="jira_search", ...)]
```

### Example: OAuth2 credentials (Spotify)

```python
"""Spotify tool."""
from talon_tools.credentials import get as cred, set_credential, CredentialRequirement, validate

CREDENTIALS = [
    CredentialRequirement("SPOTIFY_CLIENT_ID", "Spotify app client ID",
                          hint="https://developer.spotify.com/dashboard"),
    CredentialRequirement("SPOTIFY_CLIENT_SECRET", "Spotify app client secret"),
]


def build_tools() -> list[Tool]:
    validate("spotify", CREDENTIALS)
    ...


def get_access_token():
    """Return a valid access token, refreshing if expired."""
    client_id = cred("SPOTIFY_CLIENT_ID")
    client_secret = cred("SPOTIFY_CLIENT_SECRET")

    # Load cached token
    cached = cred("SPOTIFY_TOKEN", "")
    if not cached:
        raise RuntimeError("No token. Run setup first.")

    token_info = json.loads(cached)

    # Refresh if expired
    if token_info["expires_at"] < time.time() + 60:
        token_info = refresh(token_info, client_id, client_secret)
        set_credential("SPOTIFY_TOKEN", json.dumps(token_info))

    return token_info["access_token"]
```

### Example: OAuth2 credentials (Google)

```python
"""Google auth."""
from talon_tools.credentials import get as cred, set_credential

def get_credentials():
    """Return valid Google OAuth credentials, refreshing if needed."""
    token_json = cred("GOOGLE_TOKEN", "")
    if not token_json:
        raise RuntimeError("No Google token. Run: talon auth google")

    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        set_credential("GOOGLE_TOKEN", creds.to_json())

    return creds
```

---

## Implementing a Provider (Host Program)

A host program must implement the `CredentialProvider` protocol and call `init()` at startup.

### Minimal example (env-var only)

```python
from talon_tools import credentials


class EnvProvider:
    """Reads credentials from environment variables."""

    def get(self, key, default=None):
        import os
        val = os.environ.get(key.upper())
        if val is None:
            if default is not None:
                return default
            raise KeyError(key)
        return val

    def keys(self):
        import os
        return {k for k in os.environ if k == k.upper() and "_" in k}


credentials.init(EnvProvider())
```

### Full example (encrypted store + env fallback)

```python
from talon_tools import credentials


class EncryptedStoreProvider:
    """Reads from encrypted .credentials.enc files, writes back on set()."""

    def __init__(self, store: dict[str, str]):
        self._store = store

    def get(self, key, default=None):
        val = self._store.get(key.upper())
        if val is not None:
            return val
        import os
        val = os.environ.get(key.upper())
        if val is not None:
            return val
        if default is not None:
            return default
        raise KeyError(key)

    def keys(self):
        import os
        result = set(self._store.keys())
        result.update(k for k in os.environ if k == k.upper() and "_" in k)
        return result

    def set(self, key, value):
        self._store[key.upper()] = value
        self._persist()

    def _persist(self):
        # encrypt and write self._store to disk
        ...


# At startup:
store = load_and_decrypt(".credentials.enc")
credentials.init(EncryptedStoreProvider(store))
```

---

## Onboarding Flow

The onboarding program uses `list_credentials()` and `set_credential()` to walk the user through setup:

```python
from talon_tools.credentials import list_credentials, set_credential

def onboard_tool(tool_name: str):
    """Interactive onboarding for a single tool."""
    reqs = list_credentials(tool_name)
    if not reqs:
        print(f"No credentials needed for {tool_name}")
        return

    print(f"\n  Setting up {tool_name}")
    print(f"  {'─' * 40}")

    for req in reqs:
        label = f"  {req.description}"
        if req.hint:
            label += f"\n    → {req.hint}"
        if not req.required:
            label += " (optional)"
        print(label)

        value = input(f"  {req.key}: ").strip()
        if value:
            set_credential(req.key, value)
        elif req.required:
            print(f"  ⚠ Skipped required credential: {req.key}")

    print(f"  ✓ {tool_name} configured\n")


def onboard_all():
    """Onboard all registered tools."""
    for tool_name in list_credentials():
        onboard_tool(tool_name)
```

---

## Testing

Use `reset()` and env vars to test tools without a real provider:

```python
import os
from talon_tools.credentials import reset, get

reset()  # no provider — falls back to env vars

os.environ["JIRA_URL"] = "https://test.atlassian.net"
os.environ["JIRA_USERNAME"] = "test@example.com"
os.environ["JIRA_API_TOKEN"] = "fake-token"

# Now tool code works against env vars
assert get("JIRA_URL") == "https://test.atlassian.net"
```

Or inject a dict-based provider for full control:

```python
from talon_tools import credentials


class DictProvider:
    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=None):
        if key.upper() in self._data:
            return self._data[key.upper()]
        if default is not None:
            return default
        raise KeyError(key)

    def keys(self):
        return set(self._data.keys())

    def set(self, key, value):
        self._data[key.upper()] = value


store = {"JIRA_URL": "https://test.atlassian.net", "JIRA_API_TOKEN": "tok"}
credentials.init(DictProvider(store))
```
