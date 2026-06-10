"""Tests for constants module."""

import ai_qa.constants as c


class TestAgentNames:
    def test_agent_names_exist(self) -> None:
        assert c.AGENT_ALICE == "alice"
        assert c.AGENT_BOB == "bob"
        assert c.AGENT_MARY == "mary"
        assert c.AGENT_SARAH == "sarah"
        assert c.AGENT_JACK == "jack"

    def test_all_agents_list(self) -> None:
        assert c.AGENT_ALICE in c.ALL_AGENTS
        assert c.AGENT_BOB in c.ALL_AGENTS
        assert c.AGENT_MARY in c.ALL_AGENTS
        assert c.AGENT_SARAH in c.ALL_AGENTS
        assert c.AGENT_JACK in c.ALL_AGENTS
        assert len(c.ALL_AGENTS) == 5


class TestStageNames:
    def test_stage_names_exist(self) -> None:
        assert c.STAGE_CONFIGURATION == "configuration"
        assert c.STAGE_REQUIREMENTS == "requirements"
        assert c.STAGE_TEST_CASES == "test_cases"
        assert c.STAGE_TEST_SCRIPTS == "test_scripts"
        assert c.STAGE_EXECUTION == "execution"
        assert c.STAGE_REPORT == "report"

    def test_all_stages_list(self) -> None:
        assert len(c.ALL_STAGES) == 6
        assert all(
            stage in c.ALL_STAGES
            for stage in [
                c.STAGE_CONFIGURATION,
                c.STAGE_REQUIREMENTS,
                c.STAGE_TEST_CASES,
                c.STAGE_TEST_SCRIPTS,
                c.STAGE_EXECUTION,
                c.STAGE_REPORT,
            ]
        )


class TestMessageTypes:
    def test_message_types_exist(self) -> None:
        assert c.MESSAGE_TYPE_STATUS == "status"
        assert c.MESSAGE_TYPE_RESULT == "result"
        assert c.MESSAGE_TYPE_ERROR == "error"
        assert c.MESSAGE_TYPE_REVIEW == "review"
        assert c.MESSAGE_TYPE_INFO == "info"

    def test_all_message_types(self) -> None:
        assert len(c.ALL_MESSAGE_TYPES) == 5


class TestConfidenceThresholds:
    def test_thresholds(self) -> None:
        assert c.CONFIDENCE_THRESHOLD_HIGH == 0.8
        assert c.CONFIDENCE_THRESHOLD_MEDIUM == 0.5
        assert c.CONFIDENCE_THRESHOLD_HIGH > c.CONFIDENCE_THRESHOLD_MEDIUM


class TestLLMNames:
    def test_llm_names(self) -> None:
        assert c.LLM_CLAUDE_SONNET is not None
        assert c.LLM_DEEPSEEK is not None
        assert c.LLM_QWEN is not None
        assert len(c.ALL_LLMS) == 3


class TestTimeouts:
    def test_timeouts_positive(self) -> None:
        assert c.TIMEOUT_MCP_REQUEST > 0
        assert c.TIMEOUT_LLM_REQUEST > 0
        assert c.TIMEOUT_BROWSER_ACTION > 0
        assert c.TIMEOUT_BROWSER_LOAD > 0


class TestPaginationLimits:
    def test_pagination(self) -> None:
        assert c.DEFAULT_CONFLUENCE_PAGE_SIZE > 0
        assert c.MAX_CONFLUENCE_PAGES > 0
        assert c.MAX_RETRIES_LLM >= 1
        assert c.MAX_RETRIES_MCP >= 1


class TestApiEndpoints:
    def test_endpoints(self) -> None:
        assert c.API_ENDPOINT_METRICS.startswith("/")
        assert c.API_ENDPOINT_AUDIT.startswith("/")
        assert c.API_ENDPOINT_CONFIG.startswith("/")
        assert c.API_ENDPOINT_RESULTS.startswith("/")


class TestFileNaming:
    def test_file_conventions(self) -> None:
        assert c.OUTPUT_FILE_EXTENSION == ".py"
        assert c.OUTPUT_DIR_SCRIPTS is not None
        assert c.OUTPUT_DIR_REPORTS is not None


class TestDatabaseConstants:
    def test_db_tables(self) -> None:
        assert c.DB_TABLE_AUDIT is not None
        assert c.DB_TABLE_METRICS is not None
        assert c.DB_TABLE_CACHE is not None
