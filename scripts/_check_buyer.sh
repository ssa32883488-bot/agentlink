#!/bin/bash
systemctl is-active agentlink-buyer-a
sleep 2
curl -sk -o /tmp/m.json -w "http=%{http_code}\n" http://127.0.0.1:8010/api/flow/metrics
curl -sk -o /tmp/m2.json -w "https=%{http_code}\n" https://127.0.0.1:8010/api/flow/metrics
head -c 200 /tmp/m2.json; echo
tail -n 40 /var/log/agentlink/buyer-a.log
