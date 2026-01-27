# AIOS Plugins

This directory contains example plugins for AIOS.

## Available Plugins

### ansible_network.py

A comprehensive plugin for managing network devices using Ansible.

**Features:**
- Run Ansible playbooks and ad-hoc commands
- Manage network device inventory
- Backup device configurations
- Check network health and connectivity
- Gather device facts and status

**Tools Provided:**

| Tool | Description | Requires Confirmation |
|------|-------------|----------------------|
| `ansible_run_playbook` | Run an Ansible playbook | Yes |
| `ansible_adhoc` | Run ad-hoc Ansible commands | Yes |
| `ansible_add_device` | Add device to inventory | No |
| `ansible_list_devices` | List all network devices | No |
| `ansible_remove_device` | Remove device from inventory | Yes |
| `ansible_backup_config` | Backup device configurations | No |
| `ansible_check_connectivity` | Check device connectivity | No |
| `ansible_gather_facts` | Gather device facts | No |
| `ansible_list_playbooks` | List available playbooks | No |
| `ansible_show_playbook` | Show playbook contents | No |

**Recipes Provided:**

| Recipe | Trigger Phrases |
|--------|-----------------|
| `network_health_check` | "network health check", "check network status" |
| `network_backup` | "backup network configs", "backup router configs" |
| `add_cisco_switch` | "add cisco switch", "add new switch" |
| `disaster_recovery_prep` | "disaster recovery prep", "dr preparation" |

**Built-in Playbooks:**
- `backup_config.yml` - Backup running configurations
- `check_connectivity.yml` - Verify device connectivity
- `gather_facts.yml` - Collect device information
- `configure_interface.yml` - Configure network interfaces
- `update_firmware.yml` - Stage firmware updates

**Requirements:**
```bash
pip install ansible-core
ansible-galaxy collection install ansible.netcommon
ansible-galaxy collection install cisco.ios
```

## Installing Plugins

Copy plugin files to one of these directories:

```
~/.config/aios/plugins/     # User plugins (Linux/Mac)
%APPDATA%\aios\plugins\     # User plugins (Windows)
/etc/aios/plugins/          # System-wide plugins
```

## Creating Your Own Plugin

See [PLUGINS.md](../PLUGINS.md) for comprehensive documentation on creating plugins.

### Quick Start

```python
from aios.plugins import PluginBase, PluginMetadata, ToolDefinition

class MyPlugin(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            author="Your Name"
        )

    def get_tools(self):
        return [
            ToolDefinition(
                name="my_tool",
                description="Does something useful",
                input_schema={"type": "object", "properties": {}},
                handler=self.handle_my_tool
            )
        ]

    def handle_my_tool(self, params):
        return {
            "success": True,
            "output": "Result here",
            "message": "Operation completed"
        }
```

## Plugin Best Practices

1. **Use descriptive names** - Tool names should clearly indicate their purpose
2. **Validate input** - Don't trust params match your schema; validate in handlers
3. **Handle errors gracefully** - Return error info rather than raising exceptions
4. **Use `requires_confirmation`** - For any operation that modifies state
5. **Document your tools** - Use the `description` field thoroughly
6. **Write tests** - See `tests/test_ansible_plugin.py` for examples
