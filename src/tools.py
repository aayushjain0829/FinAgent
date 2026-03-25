import requests
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .config_loader import get_config


# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class NAVData:
    """NAV data for a mutual fund scheme."""
    scheme_code: str
    scheme_name: str
    nav: float
    date: str
    fund_type: str
    fund_house: str


def _make_request_with_retry(url: Optional[str] = None) -> Optional[requests.Response]:
    """Make HTTP request with exponential backoff retry logic using centralized config.
    
    Args:
        url: URL to fetch (defaults to config amfi_nav_url)
        
    Returns:
        Response object or None if all retries fail
    """
    config = get_config()
    
    final_url = url or config.data_sources.amfi_nav_url
    max_retries = config.network.max_retries
    base_delay = config.network.base_delay_seconds
    timeout = config.network.timeout_seconds
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"Fetching {final_url} (attempt {attempt + 1}/{max_retries})")
            response = requests.get(final_url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.Timeout:
            logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries} for {final_url}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
        except requests.RequestException as e:
            logger.warning(f"Request failed on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
    
    logger.error(f"All {max_retries} attempts failed for {final_url}")
    return None


def fetch_nav_data(scheme_code: str) -> Optional[NAVData]:
    """Fetch NAV data for a mutual fund scheme from AMFI India with retry logic.
    
    Args:
        scheme_code: The AMFI scheme code (e.g., "120620" for SBI Flexi Cap)
        
    Returns:
        NAVData object or None if fetch fails after retries
    """
    response = _make_request_with_retry()
    
    if response is None:
        logger.error(f"Failed to fetch NAV data after retries for scheme {scheme_code}")
        return None
    
    try:
        lines = response.text.strip().split("\n")
        current_fund_house = ""
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
                
            parts = line.split(";")
            
            if len(parts) == 1:
                current_fund_house = parts[0]
                continue
                
            if len(parts) >= 6:
                if parts[0].strip() == scheme_code:
                    nav_value = float(parts[4].strip()) if parts[4].strip() else 0.0
                    logger.info(f"Found NAV data for {scheme_code}: {parts[3].strip()} @ {nav_value}")
                    return NAVData(
                        scheme_code=parts[0].strip(),
                        scheme_name=parts[3].strip(),
                        nav=nav_value,
                        date=parts[5].strip(),
                        fund_type="Mutual Fund",
                        fund_house=current_fund_house
                    )
        
        logger.warning(f"Scheme code {scheme_code} not found in NAV data")
        return None
        
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing NAV data for {scheme_code}: {e}")
        return None


def search_scheme_by_name(query: str, limit: int = 10) -> list:
    """Search for AMFI scheme codes by fund name (partial match, case-insensitive) with retry logic.
    
    Args:
        query: Partial or full fund name to search for (e.g., "SBI Flexi Cap")
        limit: Maximum number of results to return (default: 10)
        
    Returns:
        List of dicts with scheme_code, scheme_name, and fund_house for matches
    """
    results = []
    query_lower = query.lower()
    
    response = _make_request_with_retry()
    
    if response is None:
        logger.error(f"Failed to search for '{query}' after retries")
        return results
    
    try:
        lines = response.text.strip().split("\n")
        current_fund_house = ""
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
                
            parts = line.split(";")
            
            if len(parts) == 1:
                current_fund_house = parts[0]
                continue
                
            if len(parts) >= 6:
                scheme_name = parts[3].strip()
                if query_lower in scheme_name.lower():
                    results.append({
                        "scheme_code": parts[0].strip(),
                        "scheme_name": scheme_name,
                        "fund_house": current_fund_house
                    })
                    if len(results) >= limit:
                        break
                        
        logger.info(f"Found {len(results)} match(es) for '{query}'")
                        
    except Exception as e:
        logger.error(f"Error parsing search results for '{query}': {e}")
        
    return results


def resolve_fund_name_to_scheme_code(fund_name: str) -> Optional[str]:
    """Resolve a readable fund name to its AMFI scheme code.
    
    Args:
        fund_name: Human-readable fund name (e.g., "SBI Flexi Cap Fund")
        
    Returns:
        Scheme code if found, None otherwise
    """
    matches = search_scheme_by_name(fund_name, limit=1)
    if matches:
        return matches[0]["scheme_code"]
    return None


def fetch_latest_nav_batch() -> Dict[str, NAVData]:
    """Fetch all latest NAV data from AMFI India with retry logic.
    
    Returns:
        Dictionary mapping scheme codes to NAVData objects
    """
    nav_data = {}
    
    response = _make_request_with_retry()
    
    if response is None:
        logger.error("Failed to fetch NAV batch after retries")
        return nav_data
    
    try:
        lines = response.text.strip().split("\n")
        current_fund_house = ""
        parsed_count = 0
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
                
            parts = line.split(";")
            
            if len(parts) == 1:
                current_fund_house = parts[0]
                continue
                
            if len(parts) >= 6:
                scheme_code = parts[0].strip()
                try:
                    nav = float(parts[4].strip()) if parts[4].strip() else 0.0
                    nav_data[scheme_code] = NAVData(
                        scheme_code=scheme_code,
                        scheme_name=parts[3].strip(),
                        nav=nav,
                        date=parts[5].strip(),
                        fund_type="Mutual Fund",
                        fund_house=current_fund_house
                    )
                    parsed_count += 1
                except (ValueError, IndexError):
                    continue
                    
        logger.info(f"Successfully parsed {parsed_count} NAV entries")
                    
    except Exception as e:
        logger.error(f"Error parsing NAV batch data: {e}")
        
    return nav_data


def calculate_portfolio_value(holdings: list, nav_data: Dict[str, NAVData]) -> Dict[str, Any]:
    """Calculate total portfolio value using latest NAV data.
    
    Args:
        holdings: List of holdings with scheme_code and units
        nav_data: Dictionary of NAVData objects
        
    Returns:
        Dictionary with total_value, holdings_with_value, and missing_schemes
    """
    total_value = 0.0
    holdings_with_value = []
    missing_schemes = []
    
    for holding in holdings:
        scheme_code = holding.get("scheme_code")
        units = holding.get("units", 0)
        
        if scheme_code in nav_data:
            nav = nav_data[scheme_code].nav
            value = units * nav
            total_value += value
            holdings_with_value.append({
                **holding,
                "nav": nav,
                "value": value,
                "nav_date": nav_data[scheme_code].date
            })
        else:
            missing_schemes.append(scheme_code)
            holdings_with_value.append({
                **holding,
                "nav": None,
                "value": None
            })
    
    return {
        "total_value": total_value,
        "holdings": holdings_with_value,
        "missing_schemes": missing_schemes,
        "calculated_at": datetime.now().isoformat()
    }
