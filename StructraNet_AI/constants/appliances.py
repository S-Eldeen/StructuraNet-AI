"""
constants/appliances.py — Static Appliance Catalog Data for StructraNet AI

Defines the mandatory creation properties for every GNS3 appliance type
that StructraNet AI can emit.  These properties are required by the GNS3
server (or by the .gns3project portable-project format) to create a
functional node — without them, GNS3 will reject the node or silently
default to broken values.

Sources: GNS3 server v2.2 source code
  - gns3server/controller/template_manager.py    (built-in template defaults)
  - gns3server/schemas/dynamips_template.py       (Dynamips schema & defaults)
  - gns3server/schemas/iou_template.py            (IOU schema & defaults)
  - gns3server/schemas/vpcs_template.py           (VPCS schema & defaults)
  - gns3server/schemas/ethernet_switch_template.py
  - gns3server/schemas/ethernet_hub_template.py
  - gns3server/schemas/cloud_template.py
  - gns3server/schemas/nat.py
  - gns3server/schemas/frame_relay_switch.py
  - gns3server/schemas/atm_switch.py
  - gns3server/schemas/qemu_template.py           (QEMU schema & defaults)
  - gns3server/schemas/docker_template.py         (Docker schema & defaults)
  - gns3-registry/appliances/*.gns3a              (QEMU/Docker appliance files)
"""

from typing import Any, Dict, List

# ═══════════════════════════════════════════════════════════════════════════════
#  Helper: Default 8-port switch ports_mapping
#  GNS3 creates 8 access ports (VLAN 1) by default on ethernet_switch.
#  Source: gns3server/compute/builtin/nodes/ethernet_switch.py
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_SWITCH_PORTS: List[Dict[str, Any]] = [
    {"name": f"Ethernet{i}", "port_number": i, "type": "access", "vlan": 1, "ethertype": ""}
    for i in range(8)
]

# ═══════════════════════════════════════════════════════════════════════════════
#  Helper: Default 8-port hub ports_mapping
#  Source: gns3server/compute/builtin/nodes/ethernet_hub.py
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_HUB_PORTS: List[Dict[str, Any]] = [
    {"name": f"Ethernet{i}", "port_number": i}
    for i in range(8)
]


APPLIANCE_CATALOG: Dict[str, Dict[str, Any]] = {

    # ═══════════════════════════════════════════════════════════════════════════
    #  DYNAMIPS  (source: gns3server/schemas/dynamips_template.py)
    # ═══════════════════════════════════════════════════════════════════════════

    "Cisco 7200": {
        "node_type":         "dynamips",
        "platform":          "c7200",
        "image":             "c7200-adventerprisek9-mz.124-24.T5.image",
        "ram":               512,          # GNS3 default for c7200
        "nvram":             512,          # GNS3 default for c7200
        "slot0":             "C7200-IO-FE",
        "console_type":      "telnet",
        "port_name_format":  "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },

    "Cisco 3745": {
        "node_type":         "dynamips",
        "platform":          "c3745",
        "image":             "c3745-adventerprisek9-mz.124-25d.image",
        "ram":               128,          # GNS3 default for c3745
        "nvram":             256,          # GNS3 default for c3745
        "slot0":             "GT96100-FE",
        "console_type":      "telnet",
        "port_name_format":  "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },

    "Cisco 3725": {
        "node_type":         "dynamips",
        "platform":          "c3725",
        "image":             "c3725-adventerprisek9-mz.124-25d.image",
        "ram":               128,          # GNS3 default for c3725
        "nvram":             256,          # GNS3 default for c3725
        "slot0":             "GT96100-FE",
        "console_type":      "telnet",
        "port_name_format":  "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },

    "Cisco 3660": {
        "node_type":         "dynamips",
        "platform":          "c3600",      # GNS3 uses "c3600" for all 36xx
        "chassis":           "3660",       # Distinguishes from 3620/3640
        "image":             "c3660-a3jk9s-mz.124-25d.image",
        "ram":               192,          # GNS3 default for c3600 platform
        "nvram":             256,
        "slot0":             "Leopard-2FE",
        "console_type":      "telnet",
        "port_name_format":  "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },

    "Cisco 3640": {
        "node_type":         "dynamips",
        "platform":          "c3600",
        "chassis":           "3640",
        "image":             "c3640-a3js-mz.124-25d.image",
        "ram":               128,          # GNS3 default for c3640
        "nvram":             256,
        # No slot0 — slot 0 is user-configurable on c3640/c3620
        "console_type":      "telnet",
        "port_name_format":  "Ethernet{0}/{1}",
        "port_segment_size": 1,
    },

    "Cisco 2691": {
        "node_type":         "dynamips",
        "platform":          "c2691",
        "image":             "c2691-adventerprisek9-mz.124-25d.image",
        "ram":               192,          # GNS3 default for c2691
        "nvram":             256,
        "slot0":             "GT96100-FE",
        "console_type":      "telnet",
        "port_name_format":  "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },

    "Cisco 2600": {
        "node_type":         "dynamips",
        "platform":          "c2600",
        "chassis":           "2600",
        "image":             "c2600-adventerprisek9-mz.124-25d.image",
        "ram":               160,          # GNS3 default for c2600
        "nvram":             128,
        "slot0":             "C2600-MB-1FE-TX",  # Corrected from NM-1FE-TX
        "console_type":      "telnet",
        "port_name_format":  "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },

    "Cisco 1700": {
        "node_type":         "dynamips",
        "platform":          "c1700",
        "chassis":           "1721",       # Most common 1700 chassis
        "image":             "c1700-adventerprisek9-mz.124-25d.image",
        "ram":               160,          # GNS3 default for c1700
        "nvram":             128,
        "slot0":             "C1700-MB-1FE-TX",  # Corrected from C1700-MB-1ETH
        "console_type":      "telnet",
        "port_name_format":  "FastEthernet{0}",
        "port_segment_size": 1,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  IOU  (source: gns3server/schemas/iou_template.py)
    # ═══════════════════════════════════════════════════════════════════════════

    "IOU L3": {
        "node_type":         "iou",
        "path":              "/opt/gns3/images/i86bi-linux-l3-adventerprisek9-15.5.2T.bin",
        "ram":               256,          # GNS3 default
        "nvram":             128,          # GNS3 default
        "ethernet_adapters": 2,
        "serial_adapters":   0,
        "console_type":      "telnet",
        "port_name_format":  "Ethernet{0}/{1}",
        "port_segment_size": 4,            # IOU segments = 4 interfaces each
    },

    "IOU L2": {
        "node_type":         "iou",
        "path":              "/opt/gns3/images/i86bi-linux-l2-adventerprisek9-15.2d.bin",
        "ram":               256,
        "nvram":             128,
        "ethernet_adapters": 1,
        "serial_adapters":   0,
        "console_type":      "telnet",
        "port_name_format":  "Ethernet{0}/{1}",
        "port_segment_size": 4,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  BUILT-IN: VPCS
    #  Source: gns3server/schemas/vpcs_template.py
    # ═══════════════════════════════════════════════════════════════════════════

    "VPCS": {
        "node_type":         "vpcs",
        "console_type":      "telnet",
        "port_name_format":  "Ethernet{0}",
        "port_segment_size": 1,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  BUILT-IN: Ethernet Switch
    #  Source: gns3server/schemas/ethernet_switch_template.py
    #         gns3server/compute/builtin/nodes/ethernet_switch.py
    #  GNS3 creates 8 access ports (VLAN 1) by default.
    #  port type enum: "access", "dot1q", "qinq"
    #  ethertype enum: "", "0x8100", "0x88A8", "0x9100", "0x9200"
    # ═══════════════════════════════════════════════════════════════════════════

    "Ethernet Switch": {
        "node_type":         "ethernet_switch",
        "console_type":      "none",       # GNS3 default — no console on switches
        "ports_mapping":     _DEFAULT_SWITCH_PORTS,
        "port_name_format":  "Ethernet{0}",
        "port_segment_size": 1,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  BUILT-IN: Ethernet Hub
    #  Source: gns3server/schemas/ethernet_hub_template.py
    #         gns3server/compute/builtin/nodes/ethernet_hub.py
    #  No console_type — hubs have no console at all.
    # ═══════════════════════════════════════════════════════════════════════════

    "Ethernet Hub": {
        "node_type":         "ethernet_hub",
        "ports_mapping":     _DEFAULT_HUB_PORTS,
        "port_name_format":  "Ethernet{0}",
        "port_segment_size": 1,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  BUILT-IN: Cloud
    #  Source: gns3server/schemas/cloud_template.py
    #         gns3server/compute/builtin/nodes/cloud.py
    #  ports_mapping is empty — GNS3 auto-populates from host interfaces
    #  at node creation time.  No console_type.
    # ═══════════════════════════════════════════════════════════════════════════

    "Cloud": {
        "node_type":         "cloud",
        "ports_mapping":     [],            # Populated at runtime from host NICs
        "port_name_format":  "Ethernet{0}",
        "port_segment_size": 1,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  BUILT-IN: NAT
    #  Source: gns3server/schemas/nat.py
    #         gns3server/compute/builtin/nodes/nat.py
    #  NAT extends Cloud.  Auto-creates one port (nat0) linked to host's
    #  NAT interface: virbr0 (Linux) or vmnet8 (macOS/Windows).
    #  ports_mapping is read-only on NAT — the setter is a no-op.
    #  No console_type.
    # ═══════════════════════════════════════════════════════════════════════════

    "NAT": {
        "node_type":         "nat",
        "ports_mapping":     [],            # Auto-populated: nat0 → virbr0/vmnet8
        "port_name_format":  "nat{0}",
        "port_segment_size": 1,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  BUILT-IN: Frame Relay Switch
    #  Source: gns3server/schemas/frame_relay_switch.py
    #  mappings format: {"port:dlci": "port:dlci", ...}
    #  e.g. {"1:101": "2:202", "1:102": "2:202"}
    #  No console_type.
    # ═══════════════════════════════════════════════════════════════════════════

    "Frame Relay Switch": {
        "node_type":         "frame_relay_switch",
        "mappings":          {},
        "port_name_format":  "Serial{0}",
        "port_segment_size": 1,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  BUILT-IN: ATM Switch
    #  Source: gns3server/schemas/atm_switch.py
    #  mappings format: {"port:vpi:vci": "port:vpi:vci", ...}
    #  No console_type.
    # ═══════════════════════════════════════════════════════════════════════════

    "ATM Switch": {
        "node_type":         "atm_switch",
        "mappings":          {},
        "port_name_format":  "ATM{0}",
        "port_segment_size": 1,
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  QEMU  (source: gns3server/schemas/qemu_template.py)
    #  Schema defaults: ram=256, adapters=1, adapter_type="e1000",
    #                   console_type="telnet", linked_clone=true
    # ═══════════════════════════════════════════════════════════════════════════

    "Cisco CSR1000v": {
        # Source: gns3-registry/appliances/cisco-csr1000v.gns3a
        "node_type":             "qemu",
        "hda_disk_image":        "csr1000v-universalk9-serial.qcow2",
        "hda_disk_interface":    "ide",
        "ram":                   4096,
        "cpus":                  1,
        "adapters":              4,
        "adapter_type":          "vmxnet3",
        "console_type":          "telnet",
        "port_name_format":      "Gi{port1}",
        "port_segment_size":     0,
        "linked_clone":          True,
        "boot_priority":         "c",
        "kvm":                   "require",
    },

    "pfSense": {
        # Source: gns3-registry/appliances/pfsense.gns3a
        "node_type":             "qemu",
        "hda_disk_image":        "pfSense-CE-2.7.2-RELEASE-amd64.qcow2",
        "hda_disk_interface":    "virtio",
        "ram":                   2048,
        "cpus":                  1,
        "adapters":              6,
        "adapter_type":          "e1000",
        "console_type":          "vnc",
        "port_name_format":      "em{0}",
        "port_segment_size":     0,
        "linked_clone":          True,
        "boot_priority":         "c",
        "kvm":                   "allow",
    },

    "Alpine Linux": {
        # Source: gns3-registry/appliances/alpine-linux-virt.gns3a
        "node_type":             "qemu",
        "hda_disk_image":        "alpine-virt-3.19.qcow2",
        "hda_disk_interface":    "virtio",
        "ram":                   128,
        "cpus":                  1,
        "adapters":              1,
        "adapter_type":          "virtio-net-pci",
        "console_type":          "telnet",
        "port_name_format":      "eth{0}",
        "port_segment_size":     0,
        "linked_clone":          True,
        "kvm":                   "allow",
    },

    "OpenWrt": {
        # Source: gns3-registry/appliances/openwrt.gns3a
        "node_type":             "qemu",
        "hda_disk_image":        "openwrt-x86-64-generic-ext4-combined.img",
        "hda_disk_interface":    "ide",
        "ram":                   128,
        "cpus":                  1,
        "adapters":              4,
        "adapter_type":          "virtio-net-pci",
        "console_type":          "telnet",
        "port_name_format":      "Ethernet{0}",
        "port_segment_size":     0,
        "linked_clone":          True,
        "kvm":                   "allow",
    },

    "FRRouting": {
        # Source: gns3-registry/appliances/frr.gns3a
        "node_type":             "qemu",
        "hda_disk_image":        "frr-8.2.2.qcow2",
        "hda_disk_interface":    "ide",
        "ram":                   256,
        "cpus":                  1,
        "adapters":              8,
        "adapter_type":          "e1000",
        "console_type":          "telnet",
        "port_name_format":      "eth{0}",
        "port_segment_size":     0,
        "linked_clone":          True,
        "kvm":                   "allow",
        "usage":                 "Credentials: root / root\nvtysh to access the router CLI",
    },

    "OVS": {
        # Open vSwitch — common QEMU-based appliance
        "node_type":             "qemu",
        "hda_disk_image":        "openvswitch.qcow2",
        "hda_disk_interface":    "virtio",
        "ram":                   256,
        "cpus":                  1,
        "adapters":              8,
        "adapter_type":          "e1000",
        "console_type":          "telnet",
        "port_name_format":      "eth{0}",
        "port_segment_size":     0,
        "linked_clone":          True,
        "kvm":                   "allow",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    #  DOCKER  (source: gns3server/schemas/docker_template.py)
    #  Schema defaults: adapters=1, console_type="telnet"
    #  image is REQUIRED — no default.
    # ═══════════════════════════════════════════════════════════════════════════

    "Alpine Docker": {
        "node_type":         "docker",
        "image":             "alpine:latest",
        "adapters":          1,
        "console_type":      "telnet",
        "port_name_format":  "eth{0}",
        "port_segment_size": 0,
        "start_command":     "",
        "environment":       "",
    },

    "FRR Docker": {
        "node_type":         "docker",
        "image":             "frrouting/frr:latest",
        "adapters":          4,
        "console_type":      "telnet",
        "port_name_format":  "eth{0}",
        "port_segment_size": 0,
        "start_command":     "/sbin/init",
        "environment":       "",
    },

    "OVS Docker": {
        "node_type":         "docker",
        "image":             "openvswitch/ovs:latest",
        "adapters":          8,
        "console_type":      "telnet",
        "port_name_format":  "eth{0}",
        "port_segment_size": 0,
        "start_command":     "",
        "environment":       "",
    },
}