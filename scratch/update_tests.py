import re
from pathlib import Path

# Resolve path dynamically relative to this script's location
project_root = Path(__file__).resolve().parent.parent
path = project_root / "tests" / "test_agents" / "test_bob.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

# Replace all BobAgent._validate_... with bob_agent._validate_...
content = content.replace("BobAgent._validate_confluence_url", "bob_agent._validate_confluence_url")
content = content.replace("BobAgent._validate_jira_ref", "bob_agent._validate_jira_ref")


def replacer(m):
    return m.group(0).replace("()", "(bob_agent: BobAgent)")


content = re.sub(r"def test_validate_confluence_url_[^\(]+\(\) -> None:", replacer, content)
content = re.sub(r"def test_validate_jira_ref_[^\(]+\(\) -> None:", replacer, content)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated test_bob.py successfully.")
