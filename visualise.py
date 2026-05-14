import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def main():
    parser = argparse.ArgumentParser(description='Visualise summary data about clusters')
    parser.add_argument('input_file', type=str, help='Path to the input summary file')
    args = parser.parse_args()

    print(f'Reading summary data from datafile {args.input_file}')
    # Load the summary data
    df_summary = pd.read_csv(args.input_file, sep='\t')
    print(f'Loaded summary data from {args.input_file} with {len(df_summary)} records')
    print("Columns in summary data:", df_summary.columns.tolist())
    print(df_summary.sample(5).T)

    # cluster_stage1_id,num_records,recordedby_unique,recordnumber_unique,eventdate_unique,eventdate_day_offset_min,eventdate_day_offset_max,countrycode_unique,duration_days,hascoordinate_count,hascoordinate_pct,days_active_pct
    
    # Visualise the distribution of number of records per cluster
    plt.figure(figsize=(10, 6))
    sns.histplot(df_summary['num_records'], bins=50, kde=True)
    plt.title('Distribution of Number of Records per Cluster')
    plt.xlabel('Number of Records')
    plt.ylabel('Frequency')
    plt.show()

    # Visualise the distribution of durations of cluster activity
    plt.figure(figsize=(10, 6))
    sns.histplot(df_summary['duration_days'], bins=50, kde=True)
    plt.title('Distribution of Duration of Cluster Activity (days)')
    plt.xlabel('Duration (days)')
    plt.ylabel('Frequency')
    plt.show()

    # Visualise the distribution of percentages of days active
    plt.figure(figsize=(10, 6))
    sns.histplot(df_summary['days_active_pct'], bins=50, kde=True)
    plt.title('Distribution of Percentage of Days Active')
    plt.xlabel('Percentage of Days Active')
    plt.ylabel('Frequency')
    plt.show()

    # Visualise the relationship between number of records and percentage of records with coordinates
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df_summary, x='num_records', y='hascoordinate_pct')
    plt.title('Number of Records vs Percentage with Coordinates')
    plt.xlabel('Number of Records')
    plt.ylabel('Percentage with Coordinates')
    plt.show()  

    # Visualise the relationship between number of records and percentage of days active
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df_summary, x='num_records', y='days_active_pct')
    plt.title('Number of Records vs Percentage of Days Active')
    plt.xlabel('Number of Records')
    plt.ylabel('Percentage of Days Active')
    plt.show()

    # Visualise the relationship between duration of cluster activity and percentage of days active
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df_summary, x='duration_days', y='days_active_pct')
    plt.title('Duration of Cluster Activity vs Percentage of Days Active')
    plt.xlabel('Duration of Cluster Activity (days)')
    plt.ylabel('Percentage of Days Active')
    plt.show()


if __name__ == "__main__":
    main()