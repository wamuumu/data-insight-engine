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

