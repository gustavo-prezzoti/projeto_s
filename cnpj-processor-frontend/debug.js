// Simple script to test API endpoints directly
async function testApiEndpoint() {
  try {
    console.log('Testing API endpoint...');
    const response = await fetch('http://212.85.14.78/api/cnpj/consultar');
    
    if (!response.ok) {
      console.error('Error response:', response.status, response.statusText);
      return;
    }
    
    // Try to read as JSON
    try {
      const data = await response.json();
      console.log('JSON Response:', data);
    } catch (jsonError) {
      // If it's not JSON, read as text
      const text = await response.text();
      console.log('Text Response:', text.substring(0, 200) + '...');
    }
  } catch (error) {
    console.error('Fetch error:', error);
  }
}

testApiEndpoint(); 