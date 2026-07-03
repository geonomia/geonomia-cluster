import argparse
import json
import pandas as pd
import re
import requests
from time import sleep
from tqdm import tqdm
from urllib.parse import quote
from unidecode import unidecode
from geonomia_dtypes import DATA_SCHEMA
import logging
# display at least 500 records when outputting dataframes
pd.set_option("display.max_rows", 500)
# set up tqdm for pandas
tqdm.pandas()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def date2offset(date_str, unit="days"):
    """
    Convert a date string in the format 'YYYY-MM-DD' to an offset in unit (days or months) from 1970-01-01
    If the date is invalid or cannot be parsed, return None.
    """
    try:
        date = pd.to_datetime(date_str, errors="coerce")
        if pd.isnull(date):
            return None
        epoch = pd.Timestamp("1970-01-01")
        if unit == "quarters":
            offset = (date.year - epoch.year) * 4 + (date.month - 1) // 3
        elif unit == "months":
            offset = (date.year - epoch.year) * 12 + (date.month - epoch.month)
        else:
            offset = (date - epoch).days
        return offset
    except Exception as e:
        logger.error(f"Error parsing date '{date_str}': {e}")
        return None


def parse_record_number(value, convert_numeric_parts=True):
    """
    Parses a recordNumber into structured components.
    Targeting the patterns: 0+, A+0+, A.0+, 0+/0+, 0+a, etc.
    """
    if not value or not isinstance(value, str):
        return {
            k: None
            for k in ["prefix", "mainnumber", "separator", "ancillarynumber", "suffix"]
        }

    # Regex breakdown:
    # ^(?P<prefix>.*?)           -> Everything before the first digit
    # (?P<mainnumber>\d+)        -> The first sequence of digits
    # (?P<suffix>[a-zA-Z]+)?     -> Optional letter immediately after (e.g., 123a)
    # (?P<sep_group>             -> Group for secondary numbers
    #    [\s\-/.]+               -> Separator characters
    #    (?P<ancillarynumber>\d+) -> The second sequence of digits
    # )?                         -> The whole secondary part is optional
    # (?P<trailing>.*)$          -> Anything left over

    regex = r"^(?P<prefix>.*?)(?P<mainnumber>\d+)(?P<suffix>[a-zA-Z]+)?(?P<sep_group>[\s\-/.]+(?P<ancillarynumber>\d+))?(?P<trailing>.*)$"

    match = re.match(regex, value.strip())

    if match:
        res = match.groupdict()
        # Clean up the separator from the sep_group
        full_sep_group = res.get("sep_group") or ""
        ancillary = res.get("ancillarynumber") or ""

        # Extract actual separator character (e.g., the '/' in '/4')
        separator = (
            full_sep_group.replace(ancillary, "").strip() if full_sep_group else None
        )

        # If there's a suffix in 'trailing' but not in 'suffix', combine them
        # This handles cases like '0+ A' where 'A' is a trailing suffix
        final_suffix = (res.get("suffix") or "") + (res.get("trailing") or "").strip()

        parsed = {
            "prefix": res.get("prefix").strip() if res.get("prefix") else None,
            "mainnumber": res.get("mainnumber"),
            "separator": separator if separator else None,
            "ancillarynumber": ancillary if ancillary else None,
            "suffix": final_suffix.strip() if final_suffix else None,
        }

        if convert_numeric_parts:
            # Convert mainNumber and ancillaryNumber to integers if they exist
            parsed["mainnumber"] = (
                int(parsed["mainnumber"]) if parsed["mainnumber"] else None
            )
            parsed["ancillarynumber"] = (
                int(parsed["ancillarynumber"]) if parsed["ancillarynumber"] else None
            )

        return parsed

    # Fallback for non-numeric records (e.g., pattern 'a.a.')
    return {
        "prefix": value,
        "mainnumber": None,
        "separator": None,
        "ancillarynumber": None,
        "suffix": None,
    }


DWC_AGENT_PARSE_URL_REMOTE = "https://api.bionomia.net/parse.json"
DWC_AGENT_PARSE_URL_LOCAL = "http://127.0.0.1:7654/parse_batch"


def buildRecordedBy2FamilyNameMap(recordedby_l, use_local_recordedby_parse=False):

    recordedby_l = recordedby_l.tolist()
    post_data = "names=" + quote("\r\n".join(recordedby_l))
    original_key_name = "original"

    if use_local_recordedby_parse:
        post_data = {"inputs": recordedby_l}
        original_key_name = "input"
        response = requests.post(DWC_AGENT_PARSE_URL_LOCAL, json=post_data, timeout=60)

    else:
        response = requests.post(
            DWC_AGENT_PARSE_URL_REMOTE,
            # url encode the recordedby_l list into a format suitable for application/x-www-form-urlencoded content type, with each name on a new line and ampersands escaped as %26
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=60,
        )

    mapping = {}
    result = response.json()
    logger.debug(f'API returned {len(result)} parsed names')
    if len(result) != len(recordedby_l):
        logger.warning(
            f"Warning: number of parsed results ({len(result)}) does not match number of input names ({len(recordedby_l)})"
        )
    for item in result:
        # logger.debug(f'Processing item: {item}')
        original = item[original_key_name]
        try:
            families = [item["parsed"][i]["family"] for i in range(len(item["parsed"]))]
            # family = item['parsed'][0]['family']
            mapping[original] = ";".join(families)
        except Exception:
            mapping[original] = None
    if not use_local_recordedby_parse:
        sleep(0.2)  # to avoid hitting API rate limits
    return mapping


def main():
    parser = argparse.ArgumentParser(
        description="Prepare occurrence data for clustering"
    )
    parser.add_argument(
        "input_file", type=str, help="Path to the occurrence data CSV file"
    )
    parser.add_argument(
        "--columns_required",
        type=str,
        default="",
        help="Comma-separated list of columns to include in the output file (if not specified, all columns will be included)",
    )
    parser.add_argument(
        "--columns_optional",
        type=str,
        default="",
        help="Comma-separated list of columns to read from the input file (if not specified, all columns will be read)",
    )
    # Add verbosity flag, default to False
    parser.add_argument(
        "--verbose", action="store_true", help="Increase output verbosity"
    )
    parser.add_argument(
        "--intermediate_output_file",
        required=False,
        type=str,
        help="Path to the intermediate output CSV file where the augmented data will be saved",
    )
    parser.add_argument(
        "--recordedby_mapping_output_file",
        required=False,
        type=str,
        help="Path to the JSON file mapping recordedby to the first family name",
    )
    parser.add_argument(
        "--use_local_recordedby_parse",
        action="store_true",
        help="Use local parsing service instead of the Bionomia API for recordedby parsing",
    )
    parser.add_argument(
        "output_file",
        type=str,
        help="Path to the output CSV file where the prepared data will be saved",
    )
    parser.add_argument(
        "--log_level",
        type=str,
        default="INFO",
        help="Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))

    logger.info(f"Reading occurrence data from datafile {args.input_file}")
    # First read actual cols
    cols_actual = pd.read_csv(args.input_file, sep="\t", nrows=0).columns

    # Load the occurrence data, using only specified columns if provided, and print the number of records loaded
    col_subset = None
    if args.columns_required:
        cols_req = [col.strip() for col in args.columns_required.split(",")]
        # Check all required columns are in the actual columns of the input file
        for col in cols_req:
            if col not in cols_actual:
                raise ValueError(
                    f'Required column "{col}" not found in input file. Actual columns are: {cols_actual}'
                )
                exit(1)
        logger.info(f"Only including specified columns: {cols_req}")
        col_subset = cols_req

    if args.columns_optional:
        cols_opt = [col.strip() for col in args.columns_optional.split(",")]
        # Check all optional columns are in the actual columns of the input file
        for col in cols_opt:
            if col not in cols_actual:
                # Just print warning as these can be computed locally if not present in input file
                logger.warning(
                    f'Optional column "{col}" not found in input file. Actual columns are: {cols_actual}'
                )
        col_subset = (
            cols_opt if col_subset is None else list(set(col_subset) | set(cols_opt))
        )
        logger.info(f"Including optional columns: {cols_opt}")

    if col_subset is not None:
        logger.info(f"Final list of columns to read from input file: {col_subset}")
        # We first read the complete set of columns in the input file as this allows us to
        # use on_bad_lines="skip" to skip any malformed lines, and then we subset the 
        # dataframe to only include the specified columns. This avoids issues with 
        # specifying a subset of columns in read_csv when there are malformed lines 
        # in the input file. 
        df_occ = pd.read_csv(
            args.input_file,
            sep="\t",
            on_bad_lines="skip",
            engine="python",
            dtype=DATA_SCHEMA
        )
        # Only keep the columns in col_subset
        df_occ = df_occ[col_subset]
    else:
        df_occ = pd.read_csv(
            args.input_file, sep="\t", on_bad_lines="skip", engine="python", dtype=DATA_SCHEMA
        )
    logger.info(f"Loaded occurrence data from {args.input_file} with {len(df_occ)} records")

    # Display sample of occurrence data
    logger.debug(df_occ.head())
    logger.debug(df_occ.sample(n=1).T)

    ###########################################################################
    # recordNumber
    ###########################################################################

    if "recordnumber_contains_numerals" not in df_occ.columns:
        mask = df_occ["recordnumber"].notnull()
        logger.info(
            "Adding column recordnumber_contains_numerals to indicate whether recordnumber contains any numerals"
        )
        df_occ.loc[mask, "recordnumber_contains_numerals"] = df_occ.loc[
            mask, "recordnumber"
        ].apply(lambda x: bool(re.search(r"\d", str(x))) if pd.notnull(x) else False)

    if "recordnumber_contains_year" not in df_occ.columns:
        mask = df_occ["recordnumber"].notnull() & df_occ["year"].notnull()
        df_occ.loc[mask, "recordnumber_contains_year"] = df_occ.loc[mask].apply(
            lambda row: bool(
                re.search(rf"\b{int(row['year'])}\b", str(row["recordnumber"]))
            ),
            axis=1,
        )

    mask = df_occ["recordnumber"].notnull() & df_occ["recordnumber_contains_numerals"]
    # Parse the recordnumber into structured components, save each in a new column
    for col in ["prefix", "mainnumber", "separator", "ancillarynumber", "suffix"]:
        df_occ.loc[mask, f"recordnumber_{col}"] = df_occ.loc[
            mask, "recordnumber"
        ].apply(lambda x: parse_record_number(x).get(col))

    logger.info(
        f"Parsed recordnumber into components for {mask.sum()} records where recordnumber contains numerals"
    )

    # Set up a null-safe mask to gather rows where recordnumber_contains_year is True, and display a sample of the recordnumber, year, and the parsed components for those rows, to understand how often the year is included in the recordnumber and in what format
    mask = df_occ["recordnumber_contains_year"].fillna(False)
    mask_count = mask.sum()
    logger.debug(
        df_occ[mask][
            [
                "recordnumber",
                "year",
                "recordnumber_contains_year",
                "recordnumber_prefix",
                "recordnumber_mainnumber",
                "recordnumber_separator",
                "recordnumber_ancillarynumber",
                "recordnumber_suffix",
            ]
        ].sample(min(250, mask_count))
    )
    # logger.debug('Most frequently occurring recordnumber mainnumber values:')
    # logger.debug(df_occ.recordnumber_mainnumber.value_counts().head(20))

    ###########################################################################
    # eventDate
    ###########################################################################

    if "eventdate_day_offset" not in df_occ.columns:
        # Convert to an offset from 1970-01-01 using the date2offset function,
        # but first gather the unique values in the eventdate column and only
        # apply the conversion to those unique values, then map the original
        # eventdate values to the converted offsets using a dictionary mapping,
        # to save time on the conversion and avoid converting the same date
        # multiple times

        # Gather unique values for eventDate
        eventdate_uniq = df_occ["eventdate"].dropna().unique()
        # Convert unique eventDate values to offsets and save the mapping

        # for date_offset_unit in ['quarters','days','months']:
        for date_offset_unit in ["day"]:
            eventdate_offset_mapping = {}
            logger.info(
                f"Mapping of unique eventdate values to offsets ({date_offset_unit}):"
            )
            for date in eventdate_uniq:
                offset = date2offset(date, unit=date_offset_unit)
                eventdate_offset_mapping[date] = offset
            if args.verbose:
                logger.info(
                    f"... generated {len(eventdate_offset_mapping)} unique eventdate offsets"
                )
            # Apply mapping to the eventDate column in main dataframe, creating a new column eventDate_offset_[unit]]
            df_occ[f"eventdate_{date_offset_unit}_offset"] = df_occ["eventdate"].map(
                eventdate_offset_mapping
            )

    logger.info(
        f"eventdate_offset available for {df_occ['eventdate_day_offset'].notnull().sum()} records"
    )

    ###########################################################################
    # recordedBy
    ###########################################################################

    mask = df_occ["recordedby"].notnull()
    if "recordedby_has_personal_name" in df_occ.columns:
        mask = df_occ["recordedby_has_personal_name"] == 1

    # Gather unique values for recordedby, along with a count of their occurrences, and save the mapping of recordedby to recordedby_first_familyname in a new dataframe
    df_rb = pd.DataFrame({"recordedby": df_occ[mask]["recordedby"].dropna().unique()})

    chunks = [group for _, group in df_rb["recordedby"].groupby(df_rb.index // 1000)]

    mapping = {}
    for chunk in tqdm(chunks):
        chunk_mapping = buildRecordedBy2FamilyNameMap(
            chunk, use_local_recordedby_parse=args.use_local_recordedby_parse
        )
        # logger.debug(f'Generated mapping for chunk with {len(chunk_mapping)} recordedby values')
        mapping.update(chunk_mapping)

    if args.recordedby_mapping_output_file:
        json.dump(mapping, open(args.recordedby_mapping_output_file, "w"), indent=2)

    logger.info(
        f"Generated mapping of recordedby to recordedby_families for {len(mapping)} unique recordedby values"
    )
    df_rb["recordedby_families"] = df_rb["recordedby"].map(mapping)
    df_rb["recordedby_first_familyname"] = df_rb["recordedby_families"].apply(
        lambda x: unidecode(x).split(";")[0] if pd.notnull(x) else None
    )
    df_rb["recordedby_team_familynames"] = df_rb["recordedby_families"].apply(
        lambda x: unidecode(x).split(";")[1:] if pd.notnull(x) and len(x.split(";")) > 1 else None
    )

    if args.intermediate_output_file:
        df_rb.to_csv(args.intermediate_output_file, sep="\t", index=False)
        logger.info(
            f"{len(df_rb)} lines of intermediate data on recordedby parsing saved to {args.intermediate_output_file}"
        )

    df_occ = df_occ.merge(
        df_rb[["recordedby", "recordedby_first_familyname", "recordedby_team_familynames"]],
        on="recordedby",
        how="left",
    )

    logger.debug(df_occ.recordedby_first_familyname.value_counts().head(20))

    ###########################################################################
    # Add flags to define eligibility
    ###########################################################################
    # Count how many records are eligible for clustering, ie have:
    #   non-null eventdate_day_offset
    #   non-null recordnumber_mainnumber
    #   non-null recordedby_first_familyname
    for eligibility_col, source_col in [
        ("eventdate_eligible", "eventdate_day_offset"),
        ("recordnumber_eligible", "recordnumber_mainnumber"),
        ("recordedby_eligible", "recordedby_first_familyname")
    ]:
        df_occ[eligibility_col] = df_occ[source_col].notnull()
        logger.info(f"Distribution of {eligibility_col}:")
        logger.info(df_occ[eligibility_col].value_counts())

    # group by the eligible flags and count the number of records in each group, to understand how many records are eligible for clustering and how many are being excluded due to missing values in the key columns
    logger.info("Breakdown of records by eligibility for clustering based on missing values in key columns:")
    logger.info(
        df_occ.groupby(
            ["eventdate_eligible", "recordnumber_eligible", "recordedby_eligible"]
        )
        .size()
        .reset_index(name="count")
    )
    # Show the most frequently occurring recordedby values for those where recordedby_eligible is False, to understand which collectors are being excluded from the clustering and why
    logger.debug(
        "Most frequently occurring recordedby values for those where recordedby_eligible is False:"
    )
    logger.debug(df_occ[~df_occ["recordedby_eligible"]]["recordedby"].value_counts().head(200))

    logger.debug(
        "Most frequently occurring recordedby values for those where recordnumber_eligible is False:"
    )
    logger.debug(
        df_occ[~df_occ["recordnumber_eligible"]]["recordedby"].value_counts().head(200)
    )

    logger.debug(
        "Most frequently occurring recordnumber values for those where recordnumber_eligible is False:"
    )
    logger.debug(
        df_occ[~df_occ["recordnumber_eligible"]]["recordnumber"]
        .value_counts()
        .head(200)
    )

    # Save augmented data ready for clustering
    # # Save the merged dataframe to a new CSV file
    df_occ.to_csv(args.output_file, sep="\t", index=False)
    logger.info(f"{len(df_occ)} lines of prepared data saved to {args.output_file}")


def removeBracketedText(s):
    """Remove any text in brackets from a string, along with the brackets themselves. For example, "Smith (Kew)" would become "Smith"."""
    if isinstance(s, str):
        return re.sub(r"\s*\(.*?\)\s*", "", s).strip()
    else:
        return s


def value2Pattern(value, fold=False, init=False):
    """Convert a value to a regex pattern that matches the value, but also allows for some common variations (e.g. different capitalisation, extra whitespace, etc.)
    Conversion rules:
    [A-Z] -> A
    [a-z] -> a
    [0-9] -> 0
    Examples:
    value2Pattern('Abc123') -> 'Aaa000'
    value2Pattern('  Abc 123  ') -> '  Aaa 000  '
    value2Pattern('Abc-123') -> 'Aaa-000'
    Then any runs of the same character in the pattern can be folded into a single character followed
    by "+", which allows for variations in the number of characters.
    For example, if fold is True, then 'Aaa000' would become 'Aa+0+', which would match 'Aa0', 'Aaa00',
    'Aaaaa0000', etc.
    Examples:
    value2Pattern('Abc123', fold=True) -> 'Aa+0+'
    To make it useful for recordedBy, we would like to also indicate runs of abbreviated initials "A." and "A.A." etc. as a single character, so we can add a rule that if we see a pattern of an uppercase letter followed by a period, we convert it to "I" (for initial), and then fold runs of "I" as well.
    For example:
    value2Pattern('J. A. Smith', fold=True) -> 'I+ A+'
    """
    pattern = ""
    # check if value is a string, if not return the value as is
    if not isinstance(value, str):
        return pattern

    for char in value:
        if char.isupper():
            pattern += "A"
        elif char.islower():
            pattern += "a"
        elif char.isdigit():
            pattern += "0"
        else:
            pattern += char

    if init:
        # Replace patterns of uppercase letter followed by a period with "I"
        pattern = re.sub(r"[A-Z]\.", "I", pattern)
        # replace "I I" with "II" repeatedly until there are no more occurrences, to handle cases like "J. A. Smith" -> "I I A" -> "II A"
        while "I I" in pattern:
            pattern = pattern.replace("I I", "II")

    # The fold flag controls whether runs of the same character in the pattern are folded into a single character followed by a +, which allows for variations in the number of characters. For example, if fold is True, then 'Aaa000' would become 'Aa+0+', which would match 'Aa0', 'Aaa00', 'Aaaaa0000', etc.
    if fold:
        # Fold consecutive identical characters into a single character followed by a +
        folded_pattern = ""
        for i, char in enumerate(pattern):
            if i == 0 or char != pattern[i - 1]:
                folded_pattern += char
            else:
                if not folded_pattern.endswith("+"):
                    folded_pattern += "+"
        pattern = folded_pattern
        if init:
            # Ensure that any I NOT followed by a + is replaced with "I+"
            # to allow for variations in the number of initials, so that
            # "I A" would match "I A", "II A", "III A", etc.
            pattern = re.sub(r"I(?!\+)", "I+", pattern)
            # Replace I++ with I+
            pattern = re.sub(r"I\++", "I+", pattern)
    return pattern


#  todo implement strict flag
def local_parse(s, output="familyname"):
    if s.count(", ") == 1:
        elems = s.split(", ")
        # if elems[0] matches [A-Z][a-z]+ and elems[1] matches any number of [A-Z]\., then return elems[0] as the family name
        # ie "Smith, J." -> "Smith", "Kerr, A.F.G." -> "Kerr", "Smith, J.P., Jones, A." -> "Smith"

        # if re.match(r'^[A-Z][a-z]+$', elems[0]) and re.match(r'^([A-Z]\.)+$', elems[1]):
        #     return elems[0]

        if re.match(r".*[A-ZÀ-ÖØ-ÞŠŽŘ].*", elems[0]):
            # if len(elems[1]) > 0 and re.match(r'[A-Z]', elems[1][0]):
            if output == "familyname":
                return elems[0]
            elif output == "familyname_initial":
                if re.match(r"^[A-Z].*$", elems[1]):
                    return f"{elems[0]}_{elems[1][0]}"
                else:
                    return elems[0]
        else:
            logger.warning(f"local_parse failed for {s}")
    return None


if __name__ == "__main__":
    main()