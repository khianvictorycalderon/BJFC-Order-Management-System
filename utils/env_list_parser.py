import os

def parse_env_list(env_var: str) -> list[str]:
    """
    Parse a comma-separated environment variable into a list of values.

    Example:
        MY_LIST="item1, item2, item3"

    Returns:
        ["item1", "item2", "item3"]

    Missing or empty environment variables return an empty list.
    """
    value = os.getenv(env_var)

    if not value:
        return []

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]