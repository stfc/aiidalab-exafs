#!/usr/bin/env bash
# Start the AiiDA REST API inside the AiiDAlab container.
# Binds to 0.0.0.0 so it can be reached from a proxy container.

. /opt/conda/etc/profile.d/conda.sh
conda activate base

pkill -f "verdi restapi" 2>/dev/null
sleep 1

nohup verdi restapi --hostname 0.0.0.0 --port 5000 > /tmp/aiida-restapi.log 2>&1 &
echo $! > /tmp/aiida-restapi.pid

sleep 2
# Verify it started
if ! ps -p "$(cat /tmp/aiida-restapi.pid)" > /dev/null 2>&1; then
    cat /tmp/aiida-restapi.log
    exit 1
fi
