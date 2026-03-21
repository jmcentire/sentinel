"""
Contract Test Suite for SentinelAPI
Generated from contract version 1

Tests verify SentinelAPI behavior at boundaries using pytest and pytest-aiohttp.
All dependencies are mocked except aiohttp.web infrastructure.
"""

import pytest
import json
import asyncio
from datetime import datetime
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import re

# Import the component under test
from src.sentinel.api import SentinelAPI


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_sentinel():
    """Create a mock Sentinel instance with all required attributes."""
    sentinel = Mock()
    sentinel.version = "1.0.0"
    sentinel.sources = []
    sentinel.manifest = {}
    sentinel.incidents = []
    sentinel.fixes = []
    sentinel.config = Mock(auto_fix_enabled=True, manual_review_required=False)
    
    # Mock methods
    sentinel.apply_fix = AsyncMock(return_value=Mock(model_dump=lambda: {"status": "success"}))
    sentinel.register_component = Mock()
    
    return sentinel


@pytest.fixture
def api_instance(mock_sentinel):
    """Create a SentinelAPI instance with mocked sentinel."""
    return SentinelAPI(mock_sentinel)


@pytest.fixture
async def client(api_instance):
    """Create an aiohttp test client."""
    async with TestClient(TestServer(api_instance._app)) as test_client:
        yield test_client


# ============================================================================
# __init__ Tests
# ============================================================================

def test_init_happy_path(mock_sentinel):
    """Test __init__ sets all fields correctly with valid sentinel instance."""
    api = SentinelAPI(mock_sentinel)
    
    # Verify _sentinel is set
    assert api._sentinel is mock_sentinel
    
    # Verify _app is initialized as web.Application
    assert isinstance(api._app, web.Application)
    
    # Verify _runner is None
    assert api._runner is None
    
    # Verify _start_time is set
    assert api._start_time is not None
    assert isinstance(api._start_time, str)
    
    # Verify routes are configured (check that router has routes)
    assert len(api._app.router.resources()) > 0


def test_init_start_time_format(mock_sentinel):
    """Test __init__ sets _start_time in ISO format."""
    api = SentinelAPI(mock_sentinel)
    
    # Verify ISO 8601 format
    iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+'
    assert re.match(iso_pattern, api._start_time), f"_start_time '{api._start_time}' does not match ISO format"
    
    # Verify it can be parsed as datetime
    parsed = datetime.fromisoformat(api._start_time)
    assert isinstance(parsed, datetime)


# ============================================================================
# _setup_routes Tests
# ============================================================================

def test_setup_routes_all_registered(api_instance):
    """Test _setup_routes registers all required routes."""
    routes = {}
    for resource in api_instance._app.router.resources():
        route_info = resource.get_info()
        if 'path' in route_info:
            path = route_info['path']
        elif 'formatter' in route_info:
            path = route_info['formatter']
        else:
            continue
        
        for route in resource:
            method = route.method
            if path not in routes:
                routes[path] = []
            routes[path].append(method)
    
    # Verify all required routes
    assert '/status' in routes
    assert 'GET' in routes['/status']
    
    assert '/manifest' in routes
    assert 'GET' in routes['/manifest']
    
    assert '/fixes' in routes
    assert 'GET' in routes['/fixes']
    
    # Check for dynamic route /fixes/{fix_id}
    dynamic_route_found = False
    for path in routes:
        if 'fix_id' in path or path.startswith('/fixes/'):
            dynamic_route_found = True
            break
    assert dynamic_route_found or any('{fix_id}' in str(r.get_info()) for r in api_instance._app.router.resources())
    
    assert '/fix' in routes
    assert 'POST' in routes['/fix']
    
    assert '/register' in routes
    assert 'POST' in routes['/register']
    
    assert '/metrics' in routes
    assert 'GET' in routes['/metrics']


@pytest.mark.asyncio
async def test_route_404_for_undefined(client):
    """Test undefined routes return 404."""
    resp = await client.get('/undefined')
    assert resp.status == 404


@pytest.mark.asyncio
async def test_route_405_for_wrong_method(client):
    """Test wrong HTTP method returns 405."""
    resp = await client.post('/status')
    assert resp.status == 405


# ============================================================================
# start/stop Tests
# ============================================================================

@pytest.mark.asyncio
async def test_start_happy_path(api_instance):
    """Test start() initializes runner and starts TCP server."""
    await api_instance.start('127.0.0.1', 8080)
    
    # Verify _runner is initialized
    assert api_instance._runner is not None
    assert isinstance(api_instance._runner, web.AppRunner)
    
    # Cleanup
    await api_instance.stop()


@pytest.mark.asyncio
async def test_stop_with_runner(api_instance):
    """Test stop() cleans up runner when it exists."""
    # Start the server first
    await api_instance.start('127.0.0.1', 8081)
    
    # Verify runner exists
    assert api_instance._runner is not None
    
    # Stop the server
    await api_instance.stop()
    
    # Runner should still exist but be cleaned up (implementation detail)
    # The important thing is no errors occurred


@pytest.mark.asyncio
async def test_stop_without_runner(api_instance):
    """Test stop() handles case when _runner is None."""
    # Verify runner is None
    assert api_instance._runner is None
    
    # Stop should not raise an error
    await api_instance.stop()
    
    # No assertions needed - just verify no exception


# ============================================================================
# _handle_status Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_status_happy_path(client, mock_sentinel):
    """Test _handle_status returns correct status information."""
    # Setup mock sentinel state
    mock_sentinel.version = "2.0.0"
    mock_sentinel.sources = [Mock(), Mock()]
    mock_sentinel.manifest = {"comp1": Mock(), "comp2": Mock(), "comp3": Mock()}
    mock_sentinel.incidents = [Mock(status="active"), Mock(status="resolved")]
    mock_sentinel.fixes = [Mock(), Mock(), Mock(), Mock()]
    mock_sentinel.config.auto_fix_enabled = True
    mock_sentinel.config.manual_review_required = False
    
    resp = await client.get('/status')
    assert resp.status == 200
    
    data = await resp.json()
    
    # Verify all required fields
    assert 'version' in data
    assert data['version'] == "2.0.0"
    
    assert 'started_at' in data
    assert isinstance(data['started_at'], str)
    
    assert 'sources' in data
    assert data['sources'] == 2
    
    assert 'components' in data
    assert data['components'] == 3
    
    assert 'active_incidents' in data
    
    assert 'total_fixes' in data
    assert data['total_fixes'] == 4
    
    # Configuration flags
    assert 'auto_fix_enabled' in data
    assert 'manual_review_required' in data


# ============================================================================
# _handle_manifest Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_manifest_happy_path(client, mock_sentinel):
    """Test _handle_manifest returns all registered components."""
    # Setup manifest with mock entries
    mock_entry1 = Mock()
    mock_entry1.model_dump.return_value = {"component_id": "comp1", "version": 1}
    
    mock_entry2 = Mock()
    mock_entry2.model_dump.return_value = {"component_id": "comp2", "version": 2}
    
    mock_sentinel.manifest = {
        "comp1": mock_entry1,
        "comp2": mock_entry2
    }
    
    resp = await client.get('/manifest')
    assert resp.status == 200
    
    data = await resp.json()
    
    # Verify components dictionary
    assert 'components' in data
    assert isinstance(data['components'], dict)
    assert len(data['components']) == 2
    assert 'comp1' in data['components']
    assert 'comp2' in data['components']
    
    # Verify model_dump was called
    assert mock_entry1.model_dump.called
    assert mock_entry2.model_dump.called


# ============================================================================
# _handle_fixes Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_fixes_happy_path(client, mock_sentinel):
    """Test _handle_fixes returns up to 50 most recent fixes."""
    # Create 30 mock fixes
    fixes = []
    for i in range(30):
        fix = Mock()
        fix.model_dump.return_value = {"fix_id": f"fix_{i}", "timestamp": i}
        fixes.append(fix)
    
    mock_sentinel.fixes = fixes
    
    resp = await client.get('/fixes')
    assert resp.status == 200
    
    data = await resp.json()
    
    # Verify it's a list
    assert isinstance(data, list)
    
    # Verify at most 50 fixes
    assert len(data) <= 50
    
    # Verify we got all 30 fixes
    assert len(data) == 30
    
    # Verify each fix was serialized
    for fix in fixes:
        assert fix.model_dump.called


@pytest.mark.asyncio
async def test_handle_fixes_empty(client, mock_sentinel):
    """Test _handle_fixes returns empty array when no fixes exist."""
    mock_sentinel.fixes = []
    
    resp = await client.get('/fixes')
    assert resp.status == 200
    
    data = await resp.json()
    
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_handle_fixes_more_than_50(client, mock_sentinel):
    """Test _handle_fixes limits to 50 when more fixes exist."""
    # Create 100 mock fixes with timestamps
    fixes = []
    for i in range(100):
        fix = Mock()
        fix.timestamp = datetime.now().isoformat()
        fix.model_dump.return_value = {"fix_id": f"fix_{i}", "index": i}
        fixes.append(fix)
    
    mock_sentinel.fixes = fixes
    
    resp = await client.get('/fixes')
    assert resp.status == 200
    
    data = await resp.json()
    
    # Verify exactly 50 fixes returned
    assert len(data) == 50
    
    # Verify they are the newest 50 (reverse chronological order)
    # The last 50 in the list should be returned first
    returned_indices = [item['index'] for item in data]
    assert returned_indices == list(range(99, 49, -1))


# ============================================================================
# _handle_fix_detail Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_fix_detail_found(client, mock_sentinel):
    """Test _handle_fix_detail returns fix details for valid fix_id."""
    # Create mock fix
    mock_fix = Mock()
    mock_fix.fix_id = "valid_fix_id"
    mock_fix.model_dump.return_value = {"fix_id": "valid_fix_id", "status": "success"}
    
    mock_sentinel.fixes = [mock_fix]
    
    resp = await client.get('/fixes/valid_fix_id')
    assert resp.status == 200
    
    data = await resp.json()
    
    assert data['fix_id'] == "valid_fix_id"
    assert mock_fix.model_dump.called


@pytest.mark.asyncio
async def test_handle_fix_detail_not_found(client, mock_sentinel):
    """Test _handle_fix_detail returns 404 for non-existent fix_id."""
    mock_sentinel.fixes = []
    
    resp = await client.get('/fixes/nonexistent_id')
    assert resp.status == 404
    
    data = await resp.json()
    assert 'error' in data


@pytest.mark.asyncio
async def test_handle_fix_detail_special_chars(client, mock_sentinel):
    """Test _handle_fix_detail handles fix_id with special characters."""
    # Create mock fix with special characters
    fix_id = "fix-id_123.test"
    mock_fix = Mock()
    mock_fix.fix_id = fix_id
    mock_fix.model_dump.return_value = {"fix_id": fix_id}
    
    mock_sentinel.fixes = [mock_fix]
    
    # URL encode the fix_id
    import urllib.parse
    encoded_id = urllib.parse.quote(fix_id, safe='')
    
    resp = await client.get(f'/fixes/{encoded_id}')
    # Should handle it correctly (either 200 or 404, but not 500)
    assert resp.status in [200, 404]


# ============================================================================
# _handle_manual_fix Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_manual_fix_happy_path(client, mock_sentinel):
    """Test _handle_manual_fix succeeds with valid JSON body."""
    payload = {"pact_key": "test_pact", "error": "test_error"}
    
    resp = await client.post('/fix', json=payload)
    assert resp.status == 200
    
    data = await resp.json()
    
    # Verify apply_fix was called
    assert mock_sentinel.apply_fix.called
    
    # Verify response contains result
    assert data is not None


@pytest.mark.asyncio
async def test_handle_manual_fix_invalid_json(client):
    """Test _handle_manual_fix returns 400 for invalid JSON."""
    # Send malformed JSON
    resp = await client.post('/fix', data="not valid json{", headers={'Content-Type': 'application/json'})
    assert resp.status == 400
    
    data = await resp.json()
    assert 'error' in data


@pytest.mark.asyncio
async def test_handle_manual_fix_missing_pact_key(client):
    """Test _handle_manual_fix returns 400 when pact_key is missing."""
    payload = {"error": "test_error"}
    
    resp = await client.post('/fix', json=payload)
    assert resp.status == 400
    
    data = await resp.json()
    assert 'error' in data


@pytest.mark.asyncio
async def test_handle_manual_fix_missing_error(client):
    """Test _handle_manual_fix returns 400 when error is missing."""
    payload = {"pact_key": "test_pact"}
    
    resp = await client.post('/fix', json=payload)
    assert resp.status == 400
    
    data = await resp.json()
    assert 'error' in data


@pytest.mark.asyncio
async def test_handle_manual_fix_empty_pact_key(client):
    """Test _handle_manual_fix returns 400 when pact_key is empty."""
    payload = {"pact_key": "", "error": "test_error"}
    
    resp = await client.post('/fix', json=payload)
    assert resp.status == 400
    
    data = await resp.json()
    assert 'error' in data


@pytest.mark.asyncio
async def test_handle_manual_fix_empty_error(client):
    """Test _handle_manual_fix returns 400 when error is empty."""
    payload = {"pact_key": "test_pact", "error": ""}
    
    resp = await client.post('/fix', json=payload)
    assert resp.status == 400
    
    data = await resp.json()
    assert 'error' in data


# ============================================================================
# _handle_register Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_register_happy_path(client, mock_sentinel):
    """Test _handle_register succeeds with valid component_id."""
    payload = {"component_id": "test_component"}
    
    resp = await client.post('/register', json=payload)
    assert resp.status == 200
    
    data = await resp.json()
    
    # Verify status and component_id in response
    assert 'status' in data or 'component_id' in data
    
    # Verify register_component was called
    assert mock_sentinel.register_component.called


@pytest.mark.asyncio
async def test_handle_register_invalid_json(client):
    """Test _handle_register returns 400 for invalid JSON."""
    resp = await client.post('/register', data="invalid{json", headers={'Content-Type': 'application/json'})
    assert resp.status == 400
    
    data = await resp.json()
    assert 'error' in data


@pytest.mark.asyncio
async def test_handle_register_missing_component_id(client):
    """Test _handle_register returns 400 when component_id is missing."""
    payload = {"other_field": "value"}
    
    resp = await client.post('/register', json=payload)
    assert resp.status == 400
    
    data = await resp.json()
    assert 'error' in data


@pytest.mark.asyncio
async def test_handle_register_empty_component_id(client):
    """Test _handle_register returns 400 when component_id is empty."""
    payload = {"component_id": ""}
    
    resp = await client.post('/register', json=payload)
    assert resp.status == 400
    
    data = await resp.json()
    assert 'error' in data


# ============================================================================
# _handle_metrics Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_metrics_happy_path(client, mock_sentinel):
    """Test _handle_metrics returns aggregate metrics."""
    # Setup mock metrics data
    mock_sentinel.incidents = [
        Mock(status="active"),
        Mock(status="active"),
        Mock(status="resolved")
    ]
    
    # Create fixes with success/failure status
    fix1 = Mock()
    fix1.status = "success"
    fix1.spend_usd = 1.234
    
    fix2 = Mock()
    fix2.status = "failed"
    fix2.spend_usd = 2.567
    
    fix3 = Mock()
    fix3.status = "success"
    fix3.spend_usd = 3.891
    
    mock_sentinel.fixes = [fix1, fix2, fix3]
    mock_sentinel.manifest = {"comp1": Mock(), "comp2": Mock()}
    
    resp = await client.get('/metrics')
    assert resp.status == 200
    
    data = await resp.json()
    
    # Verify all required fields
    assert 'total_incidents' in data
    assert 'active_incidents' in data
    assert 'total_fixes_attempted' in data
    assert 'fixes_succeeded' in data
    assert 'fixes_failed' in data
    assert 'total_spend_usd' in data
    assert 'components_registered' in data


@pytest.mark.asyncio
async def test_handle_metrics_spend_rounding(client, mock_sentinel):
    """Test _handle_metrics rounds spend to 2 decimal places."""
    # Create fixes with various spend amounts
    fix1 = Mock()
    fix1.status = "success"
    fix1.spend_usd = 1.23456789
    
    fix2 = Mock()
    fix2.status = "success"
    fix2.spend_usd = 2.98765432
    
    mock_sentinel.fixes = [fix1, fix2]
    mock_sentinel.incidents = []
    mock_sentinel.manifest = {}
    
    resp = await client.get('/metrics')
    assert resp.status == 200
    
    data = await resp.json()
    
    # Verify spend is rounded to 2 decimal places
    spend = data['total_spend_usd']
    assert isinstance(spend, (int, float))
    
    # Check that it has at most 2 decimal places
    spend_str = f"{spend:.10f}"
    decimal_part = spend_str.split('.')[1]
    # Remove trailing zeros
    decimal_part = decimal_part.rstrip('0')
    assert len(decimal_part) <= 2


# ============================================================================
# Invariant Tests
# ============================================================================

def test_invariant_start_time_constant(mock_sentinel):
    """Test _start_time remains constant after initialization."""
    api = SentinelAPI(mock_sentinel)
    
    initial_start_time = api._start_time
    
    # Perform various operations
    import time
    time.sleep(0.01)
    
    # Verify _start_time hasn't changed
    assert api._start_time == initial_start_time


def test_invariant_app_persists(mock_sentinel):
    """Test _app persists for lifetime of instance."""
    api = SentinelAPI(mock_sentinel)
    
    initial_app = api._app
    
    # Perform operations
    api._setup_routes()
    
    # Verify _app is same instance
    assert api._app is initial_app


@pytest.mark.asyncio
async def test_invariant_runner_none_before_start(mock_sentinel):
    """Test _runner is None until start() is called."""
    api = SentinelAPI(mock_sentinel)
    
    # Verify _runner is None before start
    assert api._runner is None
    
    # Start the server
    await api.start('127.0.0.1', 8082)
    
    # Verify _runner is not None after start
    assert api._runner is not None
    
    # Cleanup
    await api.stop()
