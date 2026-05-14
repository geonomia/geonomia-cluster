import argparse
import pandas as pd

def nullSafeMax():
    def max_func(x):
        try:
            return max([int(val) for val in x if pd.notnull(val)])
        except ValueError:
            return None
    return max_func

def nullSafeMin():
    def min_func(x):
        try:
            return min([int(val) for val in x if pd.notnull(val)])
        except ValueError:
            return None
    return min_func

def main():
    parser = argparse.ArgumentParser(description='Generate metadata about clusters in the occurrence data')
    parser.add_argument('--cluster_id_col', type=str, help='Name of the column containing cluster IDs in the clustered occurrence file', default='cluster_num_id')
    parser.add_argument('input_occ_file', type=str, help='Path to the original input occurrence TSV file')
    parser.add_argument('input_prepared_file', type=str, help='Path to the input prepared occurrence TSV file')
    parser.add_argument('input_clustered_file', type=str, help='Path to the input clustered occurrence TSV file with cluster labels')
    parser.add_argument('output_file', type=str, help='Path to the output CSV file to save cluster metadata')
    args = parser.parse_args()

    print(f'Reading original occurrence data from datafile {args.input_occ_file}')
    # Load the occurrence data
    df_occ_orig = pd.read_csv(args.input_occ_file, sep='\t', on_bad_lines='warn')
    print(f'Loaded original occurrence data from {args.input_occ_file} with {len(df_occ_orig)} records')

    print(f'Reading prepared occurrence data from datafile {args.input_prepared_file}')
    # Load the occurrence data
    df_occ_prep = pd.read_csv(args.input_prepared_file, sep='\t')
    print(f'Loaded prepared occurrence data from {args.input_prepared_file} with {len(df_occ_prep)} records')

    # Join df_occ_orig and df_occ_prep to get all the columns together (using 'gbifid' as the key)
    # Only take columns from df_occ_orig that are not in df_occ_prep to avoid duplicates
    cols_to_merge = [col for col in df_occ_orig.columns if col not in df_occ_prep.columns or col == 'gbifid']
    df_occ = df_occ_prep.merge(df_occ_orig[cols_to_merge], on='gbifid', how='left')
    print(f'Merged original and prepared occurrence data to get {len(df_occ)} records with all columns')

    print("Columns in merged occurrence data:", df_occ.columns.tolist())
    print(df_occ.sample(5).T)
    print(f'Reading clustered occurrence data from datafile {args.input_clustered_file}')
    # Load the clustered occurrence data
    df_clustered = pd.read_csv(args.input_clustered_file, sep='\t')
    print(f'Loaded clustered occurrence data from {args.input_clustered_file} with {len(df_clustered)} records')

    # Join the clustered data with the original occurrence data to get all the columns together
    df_merged = df_clustered[['gbifid',args.cluster_id_col]].merge(df_occ, on='gbifid', how='left')

    print("Columns in merged occurrence data:", df_merged.columns.tolist())
    print(df_merged.sample(5).T)

    # Drop noise records (those with cluster ID -1)
    df_merged = df_merged[df_merged[args.cluster_id_col] != -1]

    # Group by cluster ID and calculate metadata for each cluster
    cluster_metadata = df_merged.groupby(args.cluster_id_col).agg(
        num_records=('gbifid', 'count'),
        recordedby_unique=('recordedby', 'nunique'),
        # data was batched by recordedby family name, so we can take the first family name as a representative for the cluster
        recordedby_first_familyname=('recordedby_first_familyname',lambda x: x.iloc[0].split(',')[0] if pd.notnull(x.iloc[0]) else None),
        recordnumber_unique=('recordnumber', 'nunique'),
        eventdate_unique=('eventdate_day_offset', 'nunique'),
        eventdate_day_offset_min=('eventdate_day_offset', 'min'),
        eventdate_day_offset_max=('eventdate_day_offset', 'max'),
        year_min=('year', nullSafeMin()),
        year_max=('year', nullSafeMax()),
        countrycode_unique=('countrycode', 'nunique'),
        # decimallatitude_unique=('decimallatitude', 'nunique'),
        # decimallongitude_unique=('decimallongitude', 'nunique'),
        duration_days=('eventdate_day_offset', lambda x: x.max() - x.min()),
        hascoordinate_count=('hascoordinate', lambda x: len([val for val in x if val == 1]))
    ).reset_index()

    cluster_metadata['hascoordinate_pct'] = round(cluster_metadata['hascoordinate_count'] / cluster_metadata['num_records'] * 100, 2)
    cluster_metadata['days_active_pct'] = round(cluster_metadata['eventdate_unique'] / (cluster_metadata['duration_days'] + 1) * 100, 2)
    
    # Convert year_min and year_max to integers (they may be floats due to NaN values)
    cluster_metadata['year_min'] = cluster_metadata['year_min'].astype('Int64')
    cluster_metadata['year_max'] = cluster_metadata['year_max'].astype('Int64')

    # Save the cluster metadata to a CSV file
    cluster_metadata.to_csv(args.output_file, index=False, sep='\t')
    
if __name__ == '__main__':
    main()
