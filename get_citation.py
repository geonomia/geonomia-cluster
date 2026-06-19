#!/usr/bin/env python3

import argparse
import json
from pygbif import occurrences


def fetch_doi(download_id: str) -> str:
    """
    Fetch DOI for a GBIF download using pygbif.
    """
    resp = occurrences.download_get(download_id)

    doi = resp.get("doi")
    if not doi:
        raise RuntimeError(f"No DOI found for download_id={download_id}")

    return doi


def fetch_citation_csl_json(doi: str) -> str:
    """
    Fetch CSL JSON citation from DOI resolver.
    """
    import requests

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

    args = parser.parse_args()

    doi = fetch_doi(args.download_id)
    citation = fetch_citation_csl_json(doi)

    # validate JSON (optional but useful in HPC pipelines)
    try:
        json.loads(citation)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid CSL JSON returned for DOI {doi}") from e

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(citation)

    print(f"Wrote citation to {args.output}")


if __name__ == "__main__":
    main()
