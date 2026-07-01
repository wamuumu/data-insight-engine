PLAN (HL Upsert)

DEVICE_FULL = when rollover is detected, so basically when initial logs are in the future respect to the last logs.

UPSERT ON CONFLICT DO NOTHING STRATEGY: in a batch of logs, if a duplicate is detected, it is skipped

- The device is not yet registered into the db and we got a new file (either full or non-full):
    If not full:
        (1) Track the file into the db 
        (2) Register the device into the db
        (3) Insert the data into the db in normal order (top to bottom)
    If full:
        (1) Track the file into the db
        (2) Register the device into the db
        (3) Find first meaningful log (oldest log) and start inserting from there
        (4) When at the end of the file, start from the top and insert the remaining logs into the db

- The device is already registered into the db and we got another file for the same device:

    If not full:
        (1) Track the new file into the db
        (2) Take all the logs from the last file and change source_file_id to the new file id
        (3) Delete the last file from the db (to preserve memory)
        (4) Upsert the data into the db with the ON CONFLICT DO NOTHING STRATEGY in normal order (top to bottom)

    If full:
        (1) Track the new file into the db
        (2) Start from the last log inserted index (i.e., row inserted field in file tracker) and upsert new logs on last file
        (3) Start from the top and upsert the new logs into the new file


SELECT
    pg_size_pretty(pg_relation_size('history_log')) AS table_size,
    pg_size_pretty(pg_indexes_size('history_log')) AS indexes_size,
    pg_size_pretty(pg_total_relation_size('history_log')) AS total_size;


Discussion 01/07/2026:

    - 1st phase: rollover detection -> get HL Download most recent (cannot be 01/01/2000) -> sort rows with HL Download at end

    - 2nd phase: 
        - detect windows of invalid sessions. If multiple, consecutive and monotonic treat them as a single window, otherwise separate them.
        - correct timestamps of the logs with unknown timestamps (i.e., 01/01/2000), leaving the other untouched
        - backward and forward correction of timestamps if multiple consecutive invalid session are detected
            - correct first window, guess the others (in both directions)
            - all the guessed windows are wrapped inside two sentinel logs (START GUESSING DATA and END GUESSING DATA). 
                START GUESSING DATA gets the timestamp of the last valid log before the missing data, and END GUESSING DATA 
                gets the timestamp of the first valid log after the missing data
            - if the counter starts not from 0, then a missing ON message is detected, and we add MISSING LOGS (with value = # of missing logs)
            - all logs in between the two sentinel logs keep the 01/01/2000 timestamp
            - after the correction, we can calculate the TSS+C for each session:
                - added TSS + C field (unsigned bigint) to history_log table
                - for each session (start, stop), each row gets TSS + C = start_ts (millis from 01/01/2022) + counter
                - TSS + C can be used as a primary way to order the logs in the db
                - using TSS + C, we can save logs as they are, and adjust only the timestamps of bogus windows
    
    - 3rd phase:
        - Update DB schema: add TSS+C (bigint) and REAL_TS (bool) fields. REAL_TS is true if the timestamp is unchanged from raw, false otherwise. It must 
          be set to true for the sentinel logs (START MISSING DATA and END MISSING DATA), and also for the 01/01/2000 in between
        - upsert the logs into the db with ON CONFLICT DO NOTHING strategy (check uniqueness using device_id and TSS+C)
            

