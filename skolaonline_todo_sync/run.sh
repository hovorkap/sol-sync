#!/usr/bin/with-contenv bashio

bashio::log.info "Starting SkolaOnline ToDo Sync..."
exec python3 /app/main.py
