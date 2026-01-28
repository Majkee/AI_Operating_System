"""Tests for Ansible Network Plugin."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import plugin components
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "skills"))

from ansible_network import (
    AnsibleNetworkPlugin,
    NetworkDevice,
    PlaybookResult,
    AnsibleExecutor,
    BUILTIN_PLAYBOOKS,
)
from aios.skills import PluginBase, ToolDefinition, Recipe


class TestNetworkDevice:
    """Test NetworkDevice dataclass."""

    def test_creation(self):
        """Test creating a network device."""
        device = NetworkDevice(
            hostname="switch01",
            ip_address="192.168.1.1",
            device_type="cisco.ios.ios"
        )
        assert device.hostname == "switch01"
        assert device.ip_address == "192.168.1.1"
        assert device.device_type == "cisco.ios.ios"
        assert device.username == "admin"  # Default
        assert device.port == 22  # Default

    def test_to_inventory_entry(self):
        """Test converting to Ansible inventory format."""
        device = NetworkDevice(
            hostname="router01",
            ip_address="10.0.0.1",
            device_type="cisco.ios.ios",
            username="netadmin",
            port=2222
        )
        entry = device.to_inventory_entry()

        assert entry["ansible_host"] == "10.0.0.1"
        assert entry["ansible_network_os"] == "cisco.ios.ios"
        assert entry["ansible_user"] == "netadmin"
        assert entry["ansible_port"] == 2222
        assert entry["ansible_connection"] == "network_cli"

    def test_with_groups(self):
        """Test device with groups."""
        device = NetworkDevice(
            hostname="sw01",
            ip_address="192.168.1.10",
            device_type="arista.eos.eos",
            groups=["switches", "datacenter"]
        )
        assert "switches" in device.groups
        assert "datacenter" in device.groups

    def test_with_variables(self):
        """Test device with custom variables."""
        device = NetworkDevice(
            hostname="fw01",
            ip_address="10.0.0.254",
            device_type="cisco.ios.ios",
            variables={"site": "headquarters", "role": "firewall"}
        )
        entry = device.to_inventory_entry()
        assert entry["site"] == "headquarters"
        assert entry["role"] == "firewall"


class TestPlaybookResult:
    """Test PlaybookResult dataclass."""

    def test_success_result(self):
        """Test successful playbook result."""
        result = PlaybookResult(
            success=True,
            changed=5,
            failed=0,
            skipped=2,
            unreachable=0,
            output="PLAY RECAP...",
            duration_seconds=15.5
        )
        assert result.success is True
        assert result.changed == 5
        assert result.failed == 0

    def test_failed_result(self):
        """Test failed playbook result."""
        result = PlaybookResult(
            success=False,
            failed=3,
            unreachable=1,
            error="Connection timeout"
        )
        assert result.success is False
        assert result.failed == 3
        assert "timeout" in result.error.lower()


class TestAnsibleExecutor:
    """Test AnsibleExecutor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.executor = AnsibleExecutor(
            inventory_path=Path(self.temp_dir) / "inventory.yml"
        )
        self.executor.playbooks_path = Path(self.temp_dir) / "playbooks"
        self.executor.backups_path = Path(self.temp_dir) / "backups"

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ensure_directories(self):
        """Test directory creation."""
        self.executor.ensure_directories()

        assert self.executor.inventory_path.parent.exists()
        assert self.executor.playbooks_path.exists()
        assert self.executor.backups_path.exists()

    def test_generate_inventory_single_device(self):
        """Test generating inventory for a single device."""
        devices = [
            NetworkDevice(
                hostname="router01",
                ip_address="192.168.1.1",
                device_type="cisco.ios.ios"
            )
        ]
        inventory = self.executor.generate_inventory(devices)

        assert "router01" in inventory
        assert "192.168.1.1" in inventory
        assert "cisco.ios.ios" in inventory

    def test_generate_inventory_multiple_devices(self):
        """Test generating inventory for multiple devices."""
        devices = [
            NetworkDevice("sw01", "10.0.0.1", "cisco.ios.ios"),
            NetworkDevice("sw02", "10.0.0.2", "cisco.ios.ios"),
            NetworkDevice("rtr01", "10.0.0.254", "cisco.iosxr.iosxr"),
        ]
        inventory = self.executor.generate_inventory(devices)

        assert "sw01" in inventory
        assert "sw02" in inventory
        assert "rtr01" in inventory

    def test_parse_play_recap(self):
        """Test parsing Ansible play recap."""
        output = """
PLAY RECAP *********************************************************************
router01                   : ok=3    changed=1    unreachable=0    failed=0    skipped=1
switch01                   : ok=3    changed=2    unreachable=0    failed=0    skipped=0
"""
        stats = self.executor._parse_play_recap(output)

        assert stats["changed"] == 3  # 1 + 2
        assert stats["failed"] == 0
        assert stats["skipped"] == 1
        assert stats["unreachable"] == 0

    @patch("subprocess.run")
    def test_run_adhoc_success(self, mock_run):
        """Test successful ad-hoc command."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="router01 | SUCCESS",
            stderr=""
        )

        result = self.executor.run_adhoc(
            pattern="router01",
            module="ping"
        )

        assert result["success"] is True
        assert "SUCCESS" in result["output"]

    @patch("subprocess.run")
    def test_run_adhoc_failure(self, mock_run):
        """Test failed ad-hoc command."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Connection refused"
        )

        result = self.executor.run_adhoc(
            pattern="router01",
            module="ping"
        )

        assert result["success"] is False

    @patch("subprocess.run")
    def test_run_playbook_success(self, mock_run):
        """Test successful playbook execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="PLAY RECAP\nrouter01 : ok=2 changed=1 failed=0",
            stderr=""
        )

        # Create a dummy playbook
        self.executor.ensure_directories()
        playbook = self.executor.playbooks_path / "test.yml"
        playbook.write_text("---\n- name: Test\n  hosts: all\n")

        result = self.executor.run_playbook(str(playbook))

        assert result.success is True

    def test_run_playbook_ansible_not_found(self):
        """Test handling when Ansible is not installed."""
        # Don't mock subprocess - let it fail naturally if ansible not installed
        self.executor.ensure_directories()
        playbook = self.executor.playbooks_path / "test.yml"
        playbook.write_text("---\n- name: Test\n  hosts: all\n")

        result = self.executor.run_playbook(str(playbook))

        # Either succeeds (ansible installed) or fails gracefully
        assert isinstance(result, PlaybookResult)


class TestAnsibleNetworkPlugin:
    """Test AnsibleNetworkPlugin class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = AnsibleNetworkPlugin()
        self.temp_dir = tempfile.mkdtemp()

        # Override paths for testing
        self.plugin._executor = AnsibleExecutor(
            inventory_path=Path(self.temp_dir) / "inventory.yml"
        )
        self.plugin.executor.playbooks_path = Path(self.temp_dir) / "playbooks"
        self.plugin.executor.backups_path = Path(self.temp_dir) / "backups"
        self.plugin.executor.ensure_directories()

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_is_plugin_base(self):
        """Test that plugin inherits from PluginBase."""
        assert isinstance(self.plugin, PluginBase)

    def test_metadata(self):
        """Test plugin metadata."""
        meta = self.plugin.metadata

        assert meta.name == "ansible-network"
        assert meta.version == "1.0.0"
        assert "network" in meta.description.lower()
        assert meta.author == "AIOS Community"

    def test_get_tools(self):
        """Test that plugin returns tools."""
        tools = self.plugin.get_tools()

        assert len(tools) > 0
        assert all(isinstance(t, ToolDefinition) for t in tools)

        # Check for expected tools
        tool_names = [t.name for t in tools]
        assert "ansible_run_playbook" in tool_names
        assert "ansible_adhoc" in tool_names
        assert "ansible_add_device" in tool_names
        assert "ansible_list_devices" in tool_names
        assert "ansible_backup_config" in tool_names

    def test_get_recipes(self):
        """Test that plugin returns recipes."""
        recipes = self.plugin.get_recipes()

        assert len(recipes) > 0
        assert all(isinstance(r, Recipe) for r in recipes)

        # Check for expected recipes
        recipe_names = [r.name for r in recipes]
        assert "network_health_check" in recipe_names
        assert "network_backup" in recipe_names

    def test_lifecycle_hooks_exist(self):
        """Test that lifecycle hooks are implemented."""
        # These should not raise
        self.plugin.on_load()
        self.plugin.on_session_start()
        self.plugin.on_session_end()
        self.plugin.on_unload()

    def test_on_load_creates_playbooks(self):
        """Test that on_load creates built-in playbooks."""
        self.plugin.on_load()

        for playbook_name in BUILTIN_PLAYBOOKS:
            playbook_path = self.plugin.executor.playbooks_path / f"{playbook_name}.yml"
            assert playbook_path.exists(), f"Missing playbook: {playbook_name}"


class TestPluginToolHandlers:
    """Test plugin tool handlers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = AnsibleNetworkPlugin()
        self.temp_dir = tempfile.mkdtemp()

        self.plugin._executor = AnsibleExecutor(
            inventory_path=Path(self.temp_dir) / "inventory.yml"
        )
        self.plugin.executor.playbooks_path = Path(self.temp_dir) / "playbooks"
        self.plugin.executor.backups_path = Path(self.temp_dir) / "backups"
        self.plugin.executor.ensure_directories()

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_device_handler(self):
        """Test adding a device."""
        result = self.plugin._handle_add_device({
            "hostname": "switch01",
            "ip_address": "192.168.1.1",
            "device_type": "cisco.ios.ios"
        })

        assert result["success"] is True
        assert len(self.plugin._devices) == 1
        assert self.plugin._devices[0].hostname == "switch01"

    def test_add_duplicate_device(self):
        """Test adding a duplicate device fails."""
        self.plugin._handle_add_device({
            "hostname": "switch01",
            "ip_address": "192.168.1.1",
            "device_type": "cisco.ios.ios"
        })

        result = self.plugin._handle_add_device({
            "hostname": "switch01",
            "ip_address": "192.168.1.2",
            "device_type": "cisco.ios.ios"
        })

        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_list_devices_empty(self):
        """Test listing devices when empty."""
        result = self.plugin._handle_list_devices({})

        assert result["success"] is True
        assert "empty" in result["message"].lower() or "no devices" in result["output"].lower()

    def test_list_devices_with_devices(self):
        """Test listing devices."""
        self.plugin._handle_add_device({
            "hostname": "router01",
            "ip_address": "10.0.0.1",
            "device_type": "cisco.ios.ios"
        })
        self.plugin._handle_add_device({
            "hostname": "switch01",
            "ip_address": "10.0.0.2",
            "device_type": "arista.eos.eos"
        })

        result = self.plugin._handle_list_devices({})

        assert result["success"] is True
        assert "router01" in result["output"]
        assert "switch01" in result["output"]

    def test_list_devices_filter_by_type(self):
        """Test filtering devices by type."""
        self.plugin._handle_add_device({
            "hostname": "cisco01",
            "ip_address": "10.0.0.1",
            "device_type": "cisco.ios.ios"
        })
        self.plugin._handle_add_device({
            "hostname": "arista01",
            "ip_address": "10.0.0.2",
            "device_type": "arista.eos.eos"
        })

        result = self.plugin._handle_list_devices({
            "device_type": "cisco.ios.ios"
        })

        assert result["success"] is True
        assert "cisco01" in result["output"]
        assert "arista01" not in result["output"]

    def test_remove_device_handler(self):
        """Test removing a device."""
        self.plugin._handle_add_device({
            "hostname": "switch01",
            "ip_address": "192.168.1.1",
            "device_type": "cisco.ios.ios"
        })

        result = self.plugin._handle_remove_device({"hostname": "switch01"})

        assert result["success"] is True
        assert len(self.plugin._devices) == 0

    def test_remove_nonexistent_device(self):
        """Test removing a device that doesn't exist."""
        result = self.plugin._handle_remove_device({"hostname": "nonexistent"})

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_list_playbooks_handler(self):
        """Test listing playbooks."""
        self.plugin.on_load()  # Creates built-in playbooks

        result = self.plugin._handle_list_playbooks({})

        assert result["success"] is True
        assert "backup_config" in result["output"]
        assert "check_connectivity" in result["output"]

    def test_show_playbook_handler(self):
        """Test showing playbook contents."""
        self.plugin.on_load()

        result = self.plugin._handle_show_playbook({"playbook": "backup_config"})

        assert result["success"] is True
        assert "Backup" in result["output"]
        assert "hosts:" in result["output"]

    def test_show_nonexistent_playbook(self):
        """Test showing a playbook that doesn't exist."""
        result = self.plugin._handle_show_playbook({"playbook": "nonexistent"})

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestPluginRecipes:
    """Test plugin recipes."""

    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = AnsibleNetworkPlugin()

    def test_network_health_check_recipe(self):
        """Test network health check recipe."""
        recipes = self.plugin.get_recipes()
        recipe = next(r for r in recipes if r.name == "network_health_check")

        assert len(recipe.steps) >= 2
        assert "network health" in " ".join(recipe.trigger_phrases).lower()

        # Check steps use valid tools
        tool_names = [t.name for t in self.plugin.get_tools()]
        for step in recipe.steps:
            assert step.tool_name in tool_names

    def test_network_backup_recipe(self):
        """Test network backup recipe."""
        recipes = self.plugin.get_recipes()
        recipe = next(r for r in recipes if r.name == "network_backup")

        assert len(recipe.steps) >= 1
        assert any("backup" in phrase for phrase in recipe.trigger_phrases)

    def test_recipe_trigger_matching(self):
        """Test that recipes match expected triggers."""
        recipes = self.plugin.get_recipes()

        health_recipe = next(r for r in recipes if r.name == "network_health_check")
        assert health_recipe.matches("check network status")
        assert health_recipe.matches("network health check")

        backup_recipe = next(r for r in recipes if r.name == "network_backup")
        assert backup_recipe.matches("backup network configs")
        assert backup_recipe.matches("backup router configs")


class TestBuiltinPlaybooks:
    """Test built-in playbook definitions."""

    def test_all_playbooks_valid_yaml(self):
        """Test that all built-in playbooks are valid YAML."""
        yaml = pytest.importorskip("yaml", reason="PyYAML not installed")

        for name, content in BUILTIN_PLAYBOOKS.items():
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid YAML in playbook '{name}': {e}")

    def test_playbooks_have_name(self):
        """Test that all playbooks have a name."""
        for name, content in BUILTIN_PLAYBOOKS.items():
            assert "name:" in content, f"Playbook '{name}' missing name"

    def test_playbooks_have_hosts(self):
        """Test that all playbooks define hosts."""
        for name, content in BUILTIN_PLAYBOOKS.items():
            assert "hosts:" in content, f"Playbook '{name}' missing hosts"

    def test_expected_playbooks_exist(self):
        """Test that expected playbooks are defined."""
        expected = [
            "backup_config",
            "check_connectivity",
            "gather_facts",
            "configure_interface",
            "update_firmware"
        ]

        for playbook in expected:
            assert playbook in BUILTIN_PLAYBOOKS, f"Missing playbook: {playbook}"


class TestToolDefinitionQuality:
    """Test tool definition quality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = AnsibleNetworkPlugin()
        self.tools = self.plugin.get_tools()

    def test_all_tools_have_descriptions(self):
        """Test that all tools have descriptions."""
        for tool in self.tools:
            assert tool.description, f"Tool '{tool.name}' missing description"
            assert len(tool.description) > 10, f"Tool '{tool.name}' description too short"

    def test_all_tools_have_schemas(self):
        """Test that all tools have input schemas."""
        for tool in self.tools:
            assert tool.input_schema, f"Tool '{tool.name}' missing input schema"
            assert tool.input_schema.get("type") == "object"

    def test_all_tools_have_handlers(self):
        """Test that all tools have handlers."""
        for tool in self.tools:
            assert callable(tool.handler), f"Tool '{tool.name}' handler not callable"

    def test_dangerous_tools_require_confirmation(self):
        """Test that dangerous tools require confirmation."""
        dangerous_tools = ["ansible_run_playbook", "ansible_adhoc", "ansible_remove_device"]

        for tool in self.tools:
            if tool.name in dangerous_tools:
                assert tool.requires_confirmation, \
                    f"Dangerous tool '{tool.name}' should require confirmation"

    def test_all_tools_have_category(self):
        """Test that all tools have a category."""
        for tool in self.tools:
            assert tool.category == "ansible", \
                f"Tool '{tool.name}' should have category 'ansible'"
