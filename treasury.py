import requests
import json
import os
from decimal import Decimal, getcontext

# Set precision for Decimal calculations
getcontext().prec = 28

# --- Helper Functions ---

def lovelace_to_ada(lovelace):
    """Converts a Lovelace value to ADA."""
    return Decimal(lovelace) / Decimal(1_000_000)

def get_latest_epoch():
    """Fetches the latest epoch number from the Koios API."""
    try:
        tip_url = "https://api.koios.rest/api/v1/tip"
        response = requests.get(tip_url, timeout=10)
        response.raise_for_status()
        return response.json()[0]['epoch_no']
    except Exception as e:
        print(f"Error fetching latest epoch: {e}")
        return None

# --- Data Gathering Functions ---

def get_current_treasury_balance():
    """Fetches the current total balance of the Cardano treasury and returns it."""
    api_url = "https://api.koios.rest/api/v1/totals?order=epoch_no.desc&limit=1"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        lovelace_balance = int(data[0].get('treasury'))
        return lovelace_to_ada(lovelace_balance)
    except Exception as e:
        print(f"An unexpected error occurred while fetching total balance: {e}")
        return None


def get_main_treasury_history(num_epochs=500):
    """
    Tracks the movements of the main Cardano treasury and returns the data as a list.
    """
    latest_epoch = get_latest_epoch()
    if not latest_epoch: return []

    start_epoch = latest_epoch - num_epochs
    history_data = []

    try:
        totals_url = f"https://api.koios.rest/api/v1/totals?epoch_no=gte.{start_epoch}&order=epoch_no.asc"
        totals_response = requests.get(totals_url, timeout=30)
        totals_response.raise_for_status()
        totals_data = {item['epoch_no']: item for item in totals_response.json()}

        for epoch in range(start_epoch + 1, latest_epoch + 1):
            if epoch not in totals_data or (epoch - 1) not in totals_data:
                continue

            treasury_current = Decimal(totals_data[epoch]['treasury'])
            treasury_previous = Decimal(totals_data[epoch - 1]['treasury'])
            net_change = treasury_current - treasury_previous

            inflow_ada = lovelace_to_ada(max(Decimal(0), net_change))
            outflow_ada = lovelace_to_ada(-min(Decimal(0), net_change))
            
            history_data.append({
                "epoch": epoch,
                "inflow_ada": f"{inflow_ada:.2f}",
                "outflow_ada": f"{outflow_ada:.2f}",
                "net_change_ada": f"{lovelace_to_ada(net_change):.2f}",
                "final_balance_ada": f"{lovelace_to_ada(treasury_current):.2f}"
            })
        return history_data
    except Exception as e:
        print(f"An error occurred during treasury history tracking: {e}")
        return []

# --- Gist Update Function ---

def update_gist(gist_id, github_token, filename, content):
    """
    Updates a specific file within a GitHub Gist.
    """
    print(f"Attempting to update Gist file: {filename}")
    api_url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        'Authorization': f'Bearer {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    payload = {
        "files": {
            filename: {
                "content": content
            }
        }
    }
    try:
        response = requests.patch(api_url, headers=headers, data=json.dumps(payload), timeout=20)
        response.raise_for_status()
        print("✅ Gist updated successfully!")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to update Gist: {e}")
        print(f"Response Body: {e.response.text if e.response else 'No response'}")


if __name__ == "__main__":
    # 1. Retrieve secrets from environment variables using your specified names
    TREASURY_GIST_ID = os.environ.get('TREASURY_GIST')
    GIST_UPDATE_TOKEN = os.environ.get('GIST_UPDATE_TOKEN')
    
    if not TREASURY_GIST_ID or not GIST_UPDATE_TOKEN:
        print("❌ Error: TREASURY_GIST and GIST_UPDATE_TOKEN environment variables must be set.")
    else:
        # 2. Fetch the Cardano data
        print("--- Running Cardano Treasury Tracker ---")
        current_balance = get_current_treasury_balance()
        history = get_main_treasury_history(num_epochs=500)
        
        if current_balance is not None and history:
            # 3. Prepare the JSON output
            output_data = {
                "current_balance_ada": f"{current_balance:.2f}",
                "history": history
            }
            
            # Convert the Python dictionary to a JSON formatted string
            json_content = json.dumps(output_data, indent=2)
            
            # 4. Update the Gist
            # The filename comes from your Gist URL
            gist_filename = "treasury.json" 
            update_gist(TREASURY_GIST_ID, GIST_UPDATE_TOKEN, gist_filename, json_content)
        else:
            print("❌ Failed to fetch Cardano data. Gist will not be updated.")

