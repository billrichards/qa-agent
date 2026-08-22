"""Tests for qa_agent/viewports.py — preset registry, parsing, emulation options."""

from __future__ import annotations

import pytest

from qa_agent.viewports import (
    MAX_DIMENSION,
    MIN_DIMENSION,
    PRESETS,
    Viewport,
    coerce_viewports,
    default_viewport,
    format_preset_table,
    get_preset,
    list_presets,
    parse_viewport,
    parse_viewports,
)


class TestPresets:
    def test_expected_presets_exist(self):
        for name in (
            "desktop", "laptop", "tablet", "tablet-landscape",
            "mobile", "mobile-small", "android",
        ):
            assert name in PRESETS

    def test_preset_names_match_keys(self):
        for key, viewport in PRESETS.items():
            assert key == viewport.name

    def test_preset_names_are_lowercase(self):
        # get_preset() lowercases its lookup, so uppercase keys would be unreachable.
        for key in PRESETS:
            assert key == key.lower()

    def test_mobile_presets_carry_full_emulation(self):
        for name in ("tablet", "tablet-landscape", "mobile", "mobile-small", "android"):
            vp = PRESETS[name]
            assert vp.is_mobile is True
            assert vp.has_touch is True
            assert vp.user_agent, f"{name} must send a device user agent"
            assert vp.device_scale_factor > 1

    def test_desktop_presets_are_not_mobile(self):
        for name in ("desktop", "laptop"):
            vp = PRESETS[name]
            assert vp.is_mobile is False
            assert vp.has_touch is False
            assert vp.user_agent is None

    def test_get_preset_is_case_insensitive(self):
        assert get_preset("MOBILE") is PRESETS["mobile"]
        assert get_preset("  Desktop  ") is PRESETS["desktop"]

    def test_get_preset_unknown_returns_none(self):
        assert get_preset("nope") is None

    def test_list_presets_preserves_registry_order(self):
        assert [vp.name for vp in list_presets()] == list(PRESETS)

    def test_format_preset_table_lists_every_preset(self):
        table = format_preset_table()
        for name in PRESETS:
            assert name in table

    def test_default_viewport_is_legacy_size(self):
        vp = default_viewport()
        assert (vp.width, vp.height) == (1280, 720)
        assert vp.name == "1280x720"
        assert vp.is_mobile is False


class TestViewportProperties:
    def test_size_and_label_for_named_viewport(self):
        vp = PRESETS["mobile"]
        assert vp.size == "390x844"
        assert vp.label == "mobile (390x844)"

    def test_label_for_raw_size_is_not_duplicated(self):
        vp = parse_viewport("1920x1080")
        assert vp.label == "1920x1080"

    def test_slug_sanitizes_unsafe_characters(self):
        vp = Viewport(name="my viewport/2", width=800, height=600)
        assert "/" not in vp.slug
        assert " " not in vp.slug

    def test_slug_never_empty(self):
        assert Viewport(name="", width=800, height=600).slug == "viewport"
        assert Viewport(name="///", width=800, height=600).slug == "___"

    def test_viewport_is_hashable(self):
        # Frozen dataclass — usable in sets/dict keys for dedup.
        assert len({PRESETS["mobile"], PRESETS["mobile"], PRESETS["desktop"]}) == 2


class TestContextOptions:
    def test_plain_size_yields_only_viewport_key(self):
        # Guards the promise that a size-only viewport produces exactly the
        # context options the agent used before viewport profiles existed.
        opts = parse_viewport("1280x720").to_context_options()
        assert opts == {"viewport": {"width": 1280, "height": 720}}

    def test_mobile_preset_yields_full_emulation(self):
        opts = PRESETS["mobile"].to_context_options()
        assert opts["viewport"] == {"width": 390, "height": 844}
        assert opts["device_scale_factor"] == 3.0
        assert opts["is_mobile"] is True
        assert opts["has_touch"] is True
        assert "iPhone" in opts["user_agent"]

    def test_laptop_includes_dpr_without_mobile_flags(self):
        opts = PRESETS["laptop"].to_context_options()
        assert opts["device_scale_factor"] == 2.0
        assert "is_mobile" not in opts
        assert "has_touch" not in opts
        assert "user_agent" not in opts


class TestParseViewport:
    def test_preset_by_name(self):
        assert parse_viewport("tablet") is PRESETS["tablet"]

    def test_raw_size(self):
        vp = parse_viewport("1600x900")
        assert (vp.name, vp.width, vp.height) == ("1600x900", 1600, 900)

    def test_raw_size_with_spaces_and_unicode_multiplier(self):
        assert parse_viewport(" 1600 × 900 ").width == 1600

    def test_uppercase_x_accepted(self):
        assert parse_viewport("1600X900").height == 900

    def test_named_custom_size(self):
        vp = parse_viewport("kiosk=1080x1920")
        assert (vp.name, vp.width, vp.height) == ("kiosk", 1080, 1920)

    def test_named_preset_alias(self):
        vp = parse_viewport("phone=mobile")
        assert vp.name == "phone"
        assert vp.width == PRESETS["mobile"].width
        assert vp.user_agent == PRESETS["mobile"].user_agent

    def test_unknown_name_raises_with_preset_list(self):
        with pytest.raises(ValueError) as exc:
            parse_viewport("phablet")
        assert "mobile" in str(exc.value)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_viewport("   ")

    def test_missing_dimension_raises(self):
        with pytest.raises(ValueError):
            parse_viewport("1920x")

    def test_dimension_below_minimum_raises(self):
        with pytest.raises(ValueError):
            parse_viewport(f"{MIN_DIMENSION - 1}x600")

    def test_dimension_above_maximum_raises(self):
        with pytest.raises(ValueError):
            parse_viewport(f"800x{MAX_DIMENSION + 1}")


class TestParseViewports:
    def test_none_returns_empty(self):
        assert parse_viewports(None) == []

    def test_empty_string_returns_empty(self):
        assert parse_viewports("") == []

    def test_comma_separated_mix(self):
        names = [vp.name for vp in parse_viewports("desktop,mobile,1440x900")]
        assert names == ["desktop", "mobile", "1440x900"]

    def test_list_input_is_flattened(self):
        names = [vp.name for vp in parse_viewports(["desktop", "mobile,tablet"])]
        assert names == ["desktop", "mobile", "tablet"]

    def test_duplicates_collapsed_preserving_order(self):
        names = [vp.name for vp in parse_viewports("mobile,desktop,mobile")]
        assert names == ["mobile", "desktop"]

    def test_blank_segments_ignored(self):
        assert [vp.name for vp in parse_viewports("desktop,, ,mobile")] == ["desktop", "mobile"]

    def test_invalid_entry_raises(self):
        with pytest.raises(ValueError):
            parse_viewports("desktop,bogus")


class TestCoerceViewports:
    def test_none_and_empty(self):
        assert coerce_viewports(None) == []
        assert coerce_viewports([]) == []

    def test_single_viewport_object(self):
        assert coerce_viewports(PRESETS["mobile"]) == [PRESETS["mobile"]]

    def test_string_spec(self):
        assert [vp.name for vp in coerce_viewports("desktop,mobile")] == ["desktop", "mobile"]

    def test_mixed_list(self):
        result = coerce_viewports([
            "mobile",
            PRESETS["desktop"],
            {"name": "kiosk", "width": 1080, "height": 1920},
            "800x600",
        ])
        assert [vp.name for vp in result] == ["mobile", "desktop", "kiosk", "800x600"]

    def test_single_dict(self):
        result = coerce_viewports({"width": 800, "height": 600})
        assert result[0].name == "800x600"

    def test_dict_with_full_emulation(self):
        vp = coerce_viewports([{
            "name": "watch",
            "width": 396,
            "height": 484,
            "device_scale_factor": 2,
            "is_mobile": True,
            "has_touch": True,
            "user_agent": "custom-agent",
        }])[0]
        assert vp.is_mobile is True
        assert vp.has_touch is True
        assert vp.user_agent == "custom-agent"
        assert vp.device_scale_factor == 2.0

    def test_duplicates_collapsed_across_forms(self):
        result = coerce_viewports(["mobile", PRESETS["mobile"], "mobile"])
        assert len(result) == 1

    def test_invalid_dict_raises(self):
        with pytest.raises(ValueError):
            coerce_viewports([{"name": "bad", "width": "wide", "height": 600}])

    def test_dict_missing_dimension_raises(self):
        with pytest.raises(KeyError):
            coerce_viewports([{"name": "bad", "width": 800}])


class TestRoundTrip:
    def test_to_dict_from_dict_preserves_profile(self):
        for vp in list_presets():
            assert Viewport.from_dict(vp.to_dict()) == vp
