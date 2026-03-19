"""Quick validation script for AI server connectivity."""

import os
import sys

os.environ["PYTHONUTF8"] = "1"

from ai_connection import AIClient, AIAuthError, load_config


def main():
    print("Loading config...")
    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}")
        sys.exit(1)

    print(f"Server: {config.base_url}")
    print(f"Model:  {config.model}")
    print(f"HTTP/2: {config.http2}")
    print()

    with AIClient(config) as client:
        # Health check
        print("--- Health Check ---")
        healthy = client.health_check()
        print(f"Server reachable: {healthy}")
        if not healthy:
            print("Cannot reach server. Check VPN connection and config.")
            sys.exit(1)
        print()

        # List models
        print("--- Available Models ---")
        try:
            models = client.list_models()
            for m in models:
                print(f"  - {m}")
        except AIAuthError:
            print("  (route restricted by virtual key)")
        except Exception as e:
            print(f"  Error: {e}")
        print()

        # Chat test
        print("--- Chat Test ---")
        try:
            response = client.chat([
                {"role": "user", "content": "Hello, are you there? Reply in one sentence."}
            ])
            choices = response.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                print(f"Model: {response.get('model', '?')}")
                print(f"Reply: {msg.get('content', '(empty)')}")
            else:
                print(f"Unexpected response: {response}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
