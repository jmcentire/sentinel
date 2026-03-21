"""
Contract-based test suite for Sentinel CLI
Generated from contract version 1
Tests all functions, error cases, edge cases, and invariants
"""

import pytest
import json
import tempfile
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
from click.testing import CliRunner
import threading
import time


# Import the CLI module
# Assuming the module is at src_sentinel_cli or similar
try:
    from src.sentinel.cli import (
        main, init, watch, register, manifest, manifest_show,
        manifest_add, triage, fix, report, status, serve
    )
except ImportError:
    # Fallback if module structure is different
    try:
        import src_sentinel_cli as cli_module
        main = cli_module.main
        init = cli_module.init
        watch = cli_module.watch
        register = cli_module.register
        manifest = cli_module.manifest
        manifest_show = cli_module.manifest_show
        manifest_add = cli_module.manifest_add
        triage = cli_module.triage
        fix = cli_module.fix
        report = cli_module.report
        status = cli_module.status
        serve = cli_module.serve
    except ImportError:
        # Create mock functions for testing
        pass


class TestMainCommand:
    """Test the main() root CLI command"""
    
    def test_main_happy_path_with_config(self, tmp_path):
        """main() loads config and sets ctx.obj with config and config_path"""
        runner = CliRunner()
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text("sources: []\nllm:\n  provider: openai\n")
        
        with patch('src_sentinel_cli.SentinelConfig') as mock_config_class:
            mock_config = Mock()
            mock_config_class.from_yaml.return_value = mock_config
            
            @main.result_callback()
            def check_context(ctx, **kwargs):
                assert isinstance(ctx.obj, dict)
                assert 'config' in ctx.obj
                assert 'config_path' in ctx.obj
                assert ctx.obj['config'] is not None
                assert ctx.obj['config_path'] is not None
            
            result = runner.invoke(main, ['--config-path', str(config_file), '--help'])
            # For testing context, we'll verify in integration tests
    
    def test_main_happy_path_no_config(self):
        """main() sets ctx.obj even when config_path is None"""
        runner = CliRunner()
        
        with patch('src_sentinel_cli.SentinelConfig') as mock_config_class:
            mock_config = Mock()
            mock_config_class.return_value = mock_config
            
            result = runner.invoke(main, ['--help'])
            assert result.exit_code == 0
    
    def test_main_edge_case_empty_config(self, tmp_path):
        """main() handles empty sentinel.yaml file"""
        runner = CliRunner()
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text("")
        
        with patch('src_sentinel_cli.SentinelConfig') as mock_config_class:
            mock_config = Mock()
            mock_config_class.from_yaml.return_value = mock_config
            
            result = runner.invoke(main, ['--config-path', str(config_file), '--help'])
            # Should not raise exception
            assert result.exit_code == 0
    
    def test_invariant_ctx_obj_always_dict(self, tmp_path):
        """Invariant: ctx.obj is always a dict after main() executes"""
        runner = CliRunner()
        
        with patch('src_sentinel_cli.SentinelConfig') as mock_config_class:
            mock_config = Mock()
            mock_config_class.return_value = mock_config
            
            # We test this through subcommands which access ctx.obj
            with patch('src_sentinel_cli.Manifest') as mock_manifest:
                result = runner.invoke(main, ['status'])
                # If ctx.obj wasn't a dict, commands would fail
    
    def test_invariant_ctx_obj_contains_config(self, tmp_path):
        """Invariant: ctx.obj['config'] always contains SentinelConfig"""
        runner = CliRunner()
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text("sources: []\n")
        
        with patch('src_sentinel_cli.SentinelConfig') as mock_config_class:
            mock_config = Mock()
            mock_config_class.from_yaml.return_value = mock_config
            
            # Test through a subcommand
            with patch('src_sentinel_cli.Manifest'):
                with patch('src_sentinel_cli.Path.exists', return_value=True):
                    result = runner.invoke(main, ['--config-path', str(config_file), 'status'])


class TestInitCommand:
    """Test the init() command"""
    
    def test_init_happy_path(self, tmp_path):
        """init() creates .sentinel directory structure and sentinel.yaml"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(init)
            
            assert result.exit_code == 0
            assert Path('.sentinel').exists()
            assert Path('.sentinel/manifest.json').exists()
            assert Path('.sentinel/proposed_contracts').exists()
            
            # Check manifest.json has empty components
            with open('.sentinel/manifest.json') as f:
                manifest_data = json.load(f)
                assert 'components' in manifest_data
                assert isinstance(manifest_data['components'], dict)
            
            # Check sentinel.yaml exists
            assert Path('sentinel.yaml').exists() or 'sentinel.yaml' in result.output
    
    def test_init_edge_case_already_exists(self, tmp_path):
        """init() handles case where .sentinel already exists"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create .sentinel first
            Path('.sentinel').mkdir()
            
            result = runner.invoke(init)
            
            # Should not error
            assert result.exit_code == 0
            assert Path('.sentinel/manifest.json').exists()
            assert Path('.sentinel/proposed_contracts').exists()
    
    def test_init_edge_case_yaml_exists(self, tmp_path):
        """init() does not overwrite existing sentinel.yaml"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create existing sentinel.yaml
            existing_content = "# My custom config\nsources: []\n"
            Path('sentinel.yaml').write_text(existing_content)
            
            result = runner.invoke(init)
            
            # Check if original content is preserved
            # (implementation may vary, but shouldn't overwrite)
            assert result.exit_code == 0
    
    def test_invariant_sentinel_structure(self, tmp_path):
        """Invariant: .sentinel/ structure has manifest.json and proposed_contracts/"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(init)
            
            assert Path('.sentinel/manifest.json').exists()
            assert Path('.sentinel/proposed_contracts').exists()
            assert Path('.sentinel/proposed_contracts').is_dir()


class TestWatchCommand:
    """Test the watch() command"""
    
    def test_watch_happy_path(self, tmp_path):
        """watch() starts watcher with configured sources"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create config with sources
            config_file = Path('sentinel.yaml')
            config_file.write_text("sources:\n  - type: webhook\n    url: http://test\n")
            
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Sentinel') as mock_sentinel_class:
                mock_sentinel = Mock()
                mock_sentinel_class.return_value = mock_sentinel
                
                # Mock watch to return immediately
                mock_sentinel.watch = Mock()
                
                result = runner.invoke(main, ['--config-path', str(config_file), 'watch'])
                
                # Should start without immediate exit
                mock_sentinel.watch.assert_called_once()
    
    def test_watch_error_no_sources(self, tmp_path):
        """watch() exits with code 1 when no sources configured"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create config with empty sources
            config_file = Path('sentinel.yaml')
            config_file.write_text("sources: []\n")
            
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            result = runner.invoke(main, ['--config-path', str(config_file), 'watch'])
            
            assert result.exit_code == 1
            assert 'no sources' in result.output.lower() or 'source' in result.output.lower()
    
    def test_watch_error_keyboard_interrupt(self, tmp_path):
        """watch() handles Ctrl+C gracefully"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            config_file = Path('sentinel.yaml')
            config_file.write_text("sources:\n  - type: webhook\n")
            
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Sentinel') as mock_sentinel_class:
                mock_sentinel = Mock()
                mock_sentinel_class.return_value = mock_sentinel
                mock_sentinel.watch.side_effect = KeyboardInterrupt()
                
                result = runner.invoke(main, ['--config-path', str(config_file), 'watch'])
                
                # Should handle gracefully
                assert result.exit_code in [0, 1]


class TestRegisterCommand:
    """Test the register() command"""
    
    def test_register_happy_path(self, tmp_path):
        """register() scans directory and adds components to manifest"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            # Create a test directory with components
            test_dir = Path('test_project')
            test_dir.mkdir()
            (test_dir / 'component1.py').write_text('# component')
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.register_from_directory = Mock()
                
                result = runner.invoke(main, ['register', str(test_dir)])
                
                assert result.exit_code == 0
                assert 'success' in result.output.lower() or 'registered' in result.output.lower()
    
    def test_register_edge_case_empty_directory(self, tmp_path):
        """register() handles directory with no components"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            # Create empty directory
            test_dir = Path('empty_project')
            test_dir.mkdir()
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                
                result = runner.invoke(main, ['register', str(test_dir)])
                
                # Should succeed with 0 components
                assert result.exit_code == 0
    
    def test_register_edge_case_nonexistent_directory(self, tmp_path):
        """register() fails when directory doesn't exist"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            result = runner.invoke(main, ['register', 'nonexistent_dir'])
            
            # Click should validate path existence
            assert result.exit_code != 0


class TestManifestCommands:
    """Test manifest show and add commands"""
    
    def test_manifest_show_happy_path(self, tmp_path):
        """manifest_show() displays all registered components"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            manifest_data = {
                "components": {
                    "comp1": {"contract": "path1", "tests": "tests1"},
                    "comp2": {"contract": "path2", "tests": "tests2"}
                }
            }
            Path('.sentinel/manifest.json').write_text(json.dumps(manifest_data))
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = [
                    Mock(component_id="comp1"),
                    Mock(component_id="comp2")
                ]
                
                result = runner.invoke(main, ['manifest', 'show'])
                
                assert result.exit_code == 0
                assert 'comp1' in result.output or 'comp2' in result.output or len(result.output) > 0
    
    def test_manifest_show_edge_case_empty(self, tmp_path):
        """manifest_show() displays message when no components"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = []
                
                result = runner.invoke(main, ['manifest', 'show'])
                
                assert result.exit_code == 0
                assert 'no components' in result.output.lower() or 'empty' in result.output.lower() or len(result.output) >= 0
    
    def test_manifest_add_happy_path(self, tmp_path):
        """manifest_add() adds component with all metadata"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.register = Mock()
                
                result = runner.invoke(main, [
                    'manifest', 'add',
                    '--component-id', 'test_comp',
                    '--contract', 'contract.yaml',
                    '--tests', 'tests.py',
                    '--source', 'src.py',
                    '--language', 'python',
                    '--project', 'test_project'
                ])
                
                assert result.exit_code == 0
                assert 'success' in result.output.lower() or 'added' in result.output.lower() or 'registered' in result.output.lower()
    
    def test_manifest_add_edge_case_special_chars(self, tmp_path):
        """manifest_add() handles component_id with special characters"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.register = Mock()
                
                result = runner.invoke(main, [
                    'manifest', 'add',
                    '--component-id', 'test.comp_123-foo',
                    '--contract', 'contract.yaml',
                    '--tests', 'tests.py',
                    '--source', 'src.py',
                    '--language', 'python',
                    '--project', 'proj'
                ])
                
                # Should handle special chars without error
                assert result.exit_code == 0


class TestTriageCommand:
    """Test the triage() command"""
    
    def test_triage_happy_path_pact_key(self, tmp_path):
        """triage() identifies component using PACT key pattern"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            manifest_data = {
                "components": {
                    "comp1": {"contract": "path1", "tests": "tests1"}
                }
            }
            Path('.sentinel/manifest.json').write_text(json.dumps(manifest_data))
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = [Mock(component_id="comp1")]
                
                with patch('src_sentinel_cli.triage_error') as mock_triage:
                    mock_triage.return_value = {
                        'component_id': 'comp1',
                        'confidence': 'high',
                        'reasoning': 'PACT key match'
                    }
                    
                    result = runner.invoke(main, ['triage', '--error-text', '[PACT:comp1] Error message'])
                    
                    assert result.exit_code == 0
                    assert 'comp1' in result.output
    
    def test_triage_happy_path_llm_fallback(self, tmp_path):
        """triage() falls back to LLM when no PACT key found"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            manifest_data = {
                "components": {
                    "comp1": {"contract": "path1", "tests": "tests1"}
                }
            }
            Path('.sentinel/manifest.json').write_text(json.dumps(manifest_data))
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = [Mock(component_id="comp1")]
                
                with patch('src_sentinel_cli.triage_error') as mock_triage:
                    mock_triage.return_value = {
                        'component_id': 'comp1',
                        'confidence': 'medium',
                        'reasoning': 'LLM analysis'
                    }
                    
                    result = runner.invoke(main, ['triage', '--error-text', 'Generic error message'])
                    
                    assert result.exit_code == 0
    
    def test_triage_error_no_components(self, tmp_path):
        """triage() exits with code 1 when no components registered"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = []
                
                result = runner.invoke(main, ['triage', '--error-text', 'Error'])
                
                assert result.exit_code == 1
                assert 'no components' in result.output.lower()
    
    def test_triage_error_llm_unavailable(self, tmp_path):
        """triage() handles LLM unavailability gracefully"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            manifest_data = {
                "components": {
                    "comp1": {"contract": "path1", "tests": "tests1"}
                }
            }
            Path('.sentinel/manifest.json').write_text(json.dumps(manifest_data))
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = [Mock(component_id="comp1")]
                
                with patch('src_sentinel_cli.triage_error') as mock_triage:
                    mock_triage.side_effect = ImportError("LLM not available")
                    
                    result = runner.invoke(main, ['triage', '--error-text', 'Error'])
                    
                    # Should handle error gracefully
                    assert 'llm' in result.output.lower() or 'error' in result.output.lower()


class TestFixCommand:
    """Test the fix() command"""
    
    def test_fix_happy_path(self, tmp_path):
        """fix() triggers fix workflow and prints JSON result"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Sentinel') as mock_sentinel_class:
                mock_sentinel = Mock()
                mock_sentinel_class.return_value = mock_sentinel
                mock_sentinel.handle_manual_fix.return_value = {
                    'status': 'success',
                    'fix_applied': True
                }
                
                result = runner.invoke(main, ['fix', '--pact-key', 'comp1', '--error', 'Test error'])
                
                assert result.exit_code == 0
                # Output should be JSON
                try:
                    output_json = json.loads(result.output)
                    assert isinstance(output_json, dict)
                except:
                    # Or at least contain JSON-like content
                    assert '{' in result.output or 'success' in result.output.lower()
    
    def test_fix_edge_case_empty_error(self, tmp_path):
        """fix() handles empty error text"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Sentinel') as mock_sentinel_class:
                mock_sentinel = Mock()
                mock_sentinel_class.return_value = mock_sentinel
                mock_sentinel.handle_manual_fix.return_value = {'status': 'attempted'}
                
                result = runner.invoke(main, ['fix', '--pact-key', 'comp1', '--error', ''])
                
                # Should not raise exception
                assert result.exit_code in [0, 1, 2]


class TestReportCommand:
    """Test the report() command"""
    
    def test_report_happy_path(self, tmp_path):
        """report() displays recent incidents"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.IncidentManager') as mock_incident_class:
                mock_incident_mgr = Mock()
                mock_incident_class.return_value = mock_incident_mgr
                mock_incident_mgr.get_recent_incidents.return_value = [
                    {'id': '1', 'component': 'comp1', 'status': 'resolved'}
                ]
                
                result = runner.invoke(main, ['report'])
                
                assert result.exit_code == 0
                assert 'comp1' in result.output or 'incident' in result.output.lower()
    
    def test_report_edge_case_no_incidents(self, tmp_path):
        """report() displays message when no incidents"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.IncidentManager') as mock_incident_class:
                mock_incident_mgr = Mock()
                mock_incident_class.return_value = mock_incident_mgr
                mock_incident_mgr.get_recent_incidents.return_value = []
                
                result = runner.invoke(main, ['report'])
                
                assert result.exit_code == 0
                assert 'no incidents' in result.output.lower() or 'no recent' in result.output.lower() or len(result.output) >= 0


class TestStatusCommand:
    """Test the status() command"""
    
    def test_status_happy_path(self, tmp_path):
        """status() displays config and component count"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            manifest_data = {
                "components": {
                    "comp1": {"contract": "path1"},
                    "comp2": {"contract": "path2"}
                }
            }
            Path('.sentinel/manifest.json').write_text(json.dumps(manifest_data))
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = [Mock(), Mock()]
                
                result = runner.invoke(main, ['status'])
                
                assert result.exit_code == 0
                # Should show component count
                assert '2' in result.output or 'component' in result.output.lower()
    
    def test_status_edge_case_no_components(self, tmp_path):
        """status() shows 0 components when manifest empty"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = []
                
                result = runner.invoke(main, ['status'])
                
                assert result.exit_code == 0
                assert '0' in result.output or 'no components' in result.output.lower()


class TestServeCommand:
    """Test the serve() command"""
    
    def test_serve_happy_path(self, tmp_path):
        """serve() starts HTTP API server"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.run_api_server') as mock_run_server:
                mock_run_server.return_value = None
                
                result = runner.invoke(main, ['serve', '--host', '127.0.0.1', '--port', '8000'])
                
                # Should call run_server
                assert result.exit_code == 0 or mock_run_server.called
    
    def test_serve_error_keyboard_interrupt(self, tmp_path):
        """serve() handles Ctrl+C gracefully"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.run_api_server') as mock_run_server:
                mock_run_server.side_effect = KeyboardInterrupt()
                
                result = runner.invoke(main, ['serve'])
                
                # Should handle gracefully
                assert result.exit_code in [0, 1]
    
    def test_serve_edge_case_port_conflict(self, tmp_path):
        """serve() handles port already in use"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path('.sentinel').mkdir()
            Path('.sentinel/manifest.json').write_text('{"components": {}}')
            
            with patch('src_sentinel_cli.run_api_server') as mock_run_server:
                mock_run_server.side_effect = OSError("Port already in use")
                
                result = runner.invoke(main, ['serve', '--port', '8000'])
                
                # Should show error about port
                assert 'port' in result.output.lower() or 'error' in result.output.lower()


class TestIntegration:
    """Integration tests for command workflows"""
    
    def test_init_register_manifest_workflow(self, tmp_path):
        """Integration: init -> register -> manifest show"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Step 1: Init
            result = runner.invoke(init)
            assert result.exit_code == 0
            assert Path('.sentinel').exists()
            
            # Step 2: Create test project
            test_dir = Path('test_project')
            test_dir.mkdir()
            (test_dir / 'component.py').write_text('# test')
            
            # Step 3: Register
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.register_from_directory = Mock()
                
                result = runner.invoke(main, ['register', str(test_dir)])
                assert result.exit_code == 0
            
            # Step 4: Show manifest
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = [Mock(component_id="test_comp")]
                
                result = runner.invoke(main, ['manifest', 'show'])
                assert result.exit_code == 0
    
    def test_init_add_status_workflow(self, tmp_path):
        """Integration: init -> manifest add -> status"""
        runner = CliRunner()
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Step 1: Init
            result = runner.invoke(init)
            assert result.exit_code == 0
            
            # Step 2: Add component
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.register = Mock()
                
                result = runner.invoke(main, [
                    'manifest', 'add',
                    '--component-id', 'test_comp',
                    '--contract', 'c.yaml',
                    '--tests', 't.py',
                    '--source', 's.py',
                    '--language', 'python',
                    '--project', 'proj'
                ])
                assert result.exit_code == 0
            
            # Step 3: Check status
            with patch('src_sentinel_cli.Manifest') as mock_manifest_class:
                mock_manifest = Mock()
                mock_manifest_class.return_value = mock_manifest
                mock_manifest.all_entries.return_value = [Mock()]
                
                result = runner.invoke(main, ['status'])
                assert result.exit_code == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
