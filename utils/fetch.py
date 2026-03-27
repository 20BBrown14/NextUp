import requests
from typing import Optional, Dict, Any

def make_request(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    should_log: bool = True
) -> requests.Response:
    """
    A generic wrapper for the requests library.
    """
    method = method.upper()
    if should_log:
        print({"method": method, "url": url, "params": params, "body": body})
    
    try:
        response = requests.request(
            method=method,
            url=url,
            params=params,
            json=body,
            headers=headers,
            timeout=timeout
        )
        
        response.raise_for_status()
        return response

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the {method} request to {url}: {e}")
        raise