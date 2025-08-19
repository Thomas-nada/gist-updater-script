// This is a serverless function to fetch all initial data for the dashboard.
// It acts as a backend, avoiding the need for client-side CORS proxies.

const API_BASE = "https://api.koios.rest/api/v1";
const SPO_DATA_URL = "https://gist.githubusercontent.com/Thomas-nada/7b742a3ca9e42281ae831b3da689c0b5/raw/fcf93ff7fae331a329f2ed69267bdf44e29f021e/governance-report.csv";
const DREP_DATA_URL = "https://gist.githubusercontent.com/Thomas-nada/28f6ba461017efcb5ab942964776923e/raw/509ad05637b91d228b2bf0b6e26cd38d9641dd4d/drep_directory.json";

// Helper to fetch from a URL and return JSON
async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
    }
    return response.json();
}

// Helper to fetch from a URL and return text (for CSV)
async function fetchText(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
    }
    return response.text();
}


// The main handler for the serverless function
export default async function handler(request, response) {
    // Set CORS headers to allow requests from any origin
    response.setHeader('Access-Control-Allow-Origin', '*');
    response.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    response.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (request.method === 'OPTIONS') {
        return response.status(200).end();
    }

    try {
        // Fetch all data sources in parallel for maximum speed
        const [spoDataCsv, drepData, proposalList] = await Promise.all([
            fetchText(SPO_DATA_URL),
            fetchJson(DREP_DATA_URL),
            fetchJson(`${API_BASE}/proposal_list`)
        ]);

        // Send all the fetched data back to the dashboard in a single response
        response.status(200).json({
            spoDataCsv,
            drepData,
            proposalList,
        });

    } catch (error) {
        console.error('Error fetching initial data:', error);
        response.status(500).json({ error: 'Failed to fetch initial data.', details: error.message });
    }
}
