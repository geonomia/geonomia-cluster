import argparse
import pandas as pd

def main():
    parser = argparse.ArgumentParser(description="Join original occurrence download and output of clustering process to create a labelled occurrence data file suitable for insert into sqlite")
    parser.add_argument("occ_file", help="Path to the downloaded occurrence file (gzipped TSV)")
    parser.add_argument("occ_clustered_file", help="Path to the clustered occurrence file (TSV)")
    parser.add_argument("output_file", help="Path to the output file for the joined data (TSV)")
    parser.add_argument("--id_col_name", default="gbifid", help="Name of the column containing the occurrence id in both files (default: 'gbifid')")
    parser.add_argument("--cluster_col_name", default="cluster_stage1_id", help="Name of the column containing the cluster id in occ_clustered file (default: 'cluster_stage1_id')")
    parser.add_argument("--recordnumber_col_name", default="recordnumber_mainnumber", help="Name of the column containing the recordnumber in occ_clustered file (default: 'recordnumber_mainnumber')")
    parser.add_argument("--eventdate_col_name", default="eventdate", help="Name of the column containing the eventdate in occ_clustered file (default: 'eventdate')")
    parser.add_argument("--hascoordinate_col_name", default="hascoordinate", help="Name of the column containing the hascoordinate flag in occ_clustered file (default: 'hascoordinate')")

    args = parser.parse_args()

    df_occ = pd.read_csv(args.occ_file, sep='\t', compression='zip', on_bad_lines="skip", engine='python')
    print(f"Loaded {len(df_occ)} occurrences from {args.occ_file}")
    print(f"Columns in occurrence file: {df_occ.columns.tolist()}")
    eligibility_columns = [col for col in df_occ.columns if col.endswith('_eligible')]
    print(f"Eligibility columns in occ file: {eligibility_columns}")
    for col in eligibility_columns:
        # Set non-True values to False, to make it easier to work with in sqlite
        df_occ[col] = df_occ[col].map({'True': True}).fillna(False).astype('bool')
    
    df_occ_clustered = pd.read_csv(args.occ_clustered_file, sep='\t',low_memory=False)
    print(f"Loaded {len(df_occ_clustered)} clustered occurrences from {args.occ_clustered_file}")
    print(f"Columns in clustered file: {df_occ_clustered.columns.tolist()}")
    eligibility_columns = [col for col in df_occ_clustered.columns if col.endswith('_eligible')]
    print(f"Eligibility columns in clustered file: {eligibility_columns}")
    for col in eligibility_columns:
        # Set non-True values to False, to make it easier to work with in sqlite
        #  df_occ_clustered[col] = df_occ_clustered[col].map({'True': True}).fillna(False).astype('bool')
        print(f"Distribution of values in column {col}:\n {df_occ_clustered[col].value_counts(dropna=False)}")

    print(df_occ_clustered.groupby(eligibility_columns).size().reset_index(name='count').sort_values('count', ascending=False))
    
    # We don't want to do a full join as the clustered file is a subset of the 
    # original, so we inspect the columns in the clustered file and only carry 
    # across those not in the original file, to avoid creating duplicate columns
    # for the original data
    # We also need the id column in the clustered file to do the join, so we include that too
    columns_to_add = [args.id_col_name] + [col for col in df_occ_clustered.columns if col not in df_occ.columns]
    print(f"Columns to add from clustered file: {columns_to_add}")

    # Join the clustered data with the original data
    df_joined = df_occ.merge(df_occ_clustered[columns_to_add], left_on=args.id_col_name, right_on=args.id_col_name, how='left')
    print(f"Joined data has {len(df_joined)} rows and {len(df_joined.columns)} columns")
    print(f"Columns in joined data: {df_joined.columns.tolist()}")
    print(f"Sample joined data:\n {df_joined.head()}")
    
    # Modify eligibility columns
    print("Inspecting eligibility columns:")
    for col in eligibility_columns:
        print(f"distribution of values in column {col}:\n {df_joined[col].value_counts(dropna=False)}")
        # print(f"pre-conversion distribution of values in column {col}:\n {df_joined[col].value_counts(dropna=False)}")
        # df_joined[col] = df_joined[col].map({'True': True, 'False': False}).astype(pd.BooleanDtype())
        # print(f"post-conversion distribution of values in column {col}:\n {df_joined[col].value_counts(dropna=False)}")

    # Modify boolean columns to be 1 for True and 0 for False, to make it easier to work with in sqlite
    print(df_joined.dtypes)
    bool_cols = df_joined.select_dtypes(include=['bool','boolean']).columns
    print(f"Boolean columns to convert: {bool_cols}")
    for col in bool_cols:
        print(f"Converting column {col} to integer")
        print(f"pre-conversion distribution of values in column {col}:\n {df_joined[col].value_counts(dropna=False)}")
        df_joined[col] = df_joined[col].map({True: 1, False: 0}).astype('Int64')
        print(f"post-conversion distribution of values in column {col}:\n {df_joined[col].value_counts(dropna=False)}")
    # df_joined[bool_cols] = df_joined[bool_cols].astype(int)
    if args.hascoordinate_col_name not in bool_cols:
        df_joined[args.hascoordinate_col_name] = df_joined[args.hascoordinate_col_name].map({'true': 1, 'false': 0}).astype('Int64')
        print(f"post-conversion distribution of values in column {args.hascoordinate_col_name}:\n {df_joined[args.hascoordinate_col_name].value_counts(dropna=False)}")
        # print(f"Warning: hascoordinate column '{args.hascoordinate_col_name}' is not boolean in the joined data, it will not be converted to integer. Please check the column name and the data types in the original and clustered files.")

    # Display group by eligibility_columns to check the distribution of eligible vs ineligible occurrences
    for col in eligibility_columns:
        print(df_joined[col].describe())

    print("Distribution of eligible vs ineligible occurrences:")
    print(df_joined.groupby(eligibility_columns).size().reset_index(name='count'))

    # Add details for where each record could receive coordinates
    # Options are: 
    # (1) already has coordinates (specimen metadata), 
    # (2) a duplicate collecting event has coordinates (collecting event), 
    # (3) another record collected by the same collector on the same day has coordinates (collector day)

    # (1) already has coordinates ("specimen_metadata")
    df_joined['coordinate_source_specimen_metadata'] = 0
    mask = (df_joined[args.hascoordinate_col_name] == 1)
    df_joined.loc[mask, 'coordinate_source_specimen_metadata'] = 1

    # (2) a duplicate collecting event has coordinates ("collecting_event")
    # group records by collecting event (cluster_id is not noise, cluster_id is shared, recordnumber_mainnumber is shared)
    mask = (df_joined[args.cluster_col_name] != -1)
    group_cols = [args.cluster_col_name, args.recordnumber_col_name]
    dfg = df_joined[mask].groupby(group_cols).agg(has_coordinate_true = (args.hascoordinate_col_name, 'sum'),
                                              has_coordinate_false = (args.hascoordinate_col_name, lambda x: x.count() - x.sum())).reset_index()
    dfg['coordinate_source_collecting_event'] = 0
    dfg.loc[dfg['has_coordinate_true'] > 0, 'coordinate_source_collecting_event'] = 1
    df_joined = df_joined.merge(dfg[group_cols + ['coordinate_source_collecting_event']], on=group_cols, how='left')

    # (3) another record collected by the same collector on the same day has coordinates ("collector_day")
    # group records by collector day (cluster_id is not noise, cluster_id is shared, eventdate is shared)
    mask = (df_joined[args.cluster_col_name] != -1)
    group_cols = [args.cluster_col_name, args.eventdate_col_name]
    dfg = df_joined[mask].groupby(group_cols).agg(has_coordinate_true = (args.hascoordinate_col_name, 'sum'),
                                              has_coordinate_false = (args.hascoordinate_col_name, lambda x: x.count() - x.sum())).reset_index()
    dfg['coordinate_source_collector_day'] = 0
    dfg.loc[dfg['has_coordinate_true'] > 0, 'coordinate_source_collector_day'] = 1
    df_joined = df_joined.merge(dfg[group_cols + ['coordinate_source_collector_day']], on=group_cols, how='left')
    
    for col in ['hascoordinate', 'coordinate_source_specimen_metadata', 'coordinate_source_collecting_event', 'coordinate_source_collector_day']:
        # update any nulls to 0, as the absence of evidence for coordinates from any source is evidence of absence of coordinates from that source
        df_joined[col] = df_joined[col].fillna(0).astype('Int64')

    print(df_joined.groupby(['coordinate_source_specimen_metadata', 'coordinate_source_collecting_event', 'coordinate_source_collector_day']).size().reset_index(name='count'))
    
    # Build a single column for coordinate source, with values "specimen_metadata", "collecting_event", "collector_day", or "none"
    def determine_coordinate_source(row):
        if row['coordinate_source_specimen_metadata'] == 1:
            return 'specimen_metadata'
        elif row['coordinate_source_collecting_event'] == 1:
            return 'collecting_event'
        elif row['coordinate_source_collector_day'] == 1:
            return 'collector_day'
        else:
            return 'none'

    df_joined['coordinate_source'] = df_joined.apply(determine_coordinate_source, axis=1)
    # Display the distribution of coordinate sources
    print("Distribution of coordinate sources:")
    print(df_joined['coordinate_source'].value_counts(dropna=False))

    # Save the joined data to a new TSV file
    df_joined.to_csv(args.output_file, sep='\t', index=False)

if __name__ == "__main__":
    main()
