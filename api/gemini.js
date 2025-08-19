// This is a serverless function, designed to run on platforms like Vercel or Netlify.
// It acts as a secure proxy to the Gemini API. This is a comment

// The handler function that receives requests.
export default async function handler(request, response) {
  // Only allow POST requests.
  if (request.method !== 'POST') {
    return response.status(405).json({ error: 'Method Not Allowed' });
  }

  // Get the prompt payload from the request body sent by the dashboard.
  const incomingPayload = request.body;

  if (!incomingPayload || !incomingPayload.contents) {
    return response.status(400).json({ error: 'Invalid request body' });
  }

  // Securely get the Gemini API key from environment variables on the server.
  // This key is NEVER exposed to the frontend.
  const apiKey = process.env.GEMINI_API_KEY;

  if (!apiKey) {
    return response.status(500).json({ error: 'API key not configured on the server.' });
  }

  const apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key=${apiKey}`;

  try {
    // Make the actual call to the Gemini API.
    const geminiResponse = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(incomingPayload),
    });

    if (!geminiResponse.ok) {
      // If the Gemini API returns an error, forward it.
      const errorBody = await geminiResponse.text();
      console.error("Gemini API Error:", errorBody);
      return response.status(geminiResponse.status).json({ error: `Gemini API error: ${errorBody}` });
    }

    // Send the successful response from Gemini back to the dashboard.
    const data = await geminiResponse.json();
    response.status(200).json(data);

  } catch (error) {
    console.error('Error proxying request to Gemini:', error);
    response.status(500).json({ error: 'Failed to fetch from Gemini API.' });
  }
}
