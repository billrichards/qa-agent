"""Tests for qa_agent/config.py — default values and dataclass integrity."""

from qa_agent.config import (
    AuthConfig,
    LLMProvider,
    OutputFormat,
    RecordingConfig,
    ScreenshotConfig,
    TestConfig,
    TestMode,
)


class TestTestConfigDefaults:
    def test_default_mode_is_focused(self):
        assert TestConfig().mode == TestMode.FOCUSED

    def test_default_urls_empty(self):
        assert TestConfig().urls == []

    def test_default_output_formats(self):
        cfg = TestConfig()
        assert OutputFormat.CONSOLE in cfg.output_formats
        assert OutputFormat.MARKDOWN in cfg.output_formats

    def test_default_headless_true(self):
        assert TestConfig().headless is True

    def test_default_viewport(self):
        cfg = TestConfig()
        assert cfg.viewport_width == 1280
        assert cfg.viewport_height == 720

    def test_default_timeout(self):
        assert TestConfig().timeout == 30000

    def test_default_max_depth(self):
        assert TestConfig().max_depth == 3

    def test_default_max_pages(self):
        assert TestConfig().max_pages == 20

    def test_default_all_test_categories_enabled(self):
        cfg = TestConfig()
        assert cfg.test_keyboard is True
        assert cfg.test_mouse is True
        assert cfg.test_forms is True
        assert cfg.test_accessibility is True
        assert cfg.test_console_errors is True
        assert cfg.test_network_errors is True

    def test_default_wcag_compliance_off(self):
        assert TestConfig().test_wcag_compliance is False

    def test_default_auth_is_none(self):
        assert TestConfig().auth is None

    def test_default_same_domain_only(self):
        assert TestConfig().same_domain_only is True

    def test_default_ignore_patterns_empty(self):
        assert TestConfig().ignore_patterns == []

    def test_default_instructions_none(self):
        assert TestConfig().instructions is None

    def test_default_use_plan_cache(self):
        assert TestConfig().use_plan_cache is True

    def test_default_llm_provider_is_anthropic(self):
        assert TestConfig().llm_provider == LLMProvider.ANTHROPIC

    def test_default_ai_model_is_none(self):
        """None means 'use the provider default' — resolved at call time."""
        assert TestConfig().ai_model is None

    def test_llm_provider_can_be_set_to_openai(self):
        cfg = TestConfig(llm_provider=LLMProvider.OPENAI)
        assert cfg.llm_provider == LLMProvider.OPENAI

    def test_ai_model_can_be_overridden(self):
        cfg = TestConfig(ai_model="claude-opus-4-6")
        assert cfg.ai_model == "claude-opus-4-6"

    def test_screenshots_enabled_by_default(self):
        assert TestConfig().screenshots.enabled is True

    def test_recording_disabled_by_default(self):
        assert TestConfig().recording.enabled is False


class TestAuthConfig:
    def test_all_fields_optional(self):
        auth = AuthConfig()
        assert auth.username is None
        assert auth.password is None
        assert auth.auth_url is None
        assert auth.cookies is None
        assert auth.headers is None

    def test_can_set_fields(self):
        auth = AuthConfig(username="user", password="pass", auth_url="https://x.com/login")
        assert auth.username == "user"
        assert auth.password == "pass"
        assert auth.auth_url == "https://x.com/login"


class TestScreenshotConfig:
    def test_defaults(self):
        sc = ScreenshotConfig()
        assert sc.enabled is True
        assert sc.on_error is True
        assert sc.on_interaction is False
        assert sc.full_page is False


class TestRecordingConfig:
    def test_defaults(self):
        rc = RecordingConfig()
        assert rc.enabled is False
        assert rc.video_size == {"width": 1280, "height": 720}


class TestTestMode:
    def test_values(self):
        assert TestMode.FOCUSED.value == "focused"
        assert TestMode.EXPLORE.value == "explore"


class TestOutputFormat:
    def test_values(self):
        assert OutputFormat.CONSOLE.value == "console"
        assert OutputFormat.MARKDOWN.value == "markdown"
        assert OutputFormat.JSON.value == "json"
        assert OutputFormat.PDF.value == "pdf"
