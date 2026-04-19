"""Project-wide constants for the AI QA automation pipeline.

Define all constants here for consistency and to avoid magic strings/numbers scattered
throughout the codebase. Configuration values (e.g., LLM temperature, timeouts) belong
in config.py; runtime constants (agent names, stage names, etc.) belong here.
"""

# --- Agent Names ---
AGENT_ALICE = "alice"  # Configuration & orchestration agent
AGENT_BOB = "bob"  # Requirements extraction (Confluence reader)
AGENT_MARY = "mary"  # Test case generation
AGENT_SARAH = "sarah"  # Test script generation (Playwright)
AGENT_JACK = "jack"  # Test execution & reporting

ALL_AGENTS = [AGENT_ALICE, AGENT_BOB, AGENT_MARY, AGENT_SARAH, AGENT_JACK]

# --- Pipeline Stage Names ---
STAGE_CONFIGURATION = "configuration"
STAGE_REQUIREMENTS = "requirements"
STAGE_TEST_CASES = "test_cases"
STAGE_TEST_SCRIPTS = "test_scripts"
STAGE_EXECUTION = "execution"
STAGE_REPORT = "report"

ALL_STAGES = [
    STAGE_CONFIGURATION,
    STAGE_REQUIREMENTS,
    STAGE_TEST_CASES,
    STAGE_TEST_SCRIPTS,
    STAGE_EXECUTION,
    STAGE_REPORT,
]

# --- AgentMessage Types ---
MESSAGE_TYPE_STATUS = "status"  # Progress update (e.g., "Parsing Confluence page 2/5")
MESSAGE_TYPE_RESULT = "result"  # Stage complete with output
MESSAGE_TYPE_ERROR = "error"  # Fatal error occurred
MESSAGE_TYPE_REVIEW = "review"  # Awaiting user approval/rejection
MESSAGE_TYPE_INFO = "info"  # FYI message (no action needed)

ALL_MESSAGE_TYPES = [
    MESSAGE_TYPE_STATUS,
    MESSAGE_TYPE_RESULT,
    MESSAGE_TYPE_ERROR,
    MESSAGE_TYPE_REVIEW,
    MESSAGE_TYPE_INFO,
]

# --- Confidence Thresholds ---
CONFIDENCE_THRESHOLD_HIGH = 0.8  # >= 0.8: High confidence, proceed without review
CONFIDENCE_THRESHOLD_MEDIUM = 0.5  # 0.5-0.79: Medium confidence, optional review
# Below CONFIDENCE_THRESHOLD_MEDIUM (< 0.5): Low confidence, MUST review before proceeding

# --- LLM Model Names ---
LLM_CLAUDE_SONNET = "claude-sonnet-4-6"  # PoC LLM (Anthropic Claude)
LLM_DEEPSEEK = "deepseek-chat"  # M1 on-premise LLM
LLM_QWEN = "qwen-max"  # M1 on-premise LLM (backup)

ALL_LLMS = [LLM_CLAUDE_SONNET, LLM_DEEPSEEK, LLM_QWEN]

# --- Default Timeouts (in seconds) ---
TIMEOUT_MCP_REQUEST = 30  # MCP server call timeout
TIMEOUT_LLM_REQUEST = 60  # LLM API call timeout (may exceed for large generation)
TIMEOUT_BROWSER_ACTION = 30  # Playwright action timeout
TIMEOUT_BROWSER_LOAD = 60  # Page load timeout

# --- Pagination & Limits ---
DEFAULT_CONFLUENCE_PAGE_SIZE = 25  # Results per MCP query
MAX_CONFLUENCE_PAGES = 10  # Maximum pages to fetch before truncating (prevent infinite loops)
MAX_RETRIES_LLM = 3  # Retry failed LLM calls up to N times
MAX_RETRIES_MCP = 2  # Retry failed MCP calls up to N times

# --- HTTP Endpoints (for future API server in Epic 2) ---
API_ENDPOINT_METRICS = "/api/metrics"
API_ENDPOINT_AUDIT = "/api/audit"
API_ENDPOINT_CONFIG = "/api/config"
API_ENDPOINT_RESULTS = "/api/results"

# --- File Naming Conventions ---
OUTPUT_FILE_EXTENSION = ".py"  # Generated scripts are Python files
OUTPUT_DIR_SCRIPTS = "generated_scripts"  # Directory for generated Playwright scripts
OUTPUT_DIR_REPORTS = "reports"  # Directory for execution reports

# --- Database & Persistence (for M1) ---
DB_TABLE_AUDIT = "audit_log"
DB_TABLE_METRICS = "metrics"
DB_TABLE_CACHE = "generation_cache"
