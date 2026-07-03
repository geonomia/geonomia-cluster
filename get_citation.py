#!/usr/bin/env python3

import argparse
import json
from pygbif import occurrences
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_doi(download_id: str) -> str:
    """
    Fetch DOI for a GBIF download using pygbif.
    """
    resp = occurrences.download_meta(download_id)

    doi = resp.get("doi")
    if not doi:
        logger.error(f"No DOI found for download_id={download_id}. Response: {resp}")
        raise RuntimeError(f"No DOI found for download_id={download_id}")

    return doi


def fetch_citation_csl_json(doi: str) -> str:
    """
    Fetch CSL JSON citation from DOI resolver.
    """
    import requests

    logger.info(f"Fetching citation for DOI: {doi}")
    url = f"https://doi.org/{doi}"
    headers = {
        "Accept": "application/vnd.citationstyles.csl+json"
    }

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    return r.text


def main():
    parser = argparse.ArgumentParser(description="Fetch GBIF citation CSL JSON")
    parser.add_argument("--download-id", required=True, help="GBIF download ID")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--logging-level", type=str, default="INFO", help="Logging level (default: INFO)")

    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.logging_level.upper()))

    logger.info(f"Called get_citation.py with arguments: {args}")
    
    doi = fetch_doi(args.download_id)
    citation = fetch_citation_csl_json(doi)

    # validate JSON (optional but useful in HPC pipelines)
    try:
        json.loads(citation)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid CSL JSON returned for DOI {doi}: {e}")
        raise RuntimeError(f"Invalid CSL JSON returned for DOI {doi}") from e

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(citation)

    logger.info(f"Wrote citation to {args.output}")


if __name__ == "__main__":
    main()
