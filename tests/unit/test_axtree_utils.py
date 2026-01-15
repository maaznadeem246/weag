"""
Unit tests for AXTree utilities.
"""

import pytest
from src.green_agent.environment.axtree_utils import (
    find_button_bid_from_observation,
    map_dom_id_to_bid,
    find_clickable_element_bid,
    _find_button_in_axtree_dict,
    _find_button_in_axtree_string,
)


# Sample AXTree data from a real click-test observation
SAMPLE_AXTREE_DICT = {
    "nodes": [
        {
            "nodeId": "2",
            "ignored": False,
            "role": {"type": "internalRole", "value": "RootWebArea"},
            "name": {"type": "computedString", "value": "Click Test Task"},
            "browsergym_id": "2",
        },
        {
            "nodeId": "3",
            "ignored": False,
            "role": {"type": "role", "value": "generic"},
            "name": {"type": "computedString", "value": ""},
            "browsergym_id": "9",
        },
        {
            "nodeId": "4",
            "ignored": False,
            "role": {"type": "role", "value": "button"},
            "name": {"type": "computedString", "value": "Click Me!"},
            "browsergym_id": "13",
        },
        {
            "nodeId": "5",
            "ignored": False,
            "role": {"type": "internalRole", "value": "StaticText"},
            "name": {"type": "computedString", "value": "Click Me!"},
        },
    ]
}


SAMPLE_AXTREE_STRING = """
{'nodes': [{'nodeId': '2', 'ignored': False, 'role': {'type': 'internalRole', 'value': 'RootWebArea'}, 
'name': {'type': 'computedString', 'value': 'Click Test Task'}, 'browsergym_id': '2'}, 
{'nodeId': '4', 'ignored': False, 'role': {'type': 'role', 'value': 'button'}, 
'name': {'type': 'computedString', 'value': 'Click Me!'}, 'browsergym_id': '13'}]}
"""


SAMPLE_EXTRA_ELEMENT_PROPERTIES = {
    "9": {"attributes": {"id": "wrap", "class": "container"}},
    "13": {"attributes": {"id": "subbtn", "class": "primary-button"}},
    "10": {"attributes": {"id": "query"}},
}


class TestFindButtonInAxtreeDict:
    """Tests for _find_button_in_axtree_dict."""
    
    def test_finds_button_with_role_dict(self):
        """Should find button when role is a dict with value."""
        result = _find_button_in_axtree_dict(SAMPLE_AXTREE_DICT)
        assert result == "13"
    
    def test_finds_button_with_role_string(self):
        """Should find button when role is a plain string."""
        axtree = {
            "nodes": [
                {"role": "generic", "browsergym_id": "1"},
                {"role": "button", "browsergym_id": "5"},
            ]
        }
        result = _find_button_in_axtree_dict(axtree)
        assert result == "5"
    
    def test_returns_none_when_no_button(self):
        """Should return None when no button in tree."""
        axtree = {
            "nodes": [
                {"role": {"value": "generic"}, "browsergym_id": "1"},
                {"role": {"value": "textbox"}, "browsergym_id": "2"},
            ]
        }
        result = _find_button_in_axtree_dict(axtree)
        assert result is None
    
    def test_returns_none_for_empty_nodes(self):
        """Should return None for empty nodes list."""
        result = _find_button_in_axtree_dict({"nodes": []})
        assert result is None
    
    def test_handles_missing_browsergym_id(self):
        """Should skip nodes without browsergym_id."""
        axtree = {
            "nodes": [
                {"role": {"value": "button"}},  # No browsergym_id
                {"role": {"value": "button"}, "browsergym_id": "7"},
            ]
        }
        result = _find_button_in_axtree_dict(axtree)
        assert result == "7"


class TestFindButtonInAxtreeString:
    """Tests for _find_button_in_axtree_string."""
    
    def test_finds_button_in_python_repr_format(self):
        """Should find button in Python repr string format."""
        result = _find_button_in_axtree_string(SAMPLE_AXTREE_STRING)
        assert result == "13"
    
    def test_finds_button_in_json_format(self):
        """Should find button in JSON string format."""
        json_str = '{"role": {"value": "button"}, "browsergym_id": "42"}'
        result = _find_button_in_axtree_string(json_str)
        assert result == "42"
    
    def test_returns_none_when_no_button(self):
        """Should return None when no button mentioned."""
        result = _find_button_in_axtree_string("{'role': 'textbox', 'browsergym_id': '5'}")
        assert result is None


class TestFindButtonBidFromObservation:
    """Tests for find_button_bid_from_observation."""
    
    def test_finds_button_from_axtree_object(self):
        """Should find button from axtree_object field."""
        obs = {"axtree_object": SAMPLE_AXTREE_DICT}
        result = find_button_bid_from_observation(obs)
        assert result == "13"
    
    def test_finds_button_from_initial_observation(self):
        """Should find button from nested initial_observation."""
        obs = {"initial_observation": {"axtree_object": SAMPLE_AXTREE_DICT}}
        result = find_button_bid_from_observation(obs)
        assert result == "13"
    
    def test_finds_button_from_axtree_string(self):
        """Should find button from axtree string field."""
        obs = {"axtree": SAMPLE_AXTREE_STRING}
        result = find_button_bid_from_observation(obs)
        assert result == "13"
    
    def test_finds_button_from_raw_string(self):
        """Should find button when observation is a raw string."""
        result = find_button_bid_from_observation(SAMPLE_AXTREE_STRING)
        assert result == "13"
    
    def test_returns_none_for_empty_observation(self):
        """Should return None for empty observation."""
        result = find_button_bid_from_observation({})
        assert result is None


class TestMapDomIdToBid:
    """Tests for map_dom_id_to_bid."""
    
    def test_maps_dom_id_from_extra_element_properties(self):
        """Should map DOM id to bid from extra_element_properties."""
        obs = {"extra_element_properties": SAMPLE_EXTRA_ELEMENT_PROPERTIES}
        result = map_dom_id_to_bid(obs, "subbtn")
        assert result == "13"
    
    def test_maps_different_dom_id(self):
        """Should map different DOM ids correctly."""
        obs = {"extra_element_properties": SAMPLE_EXTRA_ELEMENT_PROPERTIES}
        result = map_dom_id_to_bid(obs, "wrap")
        assert result == "9"
    
    def test_returns_none_for_unknown_dom_id(self):
        """Should return None for unknown DOM id."""
        obs = {"extra_element_properties": SAMPLE_EXTRA_ELEMENT_PROPERTIES}
        result = map_dom_id_to_bid(obs, "unknown")
        assert result is None
    
    def test_handles_nested_initial_observation(self):
        """Should look in initial_observation for properties."""
        obs = {"initial_observation": {"extra_element_properties": SAMPLE_EXTRA_ELEMENT_PROPERTIES}}
        result = map_dom_id_to_bid(obs, "subbtn")
        assert result == "13"


class TestFindClickableElementBid:
    """Tests for find_clickable_element_bid."""
    
    def test_prefers_dom_id_when_available(self):
        """Should use preferred DOM id when it can be mapped."""
        obs = {
            "axtree_object": SAMPLE_AXTREE_DICT,
            "extra_element_properties": SAMPLE_EXTRA_ELEMENT_PROPERTIES,
        }
        result = find_clickable_element_bid(obs, preferred_dom_id="subbtn")
        assert result == "13"
    
    def test_falls_back_to_button_search(self):
        """Should fall back to button search when DOM id not found."""
        obs = {"axtree_object": SAMPLE_AXTREE_DICT}
        result = find_clickable_element_bid(obs, preferred_dom_id="nonexistent")
        assert result == "13"
    
    def test_works_without_preferred_dom_id(self):
        """Should work when no preferred DOM id given."""
        obs = {"axtree_object": SAMPLE_AXTREE_DICT}
        result = find_clickable_element_bid(obs)
        assert result == "13"
    
    def test_returns_none_when_nothing_found(self):
        """Should return None when no clickable element found."""
        obs = {"axtree_object": {"nodes": []}}
        result = find_clickable_element_bid(obs)
        assert result is None
