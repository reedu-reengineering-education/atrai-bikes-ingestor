"""
API Client for OpenSenseMap

This module provides functionality to fetch sensor box metadata and archive data
from the OpenSenseMap API and archive service.
"""

import re
import time
from typing import List, Optional, Dict
import requests
from dataclasses import dataclass
import logging


logger = logging.getLogger(__name__)


@dataclass
class Box:
    """Represents a sensor box with its metadata."""
    id: str
    name: str
    sanitized_name: str
    grouptags: List[str]


class OpenSenseMapClient:
    """Client for interacting with OpenSenseMap API and archive service."""
    
    API_BASE_URL = "https://api.opensensemap.org"
    ARCHIVE_BASE_URL = "https://archive.opensensemap.org"
    
    def __init__(self, max_retries: int = 3, initial_delay: float = 1.0, max_delay: float = 60.0):
        """
        Initialize the OpenSenseMap client.
        
        Args:
            max_retries: Maximum number of retry attempts for failed requests
            initial_delay: Initial delay in seconds for exponential backoff
            max_delay: Maximum delay in seconds for exponential backoff
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.session = requests.Session()
    
    def sanitize_name(self, name: str) -> str:
        """
        Sanitize a box name by replacing invalid characters with underscores.
        
        Args:
            name: The original box name
            
        Returns:
            Sanitized name with only [A-Za-z0-9._-] characters
        """
        return re.sub(r'[^A-Za-z0-9._-]', '_', name)
    
    def _request_with_retry(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """
        Make an HTTP request with retry logic and exponential backoff.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: The URL to request
            **kwargs: Additional arguments to pass to requests
            
        Returns:
            Response object if successful, None if 404 or all retries failed
        """
        delay = self.initial_delay
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                
                # Handle 404 gracefully - missing data is expected
                if response.status_code == 404:
                    return None
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            wait_time = delay
                    else:
                        wait_time = delay
                    
                    time.sleep(min(wait_time, self.max_delay))
                    delay = min(delay * 2, self.max_delay)
                    continue
                
                # Raise for other HTTP errors
                response.raise_for_status()
                
                return response
                
            except requests.exceptions.RequestException as e:
                # Last attempt - don't sleep
                if attempt == self.max_retries - 1:
                    return None
                
                # Sleep with exponential backoff
                time.sleep(min(delay, self.max_delay))
                delay = min(delay * 2, self.max_delay)
        
        return None
    
    def fetch_boxes(self, grouptag: str) -> List[Box]:
        """
        Fetch sensor boxes with the specified grouptag.
        
        Args:
            grouptag: The grouptag to filter boxes by
            
        Returns:
            List of Box objects
            
        Raises:
            Exception: If the API request fails after all retries
        """
        url = f"{self.API_BASE_URL}/boxes"
        params = {"grouptag": grouptag}
        
        response = self._request_with_retry("GET", url, params=params)
        
        if response is None:
            raise Exception(f"Failed to fetch boxes with grouptag '{grouptag}' after {self.max_retries} retries")
        
        boxes_data = response.json()
        boxes = []
        
        for box_data in boxes_data:
            box_id = box_data.get("_id", "")
            box_name = box_data.get("name", "")
            grouptags = box_data.get("grouptag", [])
            
            if box_id and box_name:
                sanitized_name = self.sanitize_name(box_name)
                boxes.append(Box(
                    id=box_id,
                    name=box_name,
                    sanitized_name=sanitized_name,
                    grouptags=grouptags if isinstance(grouptags, list) else []
                ))
        
        return boxes
    
    def fetch_archive_metadata(self, box_id: str, sanitized_name: str, date: str) -> Optional[Dict]:
        """
        Fetch JSON metadata for a box on a specific date.
        
        Args:
            box_id: The box ID
            sanitized_name: The sanitized box name
            date: The date in YYYY-MM-DD format
            
        Returns:
            Dictionary containing metadata, or None if not found
        """
        url = f"{self.ARCHIVE_BASE_URL}/{date}/{box_id}-{sanitized_name}/{sanitized_name}-{date}.json"
        logger.info(f"Fetching metadata from {url}")
        
        response = self._request_with_retry("GET", url)
        
        if response is None:
            return None
        
        try:
            return response.json()
        except ValueError:
            # Invalid JSON
            return None
    
    def fetch_archive_csv(self, box_id: str, sanitized_name: str, date: str, sensor_id: str) -> Optional[str]:
        """
        Fetch CSV data for a specific sensor.
        
        Args:
            box_id: The box ID
            sanitized_name: The sanitized box name
            date: The date in YYYY-MM-DD format
            sensor_id: The sensor ID
            
        Returns:
            CSV content as string, or None if not found
        """
        url = f"{self.ARCHIVE_BASE_URL}/{date}/{box_id}-{sanitized_name}/{sensor_id}-{date}.csv"
        
        response = self._request_with_retry("GET", url)
        
        if response is None:
            return None
        
        return response.text
    
    def close(self):
        """Close the HTTP session."""
        self.session.close()
