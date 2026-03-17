import logging
from typing import Optional

import requests
from open_webui.retrieval.web.main import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


def search_tavily(
    api_key: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    # **kwargs,
) -> list[SearchResult]:
    """Search using Tavily's Search API and return the results as a list of SearchResult objects.

    Args:
        api_key (str): A Tavily Search API key
        query (str): The query to search for
        count (int): The maximum number of results to return

    Returns:
        list[SearchResult]: A list of search results
    """
    url = "https://api.tavily.com/search"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = {"query": query, "max_results": count}
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    json_response = response.json()

    results = json_response.get("results", [])
    if filter_list:
        results = get_filtered_results(results, filter_list)

    # Tavily may return images at top level
    images = json_response.get("images", [])
    image_map = {}
    for img in images:
        if isinstance(img, dict):
            image_map[img.get("url", "")] = img.get("url", "")
        elif isinstance(img, str):
            image_map[img] = img

    return [
        SearchResult(
            link=result["url"],
            title=result.get("title", ""),
            snippet=result.get("content"),
            published_date=result.get("published_date"),
        )
        for result in results
    ]
