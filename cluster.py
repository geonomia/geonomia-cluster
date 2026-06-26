import argparse
import pandas as pd
from sklearn.cluster import DBSCAN
from tqdm import tqdm
from geonomia_dtypes import DATA_SCHEMA

# Display at least 500 records when printing dataframes
pd.set_option('display.max_rows', 500)

def do_clustering(df, cluster_cols, eps=20, min_samples=5, id_col_name='gbifid', cluster_col_name='cluster_id'):
    # Prepare data for clustering
    clustering_data = df[[id_col_name] + cluster_cols].dropna()

    # Perform DBSCAN clustering
    dbscan = DBSCAN(eps=eps, min_samples=min_samples, n_jobs=-1)
    clustering_data[cluster_col_name] = dbscan.fit_predict(clustering_data[cluster_cols])

    # join cluster results back to the main dataframe
    df = df.merge(clustering_data[[id_col_name, cluster_col_name]], on=id_col_name, how='left')
    
    return df

def do_batched_clustering(df, cluster_cols, eps=20, min_samples=5, id_col_name='gbifid', cluster_col_name='cluster_id', batch_col_name='recordedby_first_familyname', intermediate_file=None):
    # Prepare data for clustering
    # We will do clustering in batches based on the batch_col_name, 
    # to ensure that we don't cluster records from different collectors together, 
    # and to make the clustering more efficient by reducing the number of records 
    # in each batch. We will also keep track of the cluster_id offset for each 
    # batch to ensure unique cluster IDs across batches.
    clustering_data = pd.DataFrame(df[[id_col_name, batch_col_name] + cluster_cols].dropna())

    # Used in dev to do a smaller sample
    # batch_values = clustering_data[batch_col_name].unique()[:10]

    # Gather these in order of the most frequently occurring batch_col_name values, 
    # to ensure that we are doing the most efficient clustering first 
    # (i.e. clustering the largest batches first)
    batches = clustering_data[batch_col_name].value_counts()
    print(batches)
    # Only use the batches that are above the min_samples threshold, as smaller batches won't produce any clusters and can be skipped
    batches = batches[batches >= min_samples] 
    batch_values = batches.index.tolist()
    print(f'Clustering will be performed in {len(batch_values)} batches based on {batch_col_name} values that have at least {min_samples} records.')

    cluster_id_offset = 0
    mode = 'w'
    header = True
    df_interm_data = None
    interm_size_max = 50000 # to avoid memory issues, we will write intermediate results to file in batches rather than keeping them all in memory
    
    for batch_value in tqdm(batch_values):
        df_batch_data = pd.DataFrame(clustering_data[clustering_data[batch_col_name] == batch_value])

        # Perform DBSCAN clustering
        dbscan = DBSCAN(eps=eps, min_samples=min_samples)
        cluster_ids = dbscan.fit_predict(df_batch_data[cluster_cols])
        
        # Apply cluster_id_offset to ensure unique cluster IDs across batches (except for noise points which have cluster ID -1)
        cluster_ids = [cluster_id + cluster_id_offset if cluster_id != -1 else -1 for cluster_id in cluster_ids]
        
        # Save in data structure
        df_batch_data[cluster_col_name] = cluster_ids

        # Update cluster_id_offset for the next batch, to ensure unique cluster IDs across batches
        if df_batch_data[cluster_col_name].max() + 1 > cluster_id_offset:
            cluster_id_offset = df_batch_data[cluster_col_name].max() + 1
        
        # Update the clustering_data data structure with the cluster_ids
        clustering_data.loc[clustering_data[batch_col_name] == batch_value, cluster_col_name] = df_batch_data[cluster_col_name].values

        if intermediate_file is not None:
            if df_interm_data is None:
                df_interm_data = df_batch_data
            else:
                df_interm_data = pd.concat([df_interm_data, df_batch_data], ignore_index=True)
            
            if len(df_interm_data) >= interm_size_max:
                # Write intermediate results to a CSV file for inspection
                df_interm_data.to_csv(intermediate_file, index=False, mode=mode, header=header, sep='\t')
                mode = 'a'
                header = False
                df_interm_data = None

    # Write any remaining intermediate results to a CSV file for inspection
    if intermediate_file is not None and df_interm_data is not None:
        df_interm_data.to_csv(intermediate_file, index=False, mode=mode, header=header, sep='\t')
        
    # Join cluster results back to the main dataframe
    df = df.merge(clustering_data[[id_col_name, cluster_col_name]], on=id_col_name, how='left')
    
    return df

def main():
    parser = argparse.ArgumentParser(description='Cluster prepared occurrence data')
    parser.add_argument('input_file', type=str, help='Path to the prepared occurrence data CSV file')
    parser.add_argument('--id_col', type=str, required=True, default='gbifid', help='Name of the column holding the record identifier (default: gbifid)')
    parser.add_argument('--columns', type=str, required=True, help='Comma separated list of columns to use for clustering (default: eventdate_day_offset,recordnumber_mainnumber)')    
    parser.add_argument('--cluster_id_col', type=str, required=True, default='cluster_num_id', help='Name of the column to store cluster IDs in (default: cluster_num_id)')
    parser.add_argument('--batch_col_name', type=str, required=True, default='recordedby_first_familyname', help='Name of the column to batch by for clustering (default: recordedby_first_family)')    
    parser.add_argument('--additional_col_names', type=str, required=False, help='Comma separated list of additional column names to include in the output (default: none)')
    parser.add_argument('--eligible_flag_columns', type=str, required=True, default='eventdate_eligible,recordnumber_eligible,recordedby_eligible', help='Comma separated list of columns that must not be null for a record to be eligible for clustering (default: none)')
    parser.add_argument('--temp_file', type=str, required=False, help='Path to temp file to save intermediate results')
    parser.add_argument('--output_all_records', action='store_true', help='Whether to output all records, or only those that were eligible for clustering (i.e. have non-null values for the cols used for clustering) and assigned a cluster label')
    parser.add_argument('output_file', type=str, help='Path to the outputfile CSV file')

    args = parser.parse_args()

    print(args)

    print(f'Reading prepared occurrence data from datafile {args.input_file}')
    # Load the occurrence data
    cols = [args.id_col] + args.columns.split(',') + args.eligible_flag_columns.split(',') + [args.batch_col_name]
    if args.additional_col_names:
        cols += args.additional_col_names.split(',')
    df_occ = pd.read_csv(args.input_file, usecols=cols, sep='\t', engine='python', on_bad_lines='skip', dtype=DATA_SCHEMA)
    print(f'Loaded occurrence data from {args.input_file} with {len(df_occ)} records')
    print(f'Columns loaded: {df_occ.columns.tolist()}')

    print(df_occ.recordedby_first_familyname.value_counts().head(20))

    # Show breakdown of the flags used for cluster eligibility
    print(df_occ.dtypes)
    print(df_occ.groupby(args.eligible_flag_columns.split(',')).size())
    
    # Display sample of occurrence data
    print(df_occ.head())
    print(df_occ.sample(n=1).T)

    # Use density based clustering (e.g. DBSCAN) to identify clusters of 
    # records in the eventDate_offset vs recordNumber_mainNumber space, 
    # and print out the clusters and their characteristics (e.g. number 
    # of records in each cluster, mean eventDate_offset and 
    # recordNumber_mainNumber for each cluster, etc.)
    df_occ = do_batched_clustering(df_occ, 
                                   cluster_cols = ['eventdate_day_offset', 'recordnumber_mainnumber'], 
                                   id_col_name=args.id_col, 
                                   cluster_col_name=args.cluster_id_col, 
                                   batch_col_name=args.batch_col_name, 
                                   intermediate_file=args.temp_file)

    if args.output_all_records:
        print(f'Outputting all {len(df_occ)} records with cluster labels to {args.output_file}')
        df_occ.to_csv(args.output_file, sep='\t', index=False)
    else:
        # Output only data with cluster labels to a new CSV file for further analysis
        mask = df_occ[args.cluster_id_col].notnull()
        print(f'Outputting {df_occ[mask].shape[0]} records to {args.output_file}')
        df_occ[mask].to_csv(args.output_file, sep='\t', index=False)

if __name__ == '__main__':
    main()
