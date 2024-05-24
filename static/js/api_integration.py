# api_integration.py
import requests

def fetch_cow_stats(wfo=None, phenomena=None, callback=None):
    """Fetches the Cow statistics from the IEM Cow API based on the provided parameters."""
    base_url = 'https://mesonet.agron.iastate.edu/api/1/cow.json'
    params = {
        'wfo': wfo,
        'phenomena': phenomena,
        'callback': callback
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raises an exception for 4XX/5XX responses
        return response.json()
    except requests.RequestException as e:
        return {'error': str(e)}
