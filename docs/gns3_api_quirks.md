Here's where each property is documented in the GNS3 official docs:

---

## The Short Answer: They're Barely Documented

The controller API (`POST /v2/projects/{id}/nodes`) — which is what the project uses — only documents:

```
properties    object    "Properties specific to an emulator"
```

That's it. One opaque `object`. No sub-fields, no types, no descriptions. The actual config properties are **hidden inside** that object with zero documentation.

---

## Where Each Property Actually Appears

| Property | Controller API Docs | Compute API Docs | Template API Docs | Source Code |
|---|---|---|---|---|
| `startup_config_content` | ❌ Not listed | ✅ Dynamips, IOU | ❌ (uses `startup_config` instead) | ✅ `dynamips_vm.py` |
| `private_config_content` | ❌ Not listed | ✅ Dynamips, IOU | ❌ (uses `private_config` instead) | ✅ `dynamips_vm.py` |
| `startup_script` | ⚠️ Sample only | ✅ VPCS | ❌ (uses `base_script_file` instead) | ✅ `vpcs.py` |
| `environment` | ❌ Not listed | ✅ Docker | ⚠️ In source only | ✅ `docker.py` |
| `start_command` | ❌ Not listed | ✅ Docker | ⚠️ In source only | ✅ `docker.py` |
| `create_config_disk` | ❌ Not listed | ✅ QEMU | ⚠️ In source only | ✅ `qemu.py` |

---

## The Exact URLs

**Dynamips compute** (where `startup_config_content` is documented):
```
https://gns3-server.readthedocs.io/en/latest/api/v2/compute/dynamips_vm/projectsprojectiddynamipsnodes.html
```

**VPCS compute** (where `startup_script` is documented):
```
https://gns3-server.readthedocs.io/en/latest/api/v2/compute/vpcs/projectsprojectidvpcsnodes.html
```

**Docker compute** (where `environment` and `start_command` are documented):
```
https://gns3-server.readthedocs.io/en/latest/api/v2/compute/docker/projectsprojectiddockernodes.html
```

**QEMU compute** (where `create_config_disk` is documented):
```
https://gns3-server.readthedocs.io/en/latest/api/v2/compute/qemu/projectsprojectidqemunodes.html
```

---

## The Naming Mismatch Problem

The docs use **different names** depending on which API level you're looking at:

| What You Want | In Template API | In Compute API | What You Should Use |
|---|---|---|---|
| Cisco IOS config | `startup_config` (filename) | `startup_config_content` (content string) | **`startup_config_content`** |
| Cisco private config | `private_config` (filename) | `private_config_content` (content string) | **`private_config_content`** |
| VPCS commands | `base_script_file` (filename) | `startup_script` (content string) | **`startup_script`** |

The controller (`node.py`) auto-maps these:
```python
mapping = {
    "base_script_file": "startup_script",
    "startup_config": "startup_config_content",
    "private_config": "private_config_content",
}
```

---

## The Real Source of Truth

Since the official docs are incomplete, the **actual authority** is the source code:

```
https://github.com/GNS3/gns3-server/blob/master/gns3server/schemas/
├── dynamips_vm.py    ← startup_config_content, private_config_content
├── vpcs.py           ← startup_script
├── docker.py         ← environment, start_command
├── qemu.py           ← create_config_disk
└── iou.py            ← startup_config_content (same as dynamips)
```

And the controller mapping logic:
```
https://github.com/GNS3/gns3-server/blob/master/gns3server/controller/node.py
```

---

**Bottom line:** The GNS3 API docs are intentionally vague about `properties` — it's a generic `object`. You have to dig into the compute-level API pages or the source code schemas to find what's valid inside it. Your project isn't doing anything wrong — the documentation just doesn't surface this information at the controller level where you're working.