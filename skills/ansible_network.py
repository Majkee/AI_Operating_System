"""
AIOS Ansible Network Skill

A comprehensive skill for managing network devices using Ansible.
Demonstrates all skill system features including tools, recipes,
lifecycle hooks, and best practices.

Features:
- Run Ansible playbooks and ad-hoc commands
- Manage network device inventory
- Backup device configurations
- Check network health and connectivity
- Gather device facts and status

Requirements:
- ansible-core >= 2.15
- ansible.netcommon collection
- ansible.utils collection
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from aios.skills import (
    SkillBase,
    SkillMetadata,
    ToolDefinition,
    Recipe,
    RecipeStep,
)


# =============================================================================
# Configuration and Data Classes
# =============================================================================

@dataclass
class NetworkDevice:
    """Represents a network device in the inventory."""
    hostname: str
    ip_address: str
    device_type: str  # cisco_ios, juniper_junos, arista_eos, etc.
    username: str = "admin"
    port: int = 22
    groups: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)

    def to_inventory_entry(self) -> Dict[str, Any]:
        """Convert to Ansible inventory format."""
        return {
            "ansible_host": self.ip_address,
            "ansible_network_os": self.device_type,
            "ansible_user": self.username,
            "ansible_port": self.port,
            "ansible_connection": "network_cli",
            **self.variables
        }


@dataclass
class PlaybookResult:
    """Result of an Ansible playbook execution."""
    success: bool
    changed: int = 0
    failed: int = 0
    skipped: int = 0
    unreachable: int = 0
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0


# =============================================================================
# Ansible Helper Functions
# =============================================================================

class AnsibleExecutor:
    """Handles Ansible command execution."""

    def __init__(self, inventory_path: Optional[Path] = None):
        self.inventory_path = inventory_path or Path.home() / ".aios" / "ansible" / "inventory.yml"
        self.playbooks_path = Path.home() / ".aios" / "ansible" / "playbooks"
        self.backups_path = Path.home() / ".aios" / "ansible" / "backups"

    def ensure_directories(self) -> None:
        """Create necessary directories."""
        self.inventory_path.parent.mkdir(parents=True, exist_ok=True)
        self.playbooks_path.mkdir(parents=True, exist_ok=True)
        self.backups_path.mkdir(parents=True, exist_ok=True)

    def run_playbook(
        self,
        playbook: str,
        limit: Optional[str] = None,
        extra_vars: Optional[Dict[str, Any]] = None,
        check_mode: bool = False,
        verbose: int = 0
    ) -> PlaybookResult:
        """Execute an Ansible playbook."""
        cmd = [
            "ansible-playbook",
            playbook,
            "-i", str(self.inventory_path),
        ]

        if limit:
            cmd.extend(["--limit", limit])

        if extra_vars:
            cmd.extend(["-e", json.dumps(extra_vars)])

        if check_mode:
            cmd.append("--check")

        if verbose > 0:
            cmd.append("-" + "v" * min(verbose, 4))

        start_time = datetime.now()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            duration = (datetime.now() - start_time).total_seconds()

            # Parse output for statistics
            stats = self._parse_play_recap(result.stdout)

            return PlaybookResult(
                success=result.returncode == 0,
                changed=stats.get("changed", 0),
                failed=stats.get("failed", 0),
                skipped=stats.get("skipped", 0),
                unreachable=stats.get("unreachable", 0),
                output=result.stdout,
                error=result.stderr,
                duration_seconds=duration
            )

        except subprocess.TimeoutExpired:
            return PlaybookResult(
                success=False,
                error="Playbook execution timed out after 5 minutes",
                duration_seconds=300
            )
        except FileNotFoundError:
            return PlaybookResult(
                success=False,
                error="Ansible not found. Install with: pip install ansible-core"
            )
        except Exception as e:
            return PlaybookResult(
                success=False,
                error=str(e)
            )

    def run_adhoc(
        self,
        pattern: str,
        module: str,
        args: Optional[str] = None,
        become: bool = False
    ) -> Dict[str, Any]:
        """Run an ad-hoc Ansible command."""
        cmd = [
            "ansible",
            pattern,
            "-i", str(self.inventory_path),
            "-m", module,
        ]

        if args:
            cmd.extend(["-a", args])

        if become:
            cmd.append("--become")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except FileNotFoundError:
            return {"success": False, "error": "Ansible not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_play_recap(self, output: str) -> Dict[str, int]:
        """Parse Ansible play recap for statistics."""
        stats = {"changed": 0, "failed": 0, "skipped": 0, "unreachable": 0}

        for line in output.split("\n"):
            if "changed=" in line:
                for key in stats:
                    if f"{key}=" in line:
                        try:
                            # Extract number after key=
                            start = line.index(f"{key}=") + len(key) + 1
                            end = start
                            while end < len(line) and line[end].isdigit():
                                end += 1
                            stats[key] += int(line[start:end])
                        except (ValueError, IndexError):
                            pass

        return stats

    def generate_inventory(self, devices: List[NetworkDevice]) -> str:
        """Generate Ansible inventory YAML from device list."""
        inventory = {
            "all": {
                "children": {
                    "network_devices": {
                        "hosts": {},
                        "children": {}
                    }
                }
            }
        }

        # Group devices by type
        device_groups: Dict[str, List[NetworkDevice]] = {}
        for device in devices:
            if device.device_type not in device_groups:
                device_groups[device.device_type] = []
            device_groups[device.device_type].append(device)

        # Add devices to inventory
        for device in devices:
            inventory["all"]["children"]["network_devices"]["hosts"][device.hostname] = \
                device.to_inventory_entry()

        # Create groups by device type
        for group_name, group_devices in device_groups.items():
            safe_name = group_name.replace(".", "_").replace("-", "_")
            inventory["all"]["children"]["network_devices"]["children"][safe_name] = {
                "hosts": {d.hostname: None for d in group_devices}
            }

        # Convert to YAML (simple implementation)
        return self._dict_to_yaml(inventory)

    def _dict_to_yaml(self, data: Any, indent: int = 0) -> str:
        """Simple dictionary to YAML converter."""
        lines = []
        prefix = "  " * indent

        if isinstance(data, dict):
            for key, value in data.items():
                if value is None:
                    lines.append(f"{prefix}{key}:")
                elif isinstance(value, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.append(self._dict_to_yaml(value, indent + 1))
                else:
                    lines.append(f"{prefix}{key}: {value}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    lines.append(self._dict_to_yaml(item, indent + 1))
                else:
                    lines.append(f"{prefix}- {item}")

        return "\n".join(lines)


# =============================================================================
# Built-in Playbooks
# =============================================================================

BUILTIN_PLAYBOOKS = {
    "backup_config": """---
# Backup network device configurations
- name: Backup Network Device Configurations
  hosts: "{{ target_hosts | default('network_devices') }}"
  gather_facts: no

  tasks:
    - name: Get current date for backup filename
      set_fact:
        backup_date: "{{ lookup('pipe', 'date +%Y%m%d_%H%M%S') }}"

    - name: Backup running configuration
      cli_command:
        command: show running-config
      register: config_output

    - name: Save configuration to file
      copy:
        content: "{{ config_output.stdout }}"
        dest: "{{ backup_path }}/{{ inventory_hostname }}_{{ backup_date }}.cfg"
      delegate_to: localhost
""",

    "check_connectivity": """---
# Check network device connectivity
- name: Check Network Device Connectivity
  hosts: "{{ target_hosts | default('network_devices') }}"
  gather_facts: no

  tasks:
    - name: Ping device
      wait_for_connection:
        timeout: 30

    - name: Get device uptime
      cli_command:
        command: show version
      register: version_output

    - name: Display connectivity status
      debug:
        msg: "Device {{ inventory_hostname }} is reachable"
""",

    "gather_facts": """---
# Gather network device facts
- name: Gather Network Device Facts
  hosts: "{{ target_hosts | default('network_devices') }}"
  gather_facts: yes

  tasks:
    - name: Display gathered facts
      debug:
        var: ansible_facts

    - name: Save facts to file
      copy:
        content: "{{ ansible_facts | to_nice_json }}"
        dest: "{{ facts_path }}/{{ inventory_hostname }}_facts.json"
      delegate_to: localhost
      when: facts_path is defined
""",

    "configure_interface": """---
# Configure network interface
- name: Configure Network Interface
  hosts: "{{ target_hosts }}"
  gather_facts: no

  tasks:
    - name: Configure interface
      cli_config:
        config: |
          interface {{ interface_name }}
            description {{ interface_description | default('Configured by AIOS') }}
            {% if ip_address is defined %}
            ip address {{ ip_address }} {{ subnet_mask }}
            {% endif %}
            {% if shutdown is defined and shutdown %}
            shutdown
            {% else %}
            no shutdown
            {% endif %}
      register: config_result

    - name: Save configuration
      cli_command:
        command: write memory
      when: save_config | default(true)
""",

    "update_firmware": """---
# Update network device firmware
- name: Update Network Device Firmware
  hosts: "{{ target_hosts }}"
  gather_facts: yes

  tasks:
    - name: Check current firmware version
      debug:
        msg: "Current version: {{ ansible_net_version | default('unknown') }}"

    - name: Backup current configuration
      cli_command:
        command: show running-config
      register: pre_upgrade_config

    - name: Save pre-upgrade config
      copy:
        content: "{{ pre_upgrade_config.stdout }}"
        dest: "{{ backup_path }}/{{ inventory_hostname }}_pre_upgrade.cfg"
      delegate_to: localhost

    - name: Copy firmware to device
      net_put:
        src: "{{ firmware_file }}"
        dest: "{{ firmware_dest | default('flash:') }}"
      when: firmware_file is defined

    - name: Display upgrade instructions
      debug:
        msg: |
          Firmware staged on device.
          To complete upgrade:
          1. Verify firmware integrity
          2. Set boot variable
          3. Reload device during maintenance window
"""
}


# =============================================================================
# Main Skill Class
# =============================================================================

class AnsibleNetworkSkill(SkillBase):
    """
    AIOS Skill for Ansible Network Device Management.

    This skill provides comprehensive tools for managing network devices
    using Ansible, including playbook execution, ad-hoc commands,
    inventory management, and pre-built workflows.
    """

    def __init__(self):
        self._executor: Optional[AnsibleExecutor] = None
        self._devices: List[NetworkDevice] = []

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="ansible-network",
            version="1.0.0",
            description="Manage network devices with Ansible - run playbooks, "
                       "backup configs, check connectivity, and more",
            author="AIOS Community",
            homepage="https://github.com/anthropics/aios",
            license="MIT",
            dependencies=["ansible-core>=2.15"]
        )

    @property
    def executor(self) -> AnsibleExecutor:
        """Lazy initialization of executor."""
        if self._executor is None:
            self._executor = AnsibleExecutor()
        return self._executor

    # =========================================================================
    # Lifecycle Hooks
    # =========================================================================

    def on_load(self) -> None:
        """Initialize skill resources."""
        self.executor.ensure_directories()

        # Write built-in playbooks
        for name, content in BUILTIN_PLAYBOOKS.items():
            playbook_path = self.executor.playbooks_path / f"{name}.yml"
            if not playbook_path.exists():
                playbook_path.write_text(content)

        # Load existing inventory if present
        if self.executor.inventory_path.exists():
            # In production, parse YAML inventory here
            pass

    def on_unload(self) -> None:
        """Clean up skill resources."""
        # Save any unsaved inventory changes
        if self._devices:
            inventory_content = self.executor.generate_inventory(self._devices)
            self.executor.inventory_path.write_text(inventory_content)

    def on_session_start(self) -> None:
        """Called when user starts an AIOS session."""
        # Could check Ansible connectivity here
        pass

    def on_session_end(self) -> None:
        """Called when user ends an AIOS session."""
        pass

    # =========================================================================
    # Tool Definitions
    # =========================================================================

    def get_tools(self) -> List[ToolDefinition]:
        return [
            # --- Playbook Execution ---
            ToolDefinition(
                name="ansible_run_playbook",
                description="Run an Ansible playbook against network devices. "
                           "Can target specific hosts or groups.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "playbook": {
                            "type": "string",
                            "description": "Playbook name (e.g., 'backup_config') or full path"
                        },
                        "target": {
                            "type": "string",
                            "description": "Host pattern to target (default: all network devices)"
                        },
                        "extra_vars": {
                            "type": "object",
                            "description": "Additional variables to pass to the playbook"
                        },
                        "check_mode": {
                            "type": "boolean",
                            "description": "Run in check mode (dry run) without making changes"
                        },
                        "verbose": {
                            "type": "integer",
                            "description": "Verbosity level (0-4)",
                            "minimum": 0,
                            "maximum": 4
                        }
                    },
                    "required": ["playbook"]
                },
                handler=self._handle_run_playbook,
                requires_confirmation=True,
                category="ansible"
            ),

            # --- Ad-hoc Commands ---
            ToolDefinition(
                name="ansible_adhoc",
                description="Run an ad-hoc Ansible command on network devices. "
                           "Useful for quick one-off operations.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Host pattern to target"
                        },
                        "module": {
                            "type": "string",
                            "description": "Ansible module to run (e.g., 'cli_command', 'ping')"
                        },
                        "args": {
                            "type": "string",
                            "description": "Module arguments"
                        },
                        "become": {
                            "type": "boolean",
                            "description": "Run with elevated privileges"
                        }
                    },
                    "required": ["target", "module"]
                },
                handler=self._handle_adhoc,
                requires_confirmation=True,
                category="ansible"
            ),

            # --- Inventory Management ---
            ToolDefinition(
                name="ansible_add_device",
                description="Add a network device to the Ansible inventory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "hostname": {
                            "type": "string",
                            "description": "Device hostname (used as inventory name)"
                        },
                        "ip_address": {
                            "type": "string",
                            "description": "Device IP address or FQDN"
                        },
                        "device_type": {
                            "type": "string",
                            "description": "Network OS type",
                            "enum": [
                                "cisco.ios.ios",
                                "cisco.nxos.nxos",
                                "cisco.iosxr.iosxr",
                                "arista.eos.eos",
                                "junipernetworks.junos.junos",
                                "vyos.vyos.vyos"
                            ]
                        },
                        "username": {
                            "type": "string",
                            "description": "SSH username (default: admin)"
                        },
                        "port": {
                            "type": "integer",
                            "description": "SSH port (default: 22)"
                        },
                        "groups": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Groups to add the device to"
                        }
                    },
                    "required": ["hostname", "ip_address", "device_type"]
                },
                handler=self._handle_add_device,
                requires_confirmation=False,
                category="ansible"
            ),

            ToolDefinition(
                name="ansible_list_devices",
                description="List all network devices in the Ansible inventory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "group": {
                            "type": "string",
                            "description": "Filter by group name"
                        },
                        "device_type": {
                            "type": "string",
                            "description": "Filter by device type"
                        }
                    }
                },
                handler=self._handle_list_devices,
                requires_confirmation=False,
                category="ansible"
            ),

            ToolDefinition(
                name="ansible_remove_device",
                description="Remove a network device from the inventory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "hostname": {
                            "type": "string",
                            "description": "Device hostname to remove"
                        }
                    },
                    "required": ["hostname"]
                },
                handler=self._handle_remove_device,
                requires_confirmation=True,
                category="ansible"
            ),

            # --- Configuration Backup ---
            ToolDefinition(
                name="ansible_backup_config",
                description="Backup running configuration from network devices",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Host pattern to backup (default: all)"
                        },
                        "backup_path": {
                            "type": "string",
                            "description": "Path to store backups"
                        }
                    }
                },
                handler=self._handle_backup_config,
                requires_confirmation=False,
                category="ansible"
            ),

            # --- Network Health ---
            ToolDefinition(
                name="ansible_check_connectivity",
                description="Check connectivity to network devices",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Host pattern to check (default: all)"
                        }
                    }
                },
                handler=self._handle_check_connectivity,
                requires_confirmation=False,
                category="ansible"
            ),

            # --- Facts Gathering ---
            ToolDefinition(
                name="ansible_gather_facts",
                description="Gather facts and information from network devices",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Host pattern to gather facts from"
                        },
                        "save_to_file": {
                            "type": "boolean",
                            "description": "Save facts to JSON files"
                        }
                    }
                },
                handler=self._handle_gather_facts,
                requires_confirmation=False,
                category="ansible"
            ),

            # --- Playbook Management ---
            ToolDefinition(
                name="ansible_list_playbooks",
                description="List available Ansible playbooks",
                input_schema={
                    "type": "object",
                    "properties": {}
                },
                handler=self._handle_list_playbooks,
                requires_confirmation=False,
                category="ansible"
            ),

            ToolDefinition(
                name="ansible_show_playbook",
                description="Show contents of an Ansible playbook",
                input_schema={
                    "type": "object",
                    "properties": {
                        "playbook": {
                            "type": "string",
                            "description": "Playbook name to display"
                        }
                    },
                    "required": ["playbook"]
                },
                handler=self._handle_show_playbook,
                requires_confirmation=False,
                category="ansible"
            ),
        ]

    # =========================================================================
    # Tool Handlers
    # =========================================================================

    def _handle_run_playbook(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_run_playbook tool."""
        playbook_name = params["playbook"]
        target = params.get("target")
        extra_vars = params.get("extra_vars", {})
        check_mode = params.get("check_mode", False)
        verbose = params.get("verbose", 0)

        # Resolve playbook path
        if not playbook_name.endswith(".yml"):
            playbook_name += ".yml"

        playbook_path = self.executor.playbooks_path / playbook_name
        if not playbook_path.exists():
            # Check if it's a full path
            playbook_path = Path(playbook_name)
            if not playbook_path.exists():
                return {
                    "success": False,
                    "error": f"Playbook not found: {playbook_name}",
                    "message": f"Could not find playbook '{playbook_name}'. "
                              f"Use ansible_list_playbooks to see available playbooks."
                }

        # Add backup path to extra_vars
        extra_vars["backup_path"] = str(self.executor.backups_path)

        result = self.executor.run_playbook(
            playbook=str(playbook_path),
            limit=target,
            extra_vars=extra_vars,
            check_mode=check_mode,
            verbose=verbose
        )

        if result.success:
            return {
                "success": True,
                "output": result.output,
                "message": f"Playbook completed successfully in {result.duration_seconds:.1f}s\n"
                          f"Changed: {result.changed}, Failed: {result.failed}, "
                          f"Skipped: {result.skipped}, Unreachable: {result.unreachable}"
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "output": result.output,
                "message": f"Playbook failed: {result.error}"
            }

    def _handle_adhoc(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_adhoc tool."""
        target = params["target"]
        module = params["module"]
        args = params.get("args")
        become = params.get("become", False)

        result = self.executor.run_adhoc(
            pattern=target,
            module=module,
            args=args,
            become=become
        )

        if result["success"]:
            return {
                "success": True,
                "output": result["output"],
                "message": f"Ad-hoc command completed on '{target}'"
            }
        else:
            return {
                "success": False,
                "error": result["error"],
                "message": f"Ad-hoc command failed: {result['error']}"
            }

    def _handle_add_device(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_add_device tool."""
        # Check for duplicates
        hostname = params["hostname"]
        if any(d.hostname == hostname for d in self._devices):
            return {
                "success": False,
                "error": f"Device '{hostname}' already exists",
                "message": f"Device with hostname '{hostname}' is already in inventory"
            }

        device = NetworkDevice(
            hostname=hostname,
            ip_address=params["ip_address"],
            device_type=params["device_type"],
            username=params.get("username", "admin"),
            port=params.get("port", 22),
            groups=params.get("groups", [])
        )

        self._devices.append(device)

        # Update inventory file
        inventory_content = self.executor.generate_inventory(self._devices)
        self.executor.inventory_path.write_text(inventory_content)

        return {
            "success": True,
            "output": f"Added device: {device.hostname} ({device.ip_address})",
            "message": f"Successfully added {device.hostname} to inventory"
        }

    def _handle_list_devices(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_list_devices tool."""
        group_filter = params.get("group")
        type_filter = params.get("device_type")

        devices = self._devices

        if group_filter:
            devices = [d for d in devices if group_filter in d.groups]

        if type_filter:
            devices = [d for d in devices if d.device_type == type_filter]

        if not devices:
            return {
                "success": True,
                "output": "No devices in inventory",
                "message": "Inventory is empty. Use ansible_add_device to add devices."
            }

        lines = ["Network Devices:", "-" * 60]
        for device in devices:
            groups_str = ", ".join(device.groups) if device.groups else "none"
            lines.append(
                f"  {device.hostname:<20} {device.ip_address:<15} "
                f"{device.device_type:<25} groups: {groups_str}"
            )

        output = "\n".join(lines)

        return {
            "success": True,
            "output": output,
            "message": f"Found {len(devices)} device(s) in inventory"
        }

    def _handle_remove_device(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_remove_device tool."""
        hostname = params["hostname"]

        device = next((d for d in self._devices if d.hostname == hostname), None)
        if not device:
            return {
                "success": False,
                "error": f"Device '{hostname}' not found",
                "message": f"No device with hostname '{hostname}' in inventory"
            }

        self._devices.remove(device)

        # Update inventory file
        inventory_content = self.executor.generate_inventory(self._devices)
        self.executor.inventory_path.write_text(inventory_content)

        return {
            "success": True,
            "output": f"Removed device: {hostname}",
            "message": f"Successfully removed {hostname} from inventory"
        }

    def _handle_backup_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_backup_config tool."""
        target = params.get("target", "network_devices")
        backup_path = params.get("backup_path", str(self.executor.backups_path))

        result = self.executor.run_playbook(
            playbook=str(self.executor.playbooks_path / "backup_config.yml"),
            limit=target,
            extra_vars={
                "target_hosts": target,
                "backup_path": backup_path
            }
        )

        if result.success:
            return {
                "success": True,
                "output": result.output,
                "message": f"Configuration backup completed. "
                          f"Files saved to: {backup_path}"
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "message": f"Backup failed: {result.error}"
            }

    def _handle_check_connectivity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_check_connectivity tool."""
        target = params.get("target", "network_devices")

        result = self.executor.run_playbook(
            playbook=str(self.executor.playbooks_path / "check_connectivity.yml"),
            limit=target,
            extra_vars={"target_hosts": target}
        )

        if result.success:
            reachable = result.changed + (0 if result.failed else 1)
            return {
                "success": True,
                "output": result.output,
                "message": f"Connectivity check completed. "
                          f"Reachable: {reachable}, Unreachable: {result.unreachable}"
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "output": result.output,
                "message": f"Some devices unreachable. Failed: {result.failed}, "
                          f"Unreachable: {result.unreachable}"
            }

    def _handle_gather_facts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_gather_facts tool."""
        target = params.get("target", "network_devices")
        save_to_file = params.get("save_to_file", False)

        extra_vars = {"target_hosts": target}
        if save_to_file:
            facts_path = self.executor.backups_path / "facts"
            facts_path.mkdir(exist_ok=True)
            extra_vars["facts_path"] = str(facts_path)

        result = self.executor.run_playbook(
            playbook=str(self.executor.playbooks_path / "gather_facts.yml"),
            limit=target,
            extra_vars=extra_vars
        )

        if result.success:
            msg = "Facts gathered successfully"
            if save_to_file:
                msg += f". Saved to: {extra_vars['facts_path']}"
            return {
                "success": True,
                "output": result.output,
                "message": msg
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "message": f"Failed to gather facts: {result.error}"
            }

    def _handle_list_playbooks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_list_playbooks tool."""
        playbooks = list(self.executor.playbooks_path.glob("*.yml"))

        if not playbooks:
            return {
                "success": True,
                "output": "No playbooks found",
                "message": "No playbooks in the playbooks directory"
            }

        lines = ["Available Playbooks:", "-" * 40]
        for pb in sorted(playbooks):
            # Get first line of description from playbook
            try:
                content = pb.read_text()
                desc = "No description"
                for line in content.split("\n"):
                    if line.strip().startswith("# "):
                        desc = line.strip()[2:]
                        break
                    elif "name:" in line.lower() and "hosts:" not in line.lower():
                        desc = line.split(":", 1)[1].strip().strip('"\'')
                        break
                lines.append(f"  {pb.stem:<25} - {desc}")
            except Exception:
                lines.append(f"  {pb.stem:<25}")

        output = "\n".join(lines)

        return {
            "success": True,
            "output": output,
            "message": f"Found {len(playbooks)} playbook(s)"
        }

    def _handle_show_playbook(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ansible_show_playbook tool."""
        playbook_name = params["playbook"]

        if not playbook_name.endswith(".yml"):
            playbook_name += ".yml"

        playbook_path = self.executor.playbooks_path / playbook_name

        if not playbook_path.exists():
            return {
                "success": False,
                "error": f"Playbook not found: {playbook_name}",
                "message": f"Could not find playbook '{playbook_name}'"
            }

        content = playbook_path.read_text()

        return {
            "success": True,
            "output": content,
            "message": f"Contents of {playbook_name}"
        }

    # =========================================================================
    # Recipe Definitions
    # =========================================================================

    def get_recipes(self) -> List[Recipe]:
        return [
            Recipe(
                name="network_health_check",
                description="Comprehensive network health check - tests connectivity, "
                           "gathers facts, and reports device status",
                trigger_phrases=[
                    "network health check",
                    "check network status",
                    "are my network devices ok",
                    "network device status"
                ],
                steps=[
                    RecipeStep(
                        description="Check connectivity to all network devices",
                        tool_name="ansible_check_connectivity",
                        tool_params={"target": "network_devices"}
                    ),
                    RecipeStep(
                        description="Gather facts from reachable devices",
                        tool_name="ansible_gather_facts",
                        tool_params={"target": "network_devices", "save_to_file": True}
                    ),
                    RecipeStep(
                        description="List all devices with current status",
                        tool_name="ansible_list_devices",
                        tool_params={}
                    )
                ],
                category="network",
                author="AIOS Community"
            ),

            Recipe(
                name="network_backup",
                description="Backup configurations from all network devices",
                trigger_phrases=[
                    "backup network configs",
                    "backup router configs",
                    "backup switch configs",
                    "save network configurations"
                ],
                steps=[
                    RecipeStep(
                        description="Check device connectivity first",
                        tool_name="ansible_check_connectivity",
                        tool_params={"target": "network_devices"}
                    ),
                    RecipeStep(
                        description="Backup running configurations",
                        tool_name="ansible_backup_config",
                        tool_params={"target": "network_devices"}
                    )
                ],
                category="network",
                author="AIOS Community"
            ),

            Recipe(
                name="add_cisco_switch",
                description="Interactive workflow to add a new Cisco switch",
                trigger_phrases=[
                    "add cisco switch",
                    "add new switch",
                    "register cisco device"
                ],
                steps=[
                    RecipeStep(
                        description="Add the Cisco switch to inventory",
                        tool_name="ansible_add_device",
                        tool_params={
                            "hostname": "$hostname",
                            "ip_address": "$ip_address",
                            "device_type": "cisco.ios.ios",
                            "groups": ["switches", "cisco"]
                        }
                    ),
                    RecipeStep(
                        description="Verify connectivity to new switch",
                        tool_name="ansible_check_connectivity",
                        tool_params={"target": "$hostname"}
                    ),
                    RecipeStep(
                        description="Gather initial facts from switch",
                        tool_name="ansible_gather_facts",
                        tool_params={"target": "$hostname", "save_to_file": True}
                    )
                ],
                category="network",
                author="AIOS Community"
            ),

            Recipe(
                name="disaster_recovery_prep",
                description="Prepare for disaster recovery - backup all configs and gather facts",
                trigger_phrases=[
                    "disaster recovery prep",
                    "dr preparation",
                    "prepare for disaster recovery"
                ],
                steps=[
                    RecipeStep(
                        description="List all network devices",
                        tool_name="ansible_list_devices",
                        tool_params={}
                    ),
                    RecipeStep(
                        description="Backup all device configurations",
                        tool_name="ansible_backup_config",
                        tool_params={"target": "network_devices"}
                    ),
                    RecipeStep(
                        description="Gather and save all device facts",
                        tool_name="ansible_gather_facts",
                        tool_params={"target": "network_devices", "save_to_file": True}
                    )
                ],
                category="network",
                author="AIOS Community"
            )
        ]


# =============================================================================
# Skill Export
# =============================================================================

# This is the skill class that AIOS will discover and load
__skill__ = AnsibleNetworkSkill
