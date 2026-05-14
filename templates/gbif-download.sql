{% set exclusion_list = [
    's.coll.', 'Unknown', '[data not captured]', 'Anonymous', 'Collector unknown', 
    'Anon.', 'Collector(s): unknown', 'not recorded', '[no data available]', 
    'unknown', 'no consta', 'Collector unspecified', 's.col.', 'provisional entry', 
    's.n.', 'provisional entry s.n. [s.d.]', 'Anonymous collector s.n. [s.d.]', 
    '?', 'sin. coll.', 's.c.', 'NO DISPONIBLE', '(n/a)', 'REFLORA provisional entry', 
    'unclear', 'leg. ign.', '<td><td>', 'et al.', 'Mike Hopkins'
] %}

SELECT
    gbifid,
    institutionid,
    basisofrecord,
    catalognumber,
    recordnumber,
    recordnumber RLIKE '[0-9]' AS recordnumber_contains_numerals,
    (POSITION ("year" IN recordnumber) > 0) AS recordnumber_contains_year,  
    recordedby,
    CASE 
        WHEN recordedby IS NULL OR SIZE(recordedby) = 0 THEN FALSE 
        WHEN ARRAY_CONTAINS(ARRAY('{{ exclusion_list | join("', '") }}'), recordedby[0]) THEN FALSE 
        ELSE TRUE 
    END AS recordedby_has_personal_name,
    recordedbyid,
    georeferenceverificationstatus,
    othercatalognumbers,
    fieldnumber,
    fieldnumber RLIKE '[0-9]' AS fieldnumber_contains_numerals,
    eventdate,
    CASE WHEN eventdate LIKE '____-__-__%' THEN DATEDIFF(SUBSTR(eventdate, 1, 10), '1970-01-01') ELSE NULL END AS eventdate_day_offset,
    "year",
    "month",
    "day",
    verbatimeventdate,
    habitat,
    fieldnotes,
    eventremarks,
    countrycode,
    locality,
    verbatimlocality,
    decimallatitude,
    decimallongitude,
    scientificname,
    datasetkey,
    elevation,
    elevationaccuracy,
    nontaxonomicissue,
    mediatype,
    v_associatedmedia,
    hascoordinate,
    hasgeospatialissues,
    issequenced,
    institutionkey,
    collectionkey,
    isincluster
FROM
    occurrence
WHERE
    {# Use IN for multiple countries. Expects country_codes to be a list like ['PE', 'CO', 'BR'] #}
    occurrence.countrycode IN ('{{ country_codes | join("', '") }}')
    
    {# Phylum is now mandatory. Template will error if phylum_key is not provided. #} 
    AND CAST(occurrence.phylumkey AS INTEGER) = {{ phylum_key }}
    
    AND occurrence.basisofrecord IN ('PRESERVED_SPECIMEN', 'MATERIAL_CITATION')