import os

# GitHub Copilot API (OpenAI 호환)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
COPILOT_BASE_URL = "https://api.githubcopilot.com"
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 8192
MAX_CONTEXT_TOKENS = 120000

# 배치당 처리할 파일 수 (컨텍스트 초과 방지)
BATCH_SIZE = 300

# DB
DB_PATH = os.environ.get("FILE_CARE_DB", "file_care.db")
