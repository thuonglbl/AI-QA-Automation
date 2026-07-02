with open("tests/api/test_admin_users_api.py") as f:
    content = f.read()
content = content.replace(
    '"timezone": "UTC",\n', '"timezone": "UTC",\n                "conversation_language": "en",\n'
)
with open("tests/api/test_admin_users_api.py", "w") as f:
    f.write(content)
