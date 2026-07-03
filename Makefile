# Form GBIF occurrence download request URL from this base 
# and the download ID held as an environment variable GBIF_DOWNLOAD_ID
GBIF_OCCURRENCES_URL_BASE := https://api.gbif.org/v1/occurrence/download/request/
# As downloads are defined using countrycode, we also use a GBIF_DOWNLOAD_COUNTRYCODE
# environment variable to label the download and the prepared and clustered files, 
# e.g. occurrences-COUNTRYCODE-prepared.tsv

SHARED_DIR 			?=../geonomia-shared

DOWNLOAD_DIR  		:= downloads
DOWNLOAD_DIR_SHARED := $(SHARED_DIR)/downloads

DATA_DIR 			:= data
DATA_DIR_SHARED 	:= $(SHARED_DIR)/data

VENV_DIR      := .venv
VENV_SENTINEL := $(VENV_DIR)/.installed

USE_LOCAL_RECORDEDBY_PARSE ?= false

ifeq ($(OS),Windows_NT)
VENV_BIN      := $(VENV_DIR)/Scripts
SYSTEM_PYTHON ?= python
PYTHON        := $(VENV_BIN)/python.exe
PIP           := $(VENV_BIN)/pip.exe
else
VENV_BIN      := $(VENV_DIR)/bin
SYSTEM_PYTHON ?= python3
PYTHON        := $(VENV_BIN)/python
PIP           := $(VENV_BIN)/pip
endif

ifeq ($(USE_LOCAL_RECORDEDBY_PARSE),true)
  USE_LOCAL_RECORDEDBY_PARSE_ARGS := --use_local_recordedby_parse
  DWC_AGENT_GOLANG_DEP := $(VENV_BIN)/dwcagent-server
else
  USE_LOCAL_RECORDEDBY_PARSE_ARGS :=
  DWC_AGENT_GOLANG_DEP := 
endif

$(VENV_BIN)/dwcagent-server: 
	wget -O dwc_agent_golang.zip https://github.com/bionomia/dwc_agent_golang/archive/refs/heads/main.zip
	unzip dwc_agent_golang.zip -d dwc_agent_golang
	# Build the dwcagentgo binary and place in VENV_BIN
	cd dwc_agent_golang/dwc_agent_golang-main && go build -o dwcagent-server ./cmd/dwcagent-server
	cp dwc_agent_golang/dwc_agent_golang-main/dwcagent-server $(VENV_BIN)/dwcagent-server
	rm dwc_agent_golang.zip
	rm -rf dwc_agent_golang

DOWNLOADED_FILE  := $(DOWNLOAD_DIR)/occurrences-$(GBIF_DOWNLOAD_COUNTRYCODE).zip
PREPARED_FILE    := $(DATA_DIR)/occurrences-$(GBIF_DOWNLOAD_COUNTRYCODE)-prepared.tsv
CLUSTERED_STAGE1_FILE := $(DATA_DIR)/occurrences-$(GBIF_DOWNLOAD_COUNTRYCODE)-clustered-stage1.tsv
SUMMARY_STAGE1_FILE := $(DATA_DIR)/occurrences-$(GBIF_DOWNLOAD_COUNTRYCODE)-clustered-stage1-summary.tsv
CLUSTERED_STAGE2_FILE := $(DATA_DIR)/occurrences-$(GBIF_DOWNLOAD_COUNTRYCODE)-clustered-stage2.tsv
SUMMARY_STAGE2_FILE := $(DATA_DIR)/occurrences-$(GBIF_DOWNLOAD_COUNTRYCODE)-clustered-stage2-summary.tsv
JOINED_FILE := $(DATA_DIR)/occurrences-$(GBIF_DOWNLOAD_COUNTRYCODE).tsv

DOWNLOAD_SCRIPT  := request_download.py
DOWNLOAD_TEMPLATE_FILE = templates/gbif-download.sql
PREPARE_SCRIPT   := prepare.py
CLUSTER_SCRIPT   := cluster.py
SUMMARISE_SCRIPT  := summarise.py
JOIN_SCRIPT := join.py

# Comma-separated list of columns to read from the GBIF SQL download for the prepare step 
# MUST include base data for later clustering step:
#	recordedBy
#	recordNumber
#	fieldNumber
#	eventDate
# SHOULD include helper columns pre-computed in SQL query:
# 	recordnumber_contains_numerals
# 	recordnumber_contains_year
# 	recordedby_has_personal_name
# 	fieldnumber_contains_numerals
# 	eventdate_day_offset    
PREPARE_COLS_REQD	 := gbifid,recordedby,recordnumber,fieldnumber,eventdate,year
PREPARE_COLS_HELPER := recordnumber_contains_numerals,recordnumber_contains_year,recordedby_has_personal_name,fieldnumber_contains_numerals,eventdate_day_offset
	
GEOSPATIAL_COLS := hascoordinate,hasgeospatialissues,countrycode,decimallatitude,decimallongitude,locality

CLUSTER_STAGE1_BATCH_COL := recordedby_first_familyname
CLUSTER_STAGE1_CLUSTER_COLS := recordnumber_mainnumber,eventdate_day_offset
CLUSTER_STAGE1_CLUSTERID_COL := cluster_stage1_id

CLUSTER_STAGE2_BATCH_COL := $(CLUSTER_STAGE1_CLUSTERID_COL)
CLUSTER_STAGE2_CLUSTER_COLS := decimallatitude,decimallongitude,eventdate_day_offset
CLUSTER_STAGE2_CLUSTERID_COL := cluster_stage2_id

.PHONY: all install download prepare cluster clean distclean

## Create virtualenv and install dependencies
$(VENV_SENTINEL): requirements.txt
	$(SYSTEM_PYTHON) -m venv $(VENV_DIR)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	touch $(VENV_SENTINEL)

install: $(VENV_SENTINEL)

downloadreq: $(VENV_SENTINEL) $(DOWNLOAD_SCRIPT)
	$(PYTHON) $(DOWNLOAD_SCRIPT) $(DOWNLOAD_TEMPLATE_FILE) --countrycodes $(GBIF_DOWNLOAD_COUNTRYCODE) 

## Download the GBIF occurrences ZIP
$(DOWNLOADED_FILE): $(VENV_SENTINEL)
	mkdir -p $(DOWNLOAD_DIR)
	wget -O $@ "$(GBIF_OCCURRENCES_URL_BASE)$(GBIF_DOWNLOAD_ID).zip"

download: $(DOWNLOADED_FILE)

## Prepare the downloaded occurrence TSV (process recordedBy and recordNumber)
$(PREPARED_FILE): $(PREPARE_SCRIPT) $(DOWNLOADED_FILE) $(VENV_SENTINEL) $(DWC_AGENT_GOLANG_DEP)
	mkdir -p $(DATA_DIR)
	if [ "$(USE_LOCAL_RECORDEDBY_PARSE)" = "true" ]; then \
		set -eu; \
		$(VENV_BIN)/dwcagent-server & \
		SERVER_PID=$$!; \
		trap 'kill $$SERVER_PID 2>/dev/null || true; wait $$SERVER_PID 2>/dev/null || true' EXIT; \
		curl --fail --retry 20 --retry-delay 1 --retry-connrefused "http://127.0.0.1:7654/health"; \
		$(PYTHON) $(PREPARE_SCRIPT) \
			$(USE_LOCAL_RECORDEDBY_PARSE_ARGS) \
			$(DOWNLOADED_FILE) $@; \
	else \
		$(PYTHON) $(PREPARE_SCRIPT) \
			$(DOWNLOADED_FILE) $@; \
	fi

prepare: $(PREPARED_FILE)

# Stage 1 cluster the prepared occurrence TSV 
# BATCH by recordedBy_first_familyName
# CLUSTER on recordNumber and eventdateoffset
$(CLUSTERED_STAGE1_FILE): $(CLUSTER_SCRIPT) $(PREPARED_FILE) $(VENV_SENTINEL)
	mkdir -p $(DATA_DIR)
	$(PYTHON) $(CLUSTER_SCRIPT) --id_col "gbifid" \
		--columns "$(CLUSTER_STAGE1_CLUSTER_COLS)"  \
		--output_all_records \
		--batch_col_name "$(CLUSTER_STAGE1_BATCH_COL)" \
		--additional_col_names "recordedby_team_familynames" \
		--eligible_flag_columns "eventdate_eligible,recordnumber_eligible,recordedby_eligible" \
		--cluster_id_col "$(CLUSTER_STAGE1_CLUSTERID_COL)" $(PREPARED_FILE) $@

cluster_stage1: $(CLUSTERED_STAGE1_FILE)

$(SUMMARY_STAGE1_FILE): $(SUMMARISE_SCRIPT) $(DOWNLOADED_FILE) $(PREPARED_FILE) $(CLUSTERED_STAGE1_FILE)
	$(PYTHON) $(SUMMARISE_SCRIPT) \
		--cluster_id_col "$(CLUSTER_STAGE1_CLUSTERID_COL)" \
		$(DOWNLOADED_FILE) $(PREPARED_FILE) $(CLUSTERED_STAGE1_FILE) $@

summary_stage1: $(SUMMARY_STAGE1_FILE)

all: summary_stage1 citation join

deploy: summary_stage1 citation join
	@echo "Deploying to shared directory $(SHARED_DIR)"
	mkdir -p $(DOWNLOAD_DIR_SHARED)
	cp $(DOWNLOADED_FILE) $(DOWNLOAD_DIR_SHARED)
	mkdir -p $(DATA_DIR_SHARED)
	cp $(PREPARED_FILE) $(DATA_DIR_SHARED)
	cp $(SUMMARY_STAGE1_FILE) $(DATA_DIR_SHARED)
	cp $(CITATION_FILE) $(DATA_DIR_SHARED)
	cp $(JOINED_FILE) $(DATA_DIR_SHARED)

CITATION_FILE := data/citation.json
citation: $(CITATION_FILE)

$(CITATION_FILE): $(VENV_SENTINEL) get_citation.py
	$(PYTHON) get_citation.py \
		--download-id "$(GBIF_DOWNLOAD_ID)" \
		--output "$@"

$(JOINED_FILE): $(VENV_SENTINEL) join.py $(DOWNLOADED_FILE) $(CLUSTERED_STAGE1_FILE)
	mkdir -p $(DATA_DIR)
	$(PYTHON) $(JOIN_SCRIPT) $(DOWNLOADED_FILE) $(CLUSTERED_STAGE1_FILE) $@
join: $(JOINED_FILE)

visualise_stage1: $(SUMMARY_STAGE1_FILE)
	$(PYTHON) visualise.py $(SUMMARY_STAGE1_FILE)

# Stage 2 cluster the clustered occurrence TSV 
# BATCH by cluster_id
# CLUSTER on decimalLatitude, decimalLongitude, and eventdateoffset
$(CLUSTERED_STAGE2_FILE): $(CLUSTER_SCRIPT) $(CLUSTERED_STAGE1_FILE) $(VENV_SENTINEL)
	mkdir -p $(DATA_DIR)
	$(PYTHON) $(CLUSTER_SCRIPT) \
		--columns "$(CLUSTER_STAGE2_CLUSTER_COLS)" \
		--batch_col_name "$(CLUSTER_STAGE2_BATCH_COL)" \
		--cluster_id_col "$(CLUSTER_STAGE2_CLUSTERID_COL)" $(CLUSTERED_STAGE1_FILE) $@
	
cluster_stage2: $(CLUSTERED_STAGE2_FILE)

## Remove prepared and clustered TSVs
clean:
	rm -f $(PREPARED_FILE) $(CLUSTERED_STAGE1_FILE) $(CLUSTERED_STAGE2_FILE)
	rm -rf $(DATA_DIR)

## Remove everything including the raw download
sterilise: clean
	rm -f $(DOWNLOADED_FILE)
	rm -rf $(DOWNLOAD_DIR)

## Remove everything including the raw download and the virtualenv
distclean: sterilise
	rm -rf $(VENV_DIR)
