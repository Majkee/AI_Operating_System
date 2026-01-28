# Ansible Network Plugin for AIOS

A comprehensive plugin for managing network devices using Ansible automation.

## Overview

The Ansible Network Plugin extends AIOS with powerful network device management capabilities. It allows you to:

- Manage network device inventory
- Run Ansible playbooks and ad-hoc commands
- Backup device configurations
- Check network health and connectivity
- Gather device facts and status

## Requirements

```bash
# Install Ansible core
pip install ansible-core>=2.15

# Install required collections
ansible-galaxy collection install ansible.netcommon
ansible-galaxy collection install ansible.utils

# For specific vendors (install as needed)
ansible-galaxy collection install cisco.ios
ansible-galaxy collection install cisco.nxos
ansible-galaxy collection install arista.eos
ansible-galaxy collection install junipernetworks.junos
```

## Installation

Copy `ansible_network.py` to your AIOS plugins directory:

```bash
# Linux/Mac
cp ansible_network.py ~/.config/aios/plugins/

# Or system-wide
sudo cp ansible_network.py /etc/aios/plugins/
```

The plugin will be automatically loaded when AIOS starts.

## Tools Reference

### Inventory Management

#### `ansible_add_device`

Add a network device to the inventory.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | Yes | Device hostname (inventory name) |
| `ip_address` | string | Yes | Device IP address or FQDN |
| `device_type` | string | Yes | Network OS type (see supported types) |
| `username` | string | No | SSH username (default: admin) |
| `port` | integer | No | SSH port (default: 22) |
| `groups` | array | No | Groups to add device to |

**Supported Device Types:**
- `cisco.ios.ios` - Cisco IOS
- `cisco.nxos.nxos` - Cisco NX-OS
- `cisco.iosxr.iosxr` - Cisco IOS-XR
- `arista.eos.eos` - Arista EOS
- `junipernetworks.junos.junos` - Juniper Junos
- `vyos.vyos.vyos` - VyOS

**Example:**
```
Add my core switch at 192.168.1.1 as a Cisco IOS device
```

---

#### `ansible_list_devices`

List all devices in the inventory.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `group` | string | No | Filter by group name |
| `device_type` | string | No | Filter by device type |

**Example:**
```
List all my network devices
Show only Cisco switches
```

---

#### `ansible_remove_device`

Remove a device from the inventory. **Requires confirmation.**

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | Yes | Device hostname to remove |

**Example:**
```
Remove switch01 from inventory
```

---

### Playbook Execution

#### `ansible_run_playbook`

Run an Ansible playbook. **Requires confirmation.**

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook` | string | Yes | Playbook name or path |
| `target` | string | No | Host pattern to target |
| `extra_vars` | object | No | Additional variables |
| `check_mode` | boolean | No | Dry run without changes |
| `verbose` | integer | No | Verbosity level (0-4) |

**Example:**
```
Run the backup_config playbook on all switches
Run configure_interface playbook on router01 in check mode
```

---

#### `ansible_adhoc`

Run an ad-hoc Ansible command. **Requires confirmation.**

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `target` | string | Yes | Host pattern to target |
| `module` | string | Yes | Ansible module to run |
| `args` | string | No | Module arguments |
| `become` | boolean | No | Use elevated privileges |

**Example:**
```
Ping all network devices
Run show version on router01
```

---

### Configuration Management

#### `ansible_backup_config`

Backup running configurations from devices.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `target` | string | No | Host pattern (default: all) |
| `backup_path` | string | No | Custom backup location |

**Example:**
```
Backup configs from all network devices
Backup router01 configuration
```

---

#### `ansible_check_connectivity`

Test connectivity to network devices.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `target` | string | No | Host pattern (default: all) |

**Example:**
```
Check if all network devices are reachable
Test connectivity to the switches group
```

---

#### `ansible_gather_facts`

Gather facts and information from devices.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `target` | string | No | Host pattern (default: all) |
| `save_to_file` | boolean | No | Save facts to JSON files |

**Example:**
```
Gather facts from all routers
Get information about switch01 and save it
```

---

### Playbook Management

#### `ansible_list_playbooks`

List all available playbooks.

**Example:**
```
What playbooks are available?
Show me the ansible playbooks
```

---

#### `ansible_show_playbook`

Display contents of a playbook.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook` | string | Yes | Playbook name |

**Example:**
```
Show me the backup_config playbook
What does the configure_interface playbook do?
```

---

## Built-in Playbooks

The plugin includes these ready-to-use playbooks:

### `backup_config.yml`

Backs up running configurations from network devices.

**Variables:**
- `target_hosts` - Host pattern (default: network_devices)
- `backup_path` - Where to save backups

**Output:** Configuration files saved as `{hostname}_{timestamp}.cfg`

---

### `check_connectivity.yml`

Verifies connectivity and retrieves device uptime.

**Variables:**
- `target_hosts` - Host pattern (default: network_devices)

---

### `gather_facts.yml`

Collects comprehensive device information.

**Variables:**
- `target_hosts` - Host pattern (default: network_devices)
- `facts_path` - Where to save facts JSON (optional)

---

### `configure_interface.yml`

Configures network interfaces.

**Variables:**
- `target_hosts` - Host pattern (required)
- `interface_name` - Interface to configure (e.g., GigabitEthernet0/1)
- `interface_description` - Interface description
- `ip_address` - IP address (optional)
- `subnet_mask` - Subnet mask (optional)
- `shutdown` - Set to true to disable interface
- `save_config` - Save after changes (default: true)

---

### `update_firmware.yml`

Stages firmware updates on devices.

**Variables:**
- `target_hosts` - Host pattern (required)
- `firmware_file` - Path to firmware image
- `firmware_dest` - Destination on device (default: flash:)
- `backup_path` - Where to save pre-upgrade config

---

## Recipes

Recipes are pre-built workflows triggered by natural language.

### Network Health Check

**Triggers:** "network health check", "check network status", "are my network devices ok"

**Steps:**
1. Check connectivity to all devices
2. Gather facts from reachable devices
3. Display device list with status

---

### Network Backup

**Triggers:** "backup network configs", "backup router configs", "save network configurations"

**Steps:**
1. Verify device connectivity
2. Backup all running configurations

---

### Add Cisco Switch

**Triggers:** "add cisco switch", "add new switch", "register cisco device"

**Steps:**
1. Add device to inventory
2. Verify connectivity
3. Gather initial facts

**Required context:** hostname, ip_address

---

### Disaster Recovery Prep

**Triggers:** "disaster recovery prep", "dr preparation"

**Steps:**
1. List all devices
2. Backup all configurations
3. Gather and save all facts

---

## File Locations

The plugin stores files in these locations:

```
~/.aios/ansible/
├── inventory.yml      # Device inventory
├── playbooks/         # Playbook files
│   ├── backup_config.yml
│   ├── check_connectivity.yml
│   ├── configure_interface.yml
│   ├── gather_facts.yml
│   └── update_firmware.yml
└── backups/           # Configuration backups
    ├── router01_20260127_120000.cfg
    ├── switch01_20260127_120000.cfg
    └── facts/         # Device facts JSON
        ├── router01_facts.json
        └── switch01_facts.json
```

## Usage Examples

### Setting Up Your Network

```
# Add devices
Add router01 at 10.0.0.1 as a Cisco IOS device
Add switch01 at 10.0.0.10 as an Arista EOS switch with groups datacenter, access

# Verify setup
List all my network devices
Check connectivity to all devices

# Initial backup
Backup configs from all network devices
```

### Daily Operations

```
# Morning health check
Run a network health check

# Check specific device
Gather facts from router01

# Backup before changes
Backup router01 configuration
```

### Making Changes

```
# Dry run first
Run configure_interface on router01 in check mode with interface GigabitEthernet0/1

# Apply changes
Run configure_interface on router01 with interface GigabitEthernet0/1 and description "Uplink to Core"
```

### Troubleshooting

```
# Check device status
Run show version on router01
Run show ip interface brief on all routers

# Check connectivity
Check if switch01 is reachable
Ping all devices in the datacenter group
```

## Security Considerations

1. **Credentials**: Device credentials should be stored securely using Ansible Vault or environment variables
2. **Confirmations**: Dangerous operations (playbook runs, ad-hoc commands, device removal) require user confirmation
3. **Audit Trail**: All operations are logged by AIOS
4. **Backup Before Changes**: Always backup configurations before making changes

## Extending the Plugin

### Adding Custom Playbooks

Place custom playbooks in `~/.aios/ansible/playbooks/`:

```yaml
# ~/.aios/ansible/playbooks/my_playbook.yml
---
- name: My Custom Playbook
  hosts: "{{ target_hosts | default('network_devices') }}"
  gather_facts: no

  tasks:
    - name: Do something
      cli_command:
        command: show version
```

Then use it:
```
Run my_playbook on all switches
```

### Adding Device Variables

Edit the inventory directly or use ansible_add_device with extra variables through the API.

## Troubleshooting

### Plugin Not Loading

1. Check file is in plugins directory
2. Verify Python syntax: `python -m py_compile ansible_network.py`
3. Check AIOS logs for errors

### Ansible Not Found

```bash
pip install ansible-core
```

### Connection Failures

1. Verify device IP and credentials
2. Check SSH connectivity: `ssh admin@device_ip`
3. Ensure correct `device_type` is set
4. Check if required Ansible collection is installed

### Playbook Errors

1. Run with verbose flag: `Run playbook with verbose 3`
2. Check playbook syntax: `ansible-playbook --syntax-check playbook.yml`
3. Test in check mode first

## Contributing

Contributions are welcome! Please:

1. Add tests for new features
2. Follow existing code style
3. Update documentation
4. Test with multiple device types

## License

MIT License - See LICENSE file for details.
