#!/bin/bash
#
# data_source.sh - Unified data source management
#
# Handles fetching and managing sensor data across different environments
#
# Usage:
#   source data/data_source.sh
#   fetch_sensor_data <output_dir> [cutoff_date]

################################################################################
# Data Fetching
################################################################################

fetch_sensor_data() {
    local output_dir="$1"
    local cutoff_date="${2:-}"
    
    ensure_dir "$output_dir"
    timer_start "data_fetch"
    
    if [[ "$HAS_CSPOT" == "true" ]]; then
        if [[ -n "${cutoff_date}" ]]; then
            # Historical/cutoff mode: fetch N records AT OR BEFORE cutoff_date.
            # Exit code 2 from the loader means CSPOT doesn't store data that old.
            # Use || to prevent set -e from killing the script on non-zero exit.
            local cspot_exit=0
            _fetch_from_cspot "$output_dir" "$cutoff_date" || cspot_exit=$?

            if [[ $cspot_exit -eq 2 ]]; then
                _warn_historical_fallback "$cutoff_date"
                _fetch_from_historical "$output_dir" "$cutoff_date" || {
                    log_error "Historical fallback failed - no sensor data available"
                    log_error "  Cutoff : ${cutoff_date}"
                    log_error "  Options:"
                    log_error "    Set HISTORICAL_DATA_PATH in config.sh to the archive directory"
                    log_error "    Or remove DATA_CUTOFF_DATE to use live CSPOT data"
                    return 1
                }
            elif [[ $cspot_exit -ne 0 ]]; then
                log_error "CSPOT fetch failed (exit ${cspot_exit}) - aborting"
                log_error "Set HAS_CSPOT=false to use DATA_SOURCE_DIR fallback"
                return 1
            fi
        else
            # Online mode: any CSPOT failure is fatal
            _fetch_from_cspot "$output_dir" "$cutoff_date" || {
                log_error "CSPOT fetch failed and HAS_CSPOT=true - aborting"
                log_error "Set HAS_CSPOT=false to use DATA_SOURCE_DIR fallback"
                return 1
            }
        fi

        # Convert raw CSPOT format to CSV (always overwrite — sensor_data.txt is fresh each run)
        # (skipped when _fetch_from_historical already wrote sensor_out.csv directly)
        if [[ -f "$output_dir/sensor_data.txt" ]]; then
            _convert_cspot_to_csv "$output_dir/sensor_data.txt" "$output_dir/sensor_out.csv" || {
                log_error "Failed to convert CSPOT data to CSV"
                return 1
            }
        fi
    elif [[ -n "${DATA_SOURCE_DIR:-}" ]]; then
        _link_from_directory "$output_dir" "${DATA_SOURCE_DIR}"
    else
        log_error "No data source available"
        log_error "  Set HAS_CSPOT=true with CSPOT accessible, or"
        log_error "  Set DATA_SOURCE_DIR to directory with sensor data"
        return 1
    fi
    
    # Write fetch metadata so downstream phases can verify data against the cutoff
    local metadata_file="${output_dir}/data_fetch_info.json"
    local source_type
    if [[ "${HAS_CSPOT:-false}" == "true" ]]; then
        # Distinguish live CSPOT from historical fallback
        if [[ -f "${output_dir}/sensor_out.csv" && ! -f "${output_dir}/sensor_data.txt" ]]; then
            source_type="historical_archive"
        else
            source_type="cspot"
        fi
    else
        source_type="directory"
    fi
    {
        echo "{"
        echo "  \"fetch_timestamp\": \"$(date -Iseconds)\","
        echo "  \"cutoff_date\": $([ -n "${cutoff_date}" ] && echo "\"${cutoff_date}\"" || echo "null"),"
        echo "  \"source\": \"${source_type}\","
        echo "  \"cspot_endpoint\": \"${CSPOT_ENDPOINT:-}\","
        echo "  \"cspot_limit\": ${CSPOT_LIMIT:-50}"
        echo "}"
    } > "$metadata_file"
    log_info "Data fetch metadata saved to: ${metadata_file}"

    timer_end "data_fetch"
}

################################################################################
# CSPOT Fetching
################################################################################

_fetch_from_cspot() {
    local output_dir="$1"
    local cutoff_date="${2:-}"
    
    local cspot_endpoint="${CSPOT_ENDPOINT:-woof://128.111.45.61/davisstations/daviscupsout}"
    local cspot_limit="${CSPOT_LIMIT:-50}"
    
    log_info "Fetching sensor data from CSPOT..."
    log_info "  Endpoint: ${cspot_endpoint}"
    log_info "  Limit: ${cspot_limit} measurements"
    [[ -n "$cutoff_date" ]] && log_info "  Cutoff: ${cutoff_date}"
    
    # Use the load_historical_data.py script
    local loader_script="${WORK_DIR}/data/load_historical_data.py"
    
    if [[ -f "$loader_script" ]]; then
        local cmd_args="-W '${cspot_endpoint}' -o '${output_dir}' -n ${cspot_limit}"
        if [[ -n "$cutoff_date" ]]; then
            cmd_args="$cmd_args -c '$cutoff_date' --historical"
        fi

        # Capture output to parse RUN_DIR; use || to stay safe under set -e
        local loader_output loader_exit=0
        loader_output=$(eval "python3 '$loader_script' $cmd_args" 2>&1) || loader_exit=$?

        echo "$loader_output"

        if [[ $loader_exit -eq 2 ]]; then
            # CSPOT data too recent for the requested cutoff — propagate sentinel
            return 2
        elif [[ $loader_exit -ne 0 ]]; then
            log_error "CSPOT data loader failed (exit ${loader_exit})"
            log_error "  Check network connectivity to CSPOT endpoint"
            log_error "  Endpoint: ${cspot_endpoint}"
            return 1
        fi
        
        # Parse RUN_DIR from output
        local run_dir
        run_dir=$(echo "$loader_output" | grep "^RUN_DIR=" | cut -d'=' -f2)
        
        if [[ -n "$run_dir" && -d "$run_dir" ]]; then
            # Move sensor_data.txt to output_dir
            if [[ -f "$run_dir/sensor_data.txt" ]]; then
                mv "$run_dir/sensor_data.txt" "$output_dir/sensor_data.txt"
                log_info "Moved sensor data to: $output_dir/sensor_data.txt"
            fi
            # Clean up empty run directory
            rmdir "$run_dir" 2>/dev/null || true
        fi
    else
        # Check if senspot-get is available in various locations
        local senspot_path=""
        if command -v senspot-get &>/dev/null; then
            senspot_path="senspot-get"
        elif [[ -x ~/common/cspot/build/bin/senspot-get ]]; then
            senspot_path="$HOME/common/cspot/build/bin/senspot-get"
        elif [[ -x ~/bin/senspot-get ]]; then
            senspot_path="$HOME/bin/senspot-get"
        elif [[ -x /global/common/software/m5290/cspot/build/bin/senspot-get ]]; then
            senspot_path="/global/common/software/m5290/cspot/build/bin/senspot-get"
        fi
        
        if [[ -z "$senspot_path" ]]; then
            log_error "senspot-get not found and load_historical_data.py not available"
            log_error "  Install senspot-get or ensure loader script exists at:"
            log_error "  ${loader_script}"
            return 1
        fi
        
        log_warn "load_historical_data.py not found, using direct CSPOT fetch"
        if ! "$senspot_path" -W "$cspot_endpoint" > "${output_dir}/sensor_data.csv"; then
            log_error "senspot-get failed to fetch from CSPOT"
            return 1
        fi
    fi
    
    # Validate fetch - must have data files
    local csv_count=$(count_files "$output_dir" "*.csv")
    local txt_count=$(count_files "$output_dir" "*.txt")
    local total_count=$((csv_count + txt_count))
    
    if [[ $total_count -eq 0 ]]; then
        log_error "No data files fetched from CSPOT"
        log_error "  CSPOT may be unreachable or returned no data"
        return 1
    fi
    
    log_info "Fetched ${total_count} data file(s) from CSPOT"
}

################################################################################
# Historical Data Fallback
################################################################################

_warn_historical_fallback() {
    local cutoff_date="$1"
    log_warn "================================================================"
    log_warn "  !!! HISTORICAL DATA MODE ACTIVATED !!!"
    log_warn "  CSPOT does not store sensor data at or before: ${cutoff_date}"
    log_warn "  Falling back to LOCAL HISTORICAL DATA ARCHIVE."
    log_warn "  All downstream phases will use ARCHIVED sensor data."
    log_warn "================================================================"
}

_fetch_from_historical() {
    local output_dir="$1"
    local cutoff_date="$2"

    local hist_path="${HISTORICAL_DATA_PATH:-/local/home/liubov_kurafeeva/storage/cups_historical}"

    if [[ -z "${HISTORICAL_DATA_PATH:-}" ]]; then
        log_warn "HISTORICAL_DATA_PATH not set in config.sh — using default: ${hist_path}"
    fi

    if [[ ! -d "$hist_path" ]]; then
        log_error "Historical data path not found: ${hist_path}"
        log_error "  Set HISTORICAL_DATA_PATH in config.sh to the archive directory"
        return 1
    fi

    local loader="${WORK_DIR}/utils/load_from_historical.py"
    if [[ ! -f "$loader" ]]; then
        log_error "Historical loader not found: ${loader}"
        return 1
    fi

    local cspot_limit="${CSPOT_LIMIT:-50}"
    log_info "Loading from historical archive..."
    log_info "  Path   : ${hist_path}"
    log_info "  Cutoff : ${cutoff_date}"
    log_info "  Limit  : ${cspot_limit} records"

    python3 "$loader" \
        --data-dir    "$hist_path" \
        --output-file "${output_dir}/sensor_out.csv" \
        --cutoff-date "$cutoff_date" \
        --limit       "$cspot_limit" || {
        log_error "Historical data loader failed"
        return 1
    }

    local count
    count=$(wc -l < "${output_dir}/sensor_out.csv" 2>/dev/null || echo 1)
    count=$((count - 1))
    log_info "Historical fallback: loaded ${count} records to sensor_out.csv"
}

################################################################################
# CSPOT Data Conversion
################################################################################

_convert_cspot_to_csv() {
    local input_file="$1"
    local output_file="$2"
    
    log_info "Converting CSPOT raw data to CSV..."
    
    # Convert raw CSPOT format to CSV with columns: dt,windspeed,windavg,winddir
    # CSPOT format: field1:field2:...:field20 time: timestamp ip seq_no: seqno
    # Field 4 = windspeed (mph), Field 5 = windavg (mph), Field 6 = winddir (degrees)
    python3 "${WORK_DIR}/utils/convert_cspot_to_csv.py" "$input_file" "$output_file"

    local count=$(wc -l < "$output_file")
    count=$((count - 1))  # Subtract header

    if [[ $count -gt 0 ]]; then
        log_info "Converted ${count} records to CSV: ${output_file}"
        return 0
    else
        log_error "No records converted from CSPOT data"
        return 1
    fi
}

################################################################################
# Directory Linking (Pre-downloaded data)
################################################################################

_link_from_directory() {
    local output_dir="$1"
    local source_dir="$2"
    
    log_info "Using pre-downloaded data from: ${source_dir}"
    
    if [[ ! -d "$source_dir" ]]; then
        log_error "Data source directory not found: ${source_dir}"
        return 1
    fi
    
    # Try symlink first, fall back to copy
    if ln -sf "$source_dir"/* "$output_dir/" 2>/dev/null; then
        log_info "Created symlinks to source data"
    else
        log_info "Copying data from source directory..."
        cp -r "$source_dir"/* "$output_dir/"
    fi
    
    local csv_count=$(count_files "$output_dir" "*.csv")
    log_info "Linked ${csv_count} data file(s)"
}

################################################################################
# Data Exploration
################################################################################

explore_sensor_data() {
    local sensor_file="$1"
    local mode="${2:-stats}"
    
    require_file "$sensor_file" "Sensor data file"
    
    local explorer_script="${WORK_DIR}/data/explore_training_data.py"
    
    if [[ -f "$explorer_script" ]]; then
        python3 "$explorer_script" "$sensor_file" "$mode"
    else
        log_error "explore_training_data.py not found"
        return 1
    fi
}

################################################################################
# Data Validation
################################################################################

validate_sensor_data() {
    local data_dir="$1"
    
    # Look for sensor data files
    local sensor_file=""
    for fname in sensor_out.csv sensor_data.txt sensor_data.csv; do
        if [[ -f "${data_dir}/${fname}" ]]; then
            sensor_file="${data_dir}/${fname}"
            break
        fi
    done
    
    if [[ -z "$sensor_file" ]]; then
        log_error "No sensor data file found in: ${data_dir}"
        return 1
    fi
    
    # Check file has data
    local lines=$(wc -l < "$sensor_file")
    if [[ $lines -lt 2 ]]; then
        log_error "Sensor file is empty: ${sensor_file}"
        return 1
    fi
    
    log_info "Sensor data validated: ${sensor_file} (${lines} lines)"
    echo "$sensor_file"
}

################################################################################
# Utility Functions
################################################################################

get_sensor_data_path() {
    if [[ -n "${DATA_SOURCE_DIR:-}" ]]; then
        echo "${DATA_SOURCE_DIR}"
    else
        echo "${WORK_DIR}/data"
    fi
}
