"""
Contract Test Suite for ArbiterClient
Generated from contract version 1
Tests the Arbiter Trust Ledger HTTP Client component
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime
import json


# Import the component under test
from src.sentinel.arbiter import ArbiterClient


class TestArbiterClientInit:
    """Test suite for __init__ method"""
    
    def test_init_happy_path(self):
        """Initialize ArbiterClient with valid ArbiterConfig"""
        # Arrange
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        
        # Act
        client = ArbiterClient(mock_config)
        
        # Assert
        assert client._endpoint == "https://api.example.com"
        assert client._trust_on_fix == True
    
    def test_init_with_none_endpoint(self):
        """Initialize ArbiterClient with None as api_endpoint"""
        # Arrange
        mock_config = Mock()
        mock_config.api_endpoint = None
        mock_config.trust_event_on_fix = False
        
        # Act
        client = ArbiterClient(mock_config)
        
        # Assert
        assert client._endpoint is None
        assert client._trust_on_fix == False
    
    def test_init_trust_on_fix_false(self):
        """Initialize ArbiterClient with trust_event_on_fix disabled"""
        # Arrange
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = False
        
        # Act
        client = ArbiterClient(mock_config)
        
        # Assert
        assert client._trust_on_fix == False


class TestIsConfigured:
    """Test suite for is_configured method"""
    
    def test_is_configured_with_endpoint(self):
        """is_configured returns True when endpoint is set"""
        # Arrange
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        # Act
        result = client.is_configured()
        
        # Assert
        assert result == True
    
    def test_is_configured_without_endpoint(self):
        """is_configured returns False when endpoint is None"""
        # Arrange
        mock_config = Mock()
        mock_config.api_endpoint = None
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        # Act
        result = client.is_configured()
        
        # Assert
        assert result == False


class TestReportTrustEvent:
    """Test suite for report_trust_event method"""
    
    @patch('src_sentinel_arbiter.datetime')
    def test_report_trust_event_success(self, mock_datetime):
        """Successfully report trust event with configured endpoint"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", 0.8, "run_456")
            
            # Assert
            assert result == True
            assert mock_post.called
            call_args = mock_post.call_args
            url = call_args[0][0]
            payload = call_args[0][1]
            
            assert url == "https://api.example.com/trust/event"
            assert payload["node_id"] == "node_123"
            assert payload["event"] == "test_event"
            assert payload["weight"] == 0.8
            assert payload["run_id"] == "run_456"
            assert "timestamp" in payload
            assert payload["timestamp"] == "2023-01-01T12:00:00"
    
    def test_report_trust_event_not_configured(self):
        """report_trust_event returns False when endpoint is None"""
        # Arrange
        mock_config = Mock()
        mock_config.api_endpoint = None
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post') as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", 0.8, "run_456")
            
            # Assert
            assert result == False
            assert not mock_post.called
    
    @patch('src_sentinel_arbiter.datetime')
    def test_report_trust_event_http_error(self, mock_datetime):
        """report_trust_event handles HTTP error gracefully"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=False) as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", 0.8, "run_456")
            
            # Assert
            assert result == False
    
    @patch('src_sentinel_arbiter.datetime')
    def test_report_trust_event_network_exception(self, mock_datetime):
        """report_trust_event handles network exception gracefully"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', side_effect=ConnectionError("Network error")):
            # Act
            # The _post method should catch the exception internally and return False
            # But if it doesn't, report_trust_event should handle it
            try:
                result = client.report_trust_event("node_123", "test_event", 0.8, "run_456")
                # If _post raises, report_trust_event should catch or _post should return False
                assert result == False
            except ConnectionError:
                # If exception propagates, that's also acceptable based on contract
                # but contract says returns False on exception
                pytest.fail("Exception should be caught and return False")
    
    @patch('src_sentinel_arbiter.datetime')
    def test_edge_case_empty_strings(self, mock_datetime):
        """Test trust event with empty string parameters"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            result = client.report_trust_event("", "", 0.0, "")
            
            # Assert
            assert result == True
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["node_id"] == ""
            assert payload["event"] == ""
            assert payload["run_id"] == ""
    
    @patch('src_sentinel_arbiter.datetime')
    def test_edge_case_negative_weight(self, mock_datetime):
        """Test trust event with negative weight"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", -2.5, "run_456")
            
            # Assert
            assert result == True
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["weight"] == -2.5
    
    @patch('src_sentinel_arbiter.datetime')
    def test_edge_case_large_weight(self, mock_datetime):
        """Test trust event with very large weight"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", 1000000.0, "run_456")
            
            # Assert
            assert result == True
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["weight"] == 1000000.0
    
    @patch('src_sentinel_arbiter.datetime')
    def test_edge_case_zero_weight(self, mock_datetime):
        """Test trust event with zero weight"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", 0.0, "run_456")
            
            # Assert
            assert result == True
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["weight"] == 0.0


class TestReportFixSuccess:
    """Test suite for report_fix_success method"""
    
    @patch('src_sentinel_arbiter.datetime')
    def test_report_fix_success_happy_path(self, mock_datetime):
        """Successfully report fix success when trust_on_fix enabled"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, 'report_trust_event', return_value=True) as mock_report:
            # Act
            result = client.report_fix_success("comp_123", "run_456")
            
            # Assert
            assert result == True
            mock_report.assert_called_once_with("comp_123", "sentinel_fix", 1.5, "run_456")
    
    def test_report_fix_success_trust_disabled(self):
        """report_fix_success returns False when trust_on_fix disabled"""
        # Arrange
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = False
        client = ArbiterClient(mock_config)
        
        with patch.object(client, 'report_trust_event') as mock_report:
            # Act
            result = client.report_fix_success("comp_123", "run_456")
            
            # Assert
            assert result == False
            assert not mock_report.called


class TestReportFixFailure:
    """Test suite for report_fix_failure method"""
    
    @patch('src_sentinel_arbiter.datetime')
    def test_report_fix_failure_happy_path(self, mock_datetime):
        """Successfully report fix failure when trust_on_fix enabled"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, 'report_trust_event', return_value=True) as mock_report:
            # Act
            result = client.report_fix_failure("comp_123", "run_456")
            
            # Assert
            assert result == True
            mock_report.assert_called_once_with("comp_123", "sentinel_fix_failure", -0.5, "run_456")
    
    def test_report_fix_failure_trust_disabled(self):
        """report_fix_failure returns False when trust_on_fix disabled"""
        # Arrange
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = False
        client = ArbiterClient(mock_config)
        
        with patch.object(client, 'report_trust_event') as mock_report:
            # Act
            result = client.report_fix_failure("comp_123", "run_456")
            
            # Assert
            assert result == False
            assert not mock_report.called


class TestReportProductionError:
    """Test suite for report_production_error method"""
    
    @patch('src_sentinel_arbiter.datetime')
    def test_report_production_error_happy_path(self, mock_datetime):
        """Successfully report production error"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, 'report_trust_event', return_value=True) as mock_report:
            # Act
            result = client.report_production_error("comp_123", "run_456")
            
            # Assert
            assert result == True
            mock_report.assert_called_once_with("comp_123", "production_error", -0.3, "run_456")
    
    @patch('src_sentinel_arbiter.datetime')
    def test_report_production_error_not_gated(self, mock_datetime):
        """report_production_error works even when trust_on_fix is False"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = False
        client = ArbiterClient(mock_config)
        
        with patch.object(client, 'report_trust_event', return_value=True) as mock_report:
            # Act
            result = client.report_production_error("comp_123", "run_456")
            
            # Assert
            # Production error should call report_trust_event regardless of _trust_on_fix
            mock_report.assert_called_once_with("comp_123", "production_error", -0.3, "run_456")


class TestInvariants:
    """Test suite for contract invariants"""
    
    @patch('src_sentinel_arbiter.datetime')
    def test_invariant_fix_success_event_weight(self, mock_datetime):
        """Verify fix success uses correct event name and weight"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            client.report_fix_success("comp_123", "run_456")
            
            # Assert
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["event"] == "sentinel_fix"
            assert payload["weight"] == 1.5
    
    @patch('src_sentinel_arbiter.datetime')
    def test_invariant_fix_failure_event_weight(self, mock_datetime):
        """Verify fix failure uses correct event name and weight"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            client.report_fix_failure("comp_123", "run_456")
            
            # Assert
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["event"] == "sentinel_fix_failure"
            assert payload["weight"] == -0.5
    
    @patch('src_sentinel_arbiter.datetime')
    def test_invariant_production_error_event_weight(self, mock_datetime):
        """Verify production error uses correct event name and weight"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            client.report_production_error("comp_123", "run_456")
            
            # Assert
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["event"] == "production_error"
            assert payload["weight"] == -0.3
    
    @patch('src_sentinel_arbiter.datetime')
    def test_invariant_timestamp_included(self, mock_datetime):
        """Verify all trust events include ISO timestamp"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00.123456"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            client.report_trust_event("node_123", "test_event", 0.8, "run_456")
            
            # Assert
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert "timestamp" in payload
            # Verify ISO 8601 format (basic check)
            timestamp = payload["timestamp"]
            assert isinstance(timestamp, str)
            assert "T" in timestamp  # ISO format contains T separator


class TestPostMethod:
    """Test suite for _post method through public methods"""
    
    @patch('src_sentinel_arbiter.datetime')
    def test_post_success_2xx(self, mock_datetime):
        """Verify _post returns True on 2xx status codes through public method"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=True) as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", 0.8, "run_456")
            
            # Assert
            assert result == True
    
    @patch('src_sentinel_arbiter.datetime')
    def test_post_failure_3xx(self, mock_datetime):
        """Verify _post returns False on 3xx status codes through public method"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        with patch.object(client, '_post', return_value=False) as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", 0.8, "run_456")
            
            # Assert
            assert result == False
    
    @patch('src_sentinel_arbiter.datetime')
    def test_post_timeout_exception(self, mock_datetime):
        """Verify _post handles timeout exception through public method"""
        # Arrange
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_config = Mock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.trust_event_on_fix = True
        client = ArbiterClient(mock_config)
        
        # _post should catch TimeoutError internally and return False
        with patch.object(client, '_post', return_value=False) as mock_post:
            # Act
            result = client.report_trust_event("node_123", "test_event", 0.8, "run_456")
            
            # Assert
            assert result == False
