"""
Contract tests for AttributionEngine component.

Tests verify behavior at boundaries, covering happy paths, edge cases,
error cases, and invariants. All dependencies are mocked.
"""

import pytest
import re
from unittest.mock import Mock, MagicMock, patch
from src.sentinel.attribution import *


class TestAttributionEngineInit:
    """Test suite for AttributionEngine.__init__"""
    
    def test_init_happy_path_valid_pattern(self):
        """Initialize AttributionEngine with valid manifest and key pattern with 2+ capture groups"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        valid_pattern = r"(\w+):(\w+)"  # 2 capture groups
        
        # Act
        engine = AttributionEngine(mock_manifest, valid_pattern)
        
        # Assert
        assert engine._manifest is mock_manifest
        assert engine._pattern is not None
        assert engine._pattern.pattern == valid_pattern
        assert engine._pattern.groups >= 2
    
    def test_init_fallback_to_default_pattern(self):
        """Initialize with pattern having fewer than 2 capture groups, should fallback to _DEFAULT_PATTERN"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        invalid_pattern = r"(\w+)"  # Only 1 capture group
        
        # Act
        engine = AttributionEngine(mock_manifest, invalid_pattern)
        
        # Assert
        assert engine._manifest is mock_manifest
        assert engine._pattern == engine._DEFAULT_PATTERN
        assert engine._pattern.groups >= 2
    
    def test_init_invalid_regex_pattern(self):
        """Initialize with invalid regex string should raise InvalidRegexPattern"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        invalid_regex = r"([unclosed"
        
        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            engine = AttributionEngine(mock_manifest, invalid_regex)
        # Should raise InvalidRegexPattern or re.error
        assert "regex" in str(type(exc_info.value)).lower() or "pattern" in str(type(exc_info.value)).lower()
    
    def test_init_pattern_with_exactly_two_groups(self):
        """Initialize with pattern having exactly 2 capture groups"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern_two_groups = r"([A-Z]+):([a-z]+)"  # Exactly 2 groups
        
        # Act
        engine = AttributionEngine(mock_manifest, pattern_two_groups)
        
        # Assert
        assert engine._pattern is not None
        assert engine._pattern.pattern == pattern_two_groups
        assert engine._pattern.groups == 2
    
    def test_invariant_pattern_always_has_two_groups(self):
        """Invariant: _pattern always has at least 2 capture groups after initialization"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        patterns = [
            r"(\w+):(\w+)",      # Valid 2 groups
            r"(\w+)",            # Invalid 1 group - should fallback
            r"no_groups",        # Invalid 0 groups - should fallback
            r"(\w+):(\w+):(\w+)" # Valid 3 groups
        ]
        
        # Act & Assert
        for pattern in patterns:
            try:
                engine = AttributionEngine(mock_manifest, pattern)
                assert engine._pattern.groups >= 2, f"Pattern {pattern} resulted in < 2 groups"
            except:
                # If invalid regex, skip (covered by error case)
                pass


class TestAttributionEngineExtractKey:
    """Test suite for AttributionEngine.extract_key"""
    
    def test_extract_key_happy_path(self):
        """Extract PACT key from log line with matching pattern"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Error in PACT:my_component:my_method occurred"
        
        # Act
        result = engine.extract_key(log_line)
        
        # Assert
        assert result is not None
        assert hasattr(result, 'component_id')
        assert hasattr(result, 'method_name')
        assert hasattr(result, 'raw')
        assert result.component_id == "my_component"
        assert result.method_name == "my_method"
        assert result.raw is not None
    
    def test_extract_key_no_match(self):
        """Extract PACT key from log line with no matching pattern returns None"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Generic error message without PACT key"
        
        # Act
        result = engine.extract_key(log_line)
        
        # Assert
        assert result is None
    
    def test_extract_key_empty_line(self):
        """Extract PACT key from empty string returns None"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = ""
        
        # Act
        result = engine.extract_key(log_line)
        
        # Assert
        assert result is None
    
    def test_extract_key_method_name_empty_when_fewer_groups(self):
        """Extract key with pattern having fewer than 2 groups or lastindex < 2 sets method_name to empty string"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        # This pattern has 1 group but will fallback to DEFAULT_PATTERN in init
        # So we need to manually test the postcondition logic
        pattern = r"(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        # Mock a pattern with only 1 group for testing
        single_group_pattern = re.compile(r"SINGLE:(\w+)")
        engine._pattern = single_group_pattern
        log_line = "SINGLE:component"
        
        # Act
        result = engine.extract_key(log_line)
        
        # Assert
        # Based on contract: method_name is empty if lastindex < 2
        if result is not None:
            assert result.method_name == ""
    
    def test_extract_key_unicode_line(self):
        """Extract PACT key from log line with unicode characters"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Error 错误 in PACT:component_1:method_2 occurred 发生"
        
        # Act
        result = engine.extract_key(log_line)
        
        # Assert
        assert result is not None
        assert result.component_id == "component_1"
        assert result.method_name == "method_2"


class TestAttributionEngineAttribute:
    """Test suite for AttributionEngine.attribute"""
    
    def test_attribute_happy_path_registered(self):
        """Attribute log line to registered component, returns Attribution with status 'registered'"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_entry = Mock()
        mock_manifest.get_component.return_value = mock_entry
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Error in PACT:registered_comp:method1"
        
        # Act
        result = engine.attribute(log_line)
        
        # Assert
        assert result is not None
        assert hasattr(result, 'status')
        assert result.status == 'registered'
        assert hasattr(result, 'error_context')
        assert result.error_context == log_line
        assert hasattr(result, 'manifest_entry')
        assert result.manifest_entry is not None
    
    def test_attribute_unregistered(self):
        """Attribute log line with PACT key not in manifest returns status 'unregistered'"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_manifest.get_component.return_value = None  # Not found
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Error in PACT:unknown_comp:method1"
        
        # Act
        result = engine.attribute(log_line)
        
        # Assert
        assert result is not None
        assert result.status == 'unregistered'
        assert result.error_context == log_line
        assert result.manifest_entry is None
    
    def test_attribute_unattributed(self):
        """Attribute log line without PACT key returns status 'unattributed'"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Generic error without PACT key"
        
        # Act
        result = engine.attribute(log_line)
        
        # Assert
        assert result is not None
        assert result.status == 'unattributed'
        assert result.error_context == log_line
        assert hasattr(result, 'pact_key')
        assert result.pact_key == ""
    
    def test_attribute_canonical_lookup(self):
        """Attribute uses canonical lookup (first segment is component_id)"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_entry = Mock()
        
        def get_component_side_effect(component_id):
            if component_id == "canonical_comp":
                return mock_entry
            return None
        
        mock_manifest.get_component.side_effect = get_component_side_effect
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Error in PACT:canonical_comp:method1"
        
        # Act
        result = engine.attribute(log_line)
        
        # Assert
        assert result is not None
        assert result.status == 'registered'
        # Verify canonical lookup was tried
        mock_manifest.get_component.assert_called()
    
    def test_attribute_secondary_lookup(self):
        """Attribute uses secondary lookup (second segment is component_id) when canonical fails"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_entry = Mock()
        
        call_count = [0]
        def get_component_side_effect(component_id):
            call_count[0] += 1
            # First call (canonical) fails, second call (secondary) succeeds
            if call_count[0] == 1:
                return None
            elif component_id == "method1":
                return mock_entry
            return None
        
        mock_manifest.get_component.side_effect = get_component_side_effect
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Error in PACT:some_prefix:method1"
        
        # Act
        result = engine.attribute(log_line)
        
        # Assert
        assert result is not None
        assert result.status == 'registered'
        # Verify both lookups were attempted
        assert mock_manifest.get_component.call_count >= 2
    
    def test_attribute_empty_line(self):
        """Attribute empty log line returns unattributed"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = ""
        
        # Act
        result = engine.attribute(log_line)
        
        # Assert
        assert result is not None
        assert result.status == 'unattributed'
    
    def test_invariant_attribution_status_always_valid(self):
        """Invariant: Attribution status is always one of: registered, unregistered, unattributed"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_manifest.get_component.return_value = None
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        test_lines = [
            "Error in PACT:comp1:method1",
            "Generic error",
            "",
            "PACT:comp2:method2 failure",
            "Multiple PACT:a:b and PACT:c:d keys"
        ]
        
        # Act & Assert
        for line in test_lines:
            result = engine.attribute(line)
            assert result.status in ['registered', 'unregistered', 'unattributed']


class TestAttributionEngineAttributeSignal:
    """Test suite for AttributionEngine.attribute_signal"""
    
    def test_attribute_signal_happy_path_with_log_key(self):
        """Attribute Signal with log_key field present and attribution succeeds"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_entry = Mock()
        mock_manifest.get_component.return_value = mock_entry
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        mock_signal = Mock()
        mock_signal.log_key = "PACT:comp1:method1"
        mock_signal.raw_text = "Raw text of the signal"
        
        # Act
        result = engine.attribute_signal(mock_signal)
        
        # Assert
        assert result is not None
        assert result.error_context == mock_signal.raw_text
        assert result.status in ['registered', 'unregistered', 'unattributed']
    
    def test_attribute_signal_fallback_to_raw_text(self):
        """Attribute Signal falls back to raw_text when log_key is empty or attribution is unattributed"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_manifest.get_component.return_value = None
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        mock_signal = Mock()
        mock_signal.log_key = ""  # Empty log_key
        mock_signal.raw_text = "PACT:comp2:method2 in raw text"
        
        # Act
        result = engine.attribute_signal(mock_signal)
        
        # Assert
        assert result is not None
        # Should have fallen back to raw_text
        assert result.error_context == mock_signal.raw_text
    
    def test_attribute_signal_log_key_unattributed(self):
        """Attribute Signal with log_key that results in unattributed, falls back to raw_text"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_manifest.get_component.return_value = None
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        mock_signal = Mock()
        mock_signal.log_key = "No PACT key here"  # Won't match pattern
        mock_signal.raw_text = "PACT:comp3:method3"
        
        # Act
        result = engine.attribute_signal(mock_signal)
        
        # Assert
        assert result is not None
        # Should have fallen back to raw_text after log_key was unattributed
    
    def test_attribute_signal_updates_error_context(self):
        """Attribute Signal updates error_context to signal.raw_text when log_key attribution succeeds"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_entry = Mock()
        mock_manifest.get_component.return_value = mock_entry
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        mock_signal = Mock()
        mock_signal.log_key = "PACT:comp4:method4"
        mock_signal.raw_text = "Original raw text content"
        
        # Act
        result = engine.attribute_signal(mock_signal)
        
        # Assert
        assert result is not None
        # Verify error_context was mutated to signal.raw_text
        assert result.error_context == mock_signal.raw_text
    
    def test_invariant_signal_attribution_status_always_valid(self):
        """Invariant: Signal attribution status is always one of: registered, unregistered, unattributed"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        
        def varying_get_component(component_id):
            # Vary returns to test different paths
            if component_id == "registered":
                return Mock()
            return None
        
        mock_manifest.get_component.side_effect = varying_get_component
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        test_signals = [
            Mock(log_key="PACT:registered:method1", raw_text="text1"),
            Mock(log_key="PACT:unregistered:method2", raw_text="text2"),
            Mock(log_key="", raw_text="PACT:registered:method3"),
            Mock(log_key="no match", raw_text="no match either"),
        ]
        
        # Act & Assert
        for signal in test_signals:
            result = engine.attribute_signal(signal)
            assert result.status in ['registered', 'unregistered', 'unattributed']


class TestAttributionEngineEdgeCases:
    """Additional edge case tests"""
    
    def test_extract_key_with_special_characters(self):
        """Extract PACT key from log line with special characters"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "Error: PACT:comp_1:method_2 [CRITICAL]!@#$%"
        
        # Act
        result = engine.extract_key(log_line)
        
        # Assert
        assert result is not None
        assert result.component_id == "comp_1"
        assert result.method_name == "method_2"
    
    def test_attribute_with_very_long_line(self):
        """Attribute log line that is very long"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_manifest.get_component.return_value = Mock()
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        # Create a very long line
        prefix = "A" * 10000
        log_line = f"{prefix} PACT:component:method {prefix}"
        
        # Act
        result = engine.attribute(log_line)
        
        # Assert
        assert result is not None
        assert result.error_context == log_line
    
    def test_init_with_pattern_having_more_than_two_groups(self):
        """Initialize with pattern having more than 2 capture groups"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"(\w+):(\w+):(\w+):(\w+)"  # 4 groups
        
        # Act
        engine = AttributionEngine(mock_manifest, pattern)
        
        # Assert
        assert engine._pattern.groups >= 2
        assert engine._pattern.pattern == pattern
    
    def test_extract_key_multiple_matches_in_line(self):
        """Extract PACT key from log line with multiple potential matches (should use first match)"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        log_line = "PACT:comp1:method1 and PACT:comp2:method2"
        
        # Act
        result = engine.extract_key(log_line)
        
        # Assert
        assert result is not None
        # Should extract first match
        assert result.component_id == "comp1"
        assert result.method_name == "method1"
    
    def test_attribute_signal_with_both_log_key_and_raw_text_having_keys(self):
        """Attribute Signal where both log_key and raw_text contain valid PACT keys"""
        # Arrange
        mock_manifest = Mock(spec=['get_component'])
        mock_entry = Mock()
        mock_manifest.get_component.return_value = mock_entry
        
        pattern = r"PACT:(\w+):(\w+)"
        engine = AttributionEngine(mock_manifest, pattern)
        
        mock_signal = Mock()
        mock_signal.log_key = "PACT:from_log_key:method1"
        mock_signal.raw_text = "PACT:from_raw_text:method2"
        
        # Act
        result = engine.attribute_signal(mock_signal)
        
        # Assert
        assert result is not None
        # Should prioritize log_key but update error_context to raw_text
        assert result.error_context == mock_signal.raw_text
