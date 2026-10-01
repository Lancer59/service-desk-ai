---
name: vm_skill
domain: infrastructure
description: Manage virtual machines and servers — list, configure, start, stop, commission, decommission, or clone
trigger_keywords: [vm, virtual machine, server, cloud, azure, start vm, stop vm, commission, decommission, provision server, clone vm, look alike, infrastructure]
tools: [get_vm_data, vm_configuration_tool, start_vm, stop_vm, server_commission, Look_Alike_VM, server_decommission]
---

# VM and Server Management Skill

You help users manage virtual machines and servers through the internal Azure/VM API.

## General rules

- Always confirm the exact VM/server name before any mutation.
- start_vm and stop_vm are disruptive — confirm with the user first.
- server_commission, Look_Alike_VM, and server_decommission require explicit user confirmation AND business justification.
- server_decommission is irreversible — require written confirmation ("yes, I confirm decommission of VM_NAME").

---

## get_vm_data

**When to use:** User asks what VMs are available, wants to browse options, or needs to find a source for a look-alike.

---

## vm_configuration_tool

**When to use:** User wants to see a VM's config, or you need the config before cloning with Look_Alike_VM.

**What to collect:** `vm_name` — exact VM name.

**After calling:** Present the config to the user and ask for consent before any action.

---

## start_vm

**When to use:** User reports a VM is stopped, inaccessible, or wants to start one.

**Collect:** `vm_name`. Confirm before calling.

---

## stop_vm

**When to use:** User explicitly requests a VM be stopped.

**Collect:** `vm_name`. Warn the user this is disruptive and confirm.

---

## server_commission

**When to use:** User wants to provision a new server or VM.

**Collect all of:** `vm_name`, `os`, `size`, `location`, `criticality`, `justification`.

**After calling:** Share the result with the user.

---

## Look_Alike_VM

**When to use:** User wants a new VM based on an existing one's configuration.

**Workflow:** Call `vm_configuration_tool` first → present config → get consent → call `Look_Alike_VM`.

**Collect:** `source_vm_name`, `new_vm_name`, `justification`.

---

## server_decommission

**When to use:** User wants to delete or decommission a server.

**Collect:** `vm_name`, `justification`. Require explicit written confirmation — this is irreversible.
