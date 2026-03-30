"""כלי עזר לעבודה בטוחה עם JSON."""

import json
from typing import Any


def safe_json_loads(text: str) -> Any:
    """מנסה לפרסר JSON ומחזיר None במקרה כשל."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print("\n[ERROR] Failed to parse JSON response.")
        print(text)
        return None
