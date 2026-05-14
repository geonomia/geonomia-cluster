import argparse
import os
from jinja2 import Template
from pygbif import occurrences as occ

def main():
    parser = argparse.ArgumentParser(description='Request a download of occurrence data from GBIF')
    parser.add_argument('query_template_file', type=str, help='Path to the query template file (a text file containing the query template with placeholders for parameters)')
    parser.add_argument('--countrycodes', type=str, help='Comma-separated list of country codes for the download (e.g. "CO,PE,EC)")')
    parser.add_argument('--phylum_key', type=int, required=False, default=7707728, help='The key of the phylum to download (e.g. "Tracheophyta" is 7707728)')
    args = parser.parse_args()

    # Load the SQL template
    with open(args.query_template_file, 'r') as f:
        template_str = f.read()

    country_code_l = args.countrycodes.split(',') if ',' in args.countrycodes else [args.countrycodes]
    print(country_code_l)

    # Create the template object and render
    template = Template(template_str)
    rendered_sql = template.render(
       country_codes=country_code_l,
        phylum_key=args.phylum_key
    )

    # Request the download from GBIF
    download_request_id = occ.download_sql(
        rendered_sql,
        user=os.getenv('GBIF_USERNAME'),
        pwd=os.getenv('GBIF_PASSWORD'),
        email=os.getenv('GBIF_EMAIL'),
        format='SQL_TSV_ZIP'
    )

    print(f'Download requested with key {download_request_id}. Check GBIF download page for status: https://www.gbif.org/downloads/{download_request_id}')
    os.environ['GBIF_DOWNLOAD_ID'] = download_request_id

if __name__ == "__main__":
    main()