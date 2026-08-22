"""Tests for qa_agent/config.py — default values and dataclass integrity."""

import pytest

from qa_agent.config import (
    AuthConfig,
    LLMProvider,
    OutputFormat,
    RecordingConfig,
    ScreenshotConfig,
    TestConfig,
    TestMode,
)
from qa_agent.viewports import Viewport


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
        assert TestConfig().max_pages == 100

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


class TestRateLimit:
    def test_default_rate_limit(self):
        assert TestConfig().rate_limit == 3.0

    def test_zero_stays_disabled(self):
        assert TestConfig(rate_limit=0).rate_limit == 0.0

    def test_negative_normalizes_to_zero(self):
        assert TestConfig(rate_limit=-5).rate_limit == 0.0

    def test_value_within_range_preserved(self):
        assert TestConfig(rate_limit=10.0).rate_limit == 10.0

    def test_value_above_max_is_clamped(self):
        cfg = TestConfig(rate_limit=999)
        assert cfg.rate_limit == cfg.RATE_LIMIT_MAX

    def test_non_numeric_falls_back_to_default(self):
        assert TestConfig(rate_limit="not-a-number").rate_limit == 3.0  # type: ignore[arg-type]


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


class TestConfigViewports:
    """TestConfig normalises whatever viewport shape a caller passes."""

    def test_default_is_single_legacy_viewport(self):
        """No viewports given must behave exactly like the pre-feature default."""
        config = TestConfig()
        assert config.viewport_names == ["1280x720"]
        assert (config.viewport_width, config.viewport_height) == (1280, 720)

    def test_legacy_scalars_seed_the_single_viewport(self):
        config = TestConfig(viewport_width=1024, viewport_height=768)
        assert config.viewport_names == ["1024x768"]
        assert config.viewports[0].width == 1024

    def test_preset_names_are_resolved(self):
        config = TestConfig(viewports=["mobile"])
        vp = config.viewports[0]
        assert (vp.width, vp.height) == (390, 844)
        # Presets carry full device emulation, not just a size.
        assert vp.is_mobile and vp.has_touch

    def test_mixed_specs_preserve_order(self):
        config = TestConfig(viewports=["desktop", "1440x900", "mobile"])
        assert config.viewport_names == ["desktop", "1440x900", "mobile"]

    def test_legacy_scalars_mirror_first_viewport(self):
        """Existing readers of viewport_width/height keep seeing a real value."""
        config = TestConfig(viewports=["mobile", "desktop"])
        assert (config.viewport_width, config.viewport_height) == (390, 844)

    def test_dict_input_is_coerced(self):
        config = TestConfig(viewports=[{"name": "kiosk", "width": 1080, "height": 1920}])
        assert config.viewport_names == ["kiosk"]

    def test_viewport_objects_pass_through(self):
        vp = Viewport(name="custom", width=800, height=600)
        assert TestConfig(viewports=[vp]).viewports == [vp]

    def test_viewports_are_capped(self):
        config = TestConfig(viewports=[f"{600 + i}x800" for i in range(20)])
        assert len(config.viewports) == TestConfig.VIEWPORTS_MAX

    def test_invalid_spec_raises(self):
        """A typo must not silently resolve to some other size."""
        with pytest.raises(ValueError):
            TestConfig(viewports=["moblie"])

    def test_out_of_range_legacy_scalars_fall_back(self):
        """Bad legacy width/height degrade to the default, matching workers/rate_limit."""
        config = TestConfig(viewport_width=-5, viewport_height=0)
        assert config.viewport_names == ["1280x720"]
