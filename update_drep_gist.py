import requests
import os
import json
import time

# --- Configuration ---
# Get Gist ID and GitHub Token from environment variables (set by GitHub Actions)
GIST_ID = os.environ.get("DREP_GIST_ID")
GIST_TOKEN = os.environ.get("GIST_UPDATE_TOKEN") # Using your existing secret name
GIST_FILENAME = "drep_directory.json"

# Koios API base URL
API_BASE = "https://api.koios.rest/api/v1"

# Headers for Koios and GitHub API calls
KOIOS_HEADERS = {"Accept": "application/json"}
GITHUB_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"token {GIST_TOKEN}",
}

# --- Helper Functions ---

def koios_paginated_fetch(endpoint):
    """
    Fetches all pages from a paginated Koios endpoint.
    """
    full_list = []
    offset = 0
    limit = 1000
    while True:
        try:
            print(f"Fetching {endpoint} with offset {offset}...")
            url = f"{API_BASE}/{endpoint}?limit={limit}&offset={offset}"
            res = requests.get(url, headers=KOIOS_HEADERS, timeout=30)
            res.raise_for_status()
            batch = res.json()
            if not isinstance(batch, list):
                raise ValueError(f"Unexpected API response from {endpoint}.")
            
            full_list.extend(batch)
            
            if len(batch) < limit:
                break
            offset += limit
            time.sleep(0.2) # Be nice to the API
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {endpoint}: {e}")
            return None
    return full_list

def koios_post_fetch_batched(endpoint, id_list, id_key, batch_size=50):
    """
    Fetches data from a Koios POST endpoint in batches.
    Reduced batch_size to 50 to avoid "Request Entity Too Large" errors.
    """
    full_results = []
    for i in range(0, len(id_list), batch_size):
        batch = id_list[i:i + batch_size]
        payload = {id_key: batch}
        try:
            print(f"Fetching {endpoint}, batch {i//batch_size + 1} of {len(id_list)//batch_size + 1}...")
            res = requests.post(f"{API_BASE}/{endpoint}", json=payload, headers=KOIOS_HEADERS, timeout=30)
            res.raise_for_status()
            full_results.extend(res.json())
            time.sleep(0.2) # Be nice to the API
        except requests.exceptions.RequestException as e:
            print(f"Error fetching batch for {endpoint}: {e}")
            continue
    return full_results

def update_gist(gist_id, filename, content):
    """
    Updates a specific file within a GitHub Gist.
    """
    if not gist_id or not GIST_TOKEN:
        print("DREP_GIST_ID or GIST_UPDATE_TOKEN not set. Skipping Gist update.")
        return False
        
    print(f"Attempting to update Gist {gist_id}...")
    url = f"https://api.github.com/gists/{gist_id}"
    payload = {
        "files": {
            filename: {
                "content": json.dumps(content, indent=2)
            }
        }
    }
    try:
        res = requests.patch(url, headers=GITHUB_HEADERS, json=payload, timeout=30)
        res.raise_for_status()
        print("Gist update successful!")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to update Gist: {e}")
        print(f"Response: {res.text}")
        return False

# --- Main Script ---

def main():
    """
    Main function to fetch all DRep data and update the Gist.
    """
    print("--- Starting DRep Data Fetch ---")

    # 1. Get the full list of all registered DReps
    drep_list = koios_paginated_fetch("drep_list")
    if not drep_list:
        print("Failed to fetch DRep list. Aborting.")
        return
    print(f"Found {len(drep_list)} total DReps.")
    drep_ids = [d["drep_id"] for d in drep_list]

    # 2. Get DRep metadata and voting power in parallel batches
    metadata_list = koios_post_fetch_batched("drep_metadata", drep_ids, "_drep_ids")
    info_list = koios_post_fetch_batched("drep_info", drep_ids, "_drep_ids")

    # 3. Process and combine the data
    print("Processing and combining data...")
    metadata_map = {item["drep_id"]: item.get("meta_json", {}) for item in metadata_list}
    info_map = {item["drep_id"]: item for item in info_list}
    
    final_drep_data = []
    for drep in drep_list:
        drep_id = drep["drep_id"]
        meta = metadata_map.get(drep_id, {})
        info = info_map.get(drep_id, {})
        
        # Extract name from different possible metadata structures
        name = ""
        if meta and meta.get("body"):
            name = meta["body"].get("givenName", "")
        if not name and meta:
            name = meta.get("drepName", "")

        # Extract and convert voting power from lovelace to ADA
        voting_power = int(info.get("amount", 0)) / 1_000_000

        final_drep_data.append({
            "drep_id": drep_id,
            "name": name,
            "voting_power": voting_power
        })

    # 4. Update the GitHub Gist
    update_gist(GIST_ID, GIST_FILENAME, final_drep_data)
    
    print("--- DRep Data Fetch Complete ---")

if __name__ == "__main__":
    main()
