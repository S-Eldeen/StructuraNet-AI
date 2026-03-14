import json
import requests
import sys

# GNS3 local server settings (Default is localhost:3080)
GNS3_SERVER_URL = "http://localhost:3080/v2"


def create_gns3_topology(json_file_path):
    # 1. Load the JSON design
    try:
        with open(json_file_path, 'r') as f:
            design = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    project_name = design.get("name", "Imported_JSON_Project")

    # 2. Get the default compute ID (Fixes the "vm" vs "local" issue)
    computes_res = requests.get(f"{GNS3_SERVER_URL}/computes")
    if computes_res.status_code != 200:
        print("Failed to connect to GNS3 server. Is it running?")
        sys.exit(1)

    available_computes = computes_res.json()
    default_compute_id = available_computes[0]['compute_id']
    print(f"Using Compute ID: {default_compute_id}")

    # 3. Create the Project in GNS3
    print(f"\nCreating project: '{project_name}'...")
    res = requests.post(f"{GNS3_SERVER_URL}/projects",
                        json={"name": project_name})

    if res.status_code == 409:  # Project already exists
        print("Project name already exists. Fetching existing project...")
        projects = requests.get(f"{GNS3_SERVER_URL}/projects").json()
        project_id = next(p['project_id']
                          for p in projects if p['name'] == project_name)
    elif res.status_code == 201:
        project_id = res.json()['project_id']
    else:
        print(f"Failed to create project: {res.text}")
        sys.exit(1)

    print(f"Project ID: {project_id}\n")

    # 4. Create Drawings (Text labels, IP addresses, shapes)
    print("Importing Visual Drawings and Labels...")
    for drawing in design['topology'].get('drawings', []):
        drawing_payload = {
            "x": drawing['x'],
            "y": drawing['y'],
            "z": drawing['z'],
            "svg": drawing['svg'],
            "rotation": drawing.get('rotation', 0)
        }
        requests.post(
            f"{GNS3_SERVER_URL}/projects/{project_id}/drawings", json=drawing_payload)
    print("  - Drawings imported.\n")

    # Dictionary to map old JSON node IDs to the new ones
    node_id_mapping = {}

    # 5. Create Nodes
    print("Creating Nodes (Routers, Switches, PCs)...")
    for node in design['topology']['nodes']:
        old_id = node['node_id']

        node_payload = {
            "name": node['name'],
            "node_type": node['node_type'],
            "compute_id": default_compute_id,  # Safely use local compute
            "properties": node.get('properties', {})
        }

        if 'x' in node:
            node_payload['x'] = node['x']
        if 'y' in node:
            node_payload['y'] = node['y']

        res = requests.post(
            f"{GNS3_SERVER_URL}/projects/{project_id}/nodes", json=node_payload)

        if res.status_code == 201:
            new_node = res.json()
            new_id = new_node['node_id']
            node_id_mapping[old_id] = new_id
            print(f"  [+] Created node: {node['name']}")
        else:
            print(f"  [-] Failed to create node '{node['name']}': {res.text}")

    # 6. Create Links
    print("\nCreating Network Links...")
    for link in design['topology']['links']:
        link_payload = {"nodes": []}

        skip_link = False
        for n in link['nodes']:
            old_node_id = n['node_id']
            if old_node_id not in node_id_mapping:
                skip_link = True
                break

            link_payload["nodes"].append({
                "node_id": node_id_mapping[old_node_id],
                "adapter_number": n['adapter_number'],
                "port_number": n['port_number']
            })

        if skip_link:
            continue

        res = requests.post(
            f"{GNS3_SERVER_URL}/projects/{project_id}/links", json=link_payload)
        if res.status_code == 201:
            pass  # Link created successfully
        else:
            print(f"  [-] Failed to create a link: {res.text}")

    print("\n✅ Topology successfully imported into GNS3!")
    print("Open your GNS3 Desktop client, and you will see '3 Tier Campus LAN 2'.")


if __name__ == "__main__":
    create_gns3_topology("Test 1.json")
