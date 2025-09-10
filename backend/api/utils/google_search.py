import requests
from django.conf import settings

def google_search(query, num_results=10):
    """Use Google Custom Search API to get links for a query"""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.GOOGLE_API_KEY,
        "cx": settings.GOOGLE_SEARCH_ENGINE_ID,
        "q": query,
        "num": num_results,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    links = [item["link"] for item in data.get("items", [])]
    return links
