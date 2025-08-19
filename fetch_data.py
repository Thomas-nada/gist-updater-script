import asyncio
import aiohttp
import pandas as pd
import json
from datetime import datetime
import os

# --- Configuration ---
API_BASE = "https://api.koios.rest/api/v1"
SPO_DATA_URL = "https://gist.githubusercontent.com/Thomas-nada/7b742a3ca9e42281ae831b3da689c0b5/raw/fcf93ff7fae331a329f2ed69267bdf44e29f021e/governance-report.csv"
DREP_DATA_URL = "https://gist.githubusercontent.com/Thomas-nada/28f6ba461017efcb5ab942964776923e/raw/509ad05637b91d228b2bf0b6e26cd38d9641dd4d/drep_directory.json"
OUTPUT_FILENAME = "governance_data.json"

# Using a proxy to avoid potential CORS or IP blocking issues, similar to the web version
PROXY_URL = "https://corsproxy.io/?"

# Gist configuration - read from environment variables
GOVERNANCE_GIST_ID = os.getenv('GOVERNANCE_GIST_ID')
GIST_TOKEN = os.getenv('GIST_TOKEN')

# --- Helper Functions ---

async def fetch_json(session, url):
    """Asynchronously fetches JSON data from a URL."""
    try:
        async with session.get(f"{PROXY_URL}{url}") as response:
            response.raise_for_status()
            # FIX: Ignore the content type from the proxy server
            return await response.json(content_type=None)
    except aiohttp.ClientError as e:
        print(f"Error fetching {url}: {e}")
        return None

async def fetch_paginated_data(session, endpoint):
    """Fetches all pages from a paginated Koios API endpoint."""
    full_list = []
    offset = 0
    limit = 1000
    while True:
        url = f"{API_BASE}/{endpoint}?limit={limit}&offset={offset}"
        batch = await fetch_json(session, url)
        if not batch:
            break
        full_list.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return full_list

# --- Data Fetching Functions ---

async def fetch_spo_data():
    """Fetches and processes SPO data from the CSV Gist."""
    print("Fetching SPO directory...")
    try:
        df = pd.read_csv(SPO_DATA_URL)
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error fetching SPO data: {e}")
        return []

async def fetch_drep_data(session):
    """Fetches DRep directory data from the JSON Gist."""
    print("Fetching DRep directory...")
    return await fetch_json(session, DREP_DATA_URL) or []

async def fetch_proposals_data(session, all_spos):
    """Fetches and processes all active governance proposals."""
    print("Fetching active governance proposals...")
    active_proposals = [
        p for p in await fetch_paginated_data(session, 'proposal_list')
        if p.get('ratified_epoch') is None and p.get('enacted_epoch') is None and
           p.get('dropped_epoch') is None and p.get('expired_epoch') is None and
           p.get('proposal_type') != 'CommitteeNoConfidence'
    ]
    print(f"Found {len(active_proposals)} active proposals. Fetching details...")

    summary_tasks = [fetch_json(session, f"{API_BASE}/proposal_voting_summary?_proposal_id={p['proposal_id']}") for p in active_proposals]
    vote_tasks = [fetch_json(session, f"{API_BASE}/proposal_votes?_proposal_id={p['proposal_id']}") for p in active_proposals]
    
    summaries_list = await asyncio.gather(*summary_tasks)
    votes_list = await asyncio.gather(*vote_tasks)

    enriched_proposals = []
    for i, p in enumerate(active_proposals):
        summary = summaries_list[i][0] if summaries_list[i] else {}
        votes = votes_list[i] if votes_list[i] else []
        
        spo_votes = [v for v in votes if v.get('voter_role') == 'SPO']
        explicitly_voted_spo_ids = {v['voter_id'] for v in spo_votes}

        spo_vote_power = {'Yes': 0, 'No': 0, 'Abstain': 0}
        spo_vote_count = {'Yes': 0, 'No': 0, 'Abstain': 0}

        for spo in all_spos:
            power = float(spo.get('voting_power_ada', 0) or 0)
            if power == 0:
                continue

            if spo['pool_id'] in explicitly_voted_spo_ids:
                explicit_vote = next(v for v in spo_votes if v['voter_id'] == spo['pool_id'])
                vote_cast = explicit_vote.get('vote')
                if vote_cast in spo_vote_power:
                    spo_vote_power[vote_cast] += power
                    spo_vote_count[vote_cast] += 1
            else:
                delegation_status = str(spo.get('vote', '')).lower()
                if 'always abstain' in delegation_status:
                    spo_vote_power['Abstain'] += power
                else:
                    spo_vote_power['No'] += power

        active_voting_power = spo_vote_power['Yes'] + spo_vote_power['No']
        spo_yes_pct = (spo_vote_power['Yes'] / active_voting_power * 100) if active_voting_power > 0 else 0

        enriched_proposals.append({
            **p,
            **summary,
            'type': p.get('proposal_type'),
            'title': p.get('meta_json', {}).get('body', {}).get('title', 'No Title'),
            'abstract': p.get('meta_json', {}).get('body', {}).get('abstract', ''),
            'drep_yes_pct': float(summary.get('drep_yes_pct', 0) or 0),
            'drep_yes_votes_cast': int(summary.get('drep_yes_votes_cast', 0) or 0),
            'drep_no_votes_cast': int(summary.get('drep_no_votes_cast', 0) or 0),
            'drep_abstain_votes_cast': int(summary.get('drep_abstain_votes_cast', 0) or 0),
            'spo_yes_pct': spo_yes_pct,
            'spo_yes_power': spo_vote_power['Yes'],
            'spo_no_power': spo_vote_power['No'],
            'spo_abstain_power': spo_vote_power['Abstain'],
            'spo_yes_votes_cast': spo_vote_count['Yes'],
            'spo_no_votes_cast': spo_vote_count['No'],
            'spo_abstain_votes_cast': spo_vote_count['Abstain'],
            'has_spo_votes': len(spo_votes) > 0
        })
    
    print("Finished processing proposals.")
    return enriched_proposals

# --- Gist Update Function ---

async def update_gist(session, data_to_upload):
    """Updates a GitHub Gist with the provided data."""
    if not GOVERNANCE_GIST_ID or not GIST_TOKEN:
        print("GOVERNANCE_GIST_ID or GIST_TOKEN not set. Skipping Gist update.")
        return

    gist_url = f"https://api.github.com/gists/{GOVERNANCE_GIST_ID}"
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "files": {
            OUTPUT_FILENAME: {
                "content": json.dumps(data_to_upload, indent=2)
            }
        }
    }
    
    print(f"Updating Gist {GOVERNANCE_GIST_ID}...")
    try:
        async with session.patch(gist_url, headers=headers, json=payload) as response:
            response.raise_for_status()
            print("✅ Gist updated successfully.")
    except aiohttp.ClientError as e:
        print(f"❌ Error updating Gist: {e}")

# --- Main Execution ---

async def main():
    """Main function to run all data fetching and updating tasks."""
    async with aiohttp.ClientSession() as session:
        spo_data = await fetch_spo_data()
        drep_data = await fetch_drep_data(session)
        proposal_data = await fetch_proposals_data(session, spo_data)

        final_data = {
            "last_updated_utc": datetime.utcnow().isoformat(),
            "proposals": proposal_data,
            "dreps": drep_data,
            "spos": spo_data
        }

        # Save to a local file (optional, but good for debugging)
        with open(OUTPUT_FILENAME, 'w') as f:
            json.dump(final_data, f, indent=2)
        print(f"Local file '{OUTPUT_FILENAME}' saved.")
        
        # Update the Gist
        await update_gist(session, final_data)


if __name__ == "__main__":
    asyncio.run(main())
