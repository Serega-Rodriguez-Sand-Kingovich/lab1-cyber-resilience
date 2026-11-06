"""HTTP healthcheck for Docker; works without curl and without API secrets."""

import json
import urllib.error
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
            value = json.load(response)
            if response.status == 200 and value.get("status") == "healthy":
                return 0
    except (OSError, ValueError, urllib.error.URLError):
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
