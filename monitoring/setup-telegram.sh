#!/bin/sh
# Контакт Telegram (@mvpcode_alarm_bot) и маршрут всех оповещений к нему.
# По просьбе Павла 13.10: без сообщений «НОРМА», повтор той же тревоги не чаще раза в сутки.
# Запускать на сервере из каталога проекта после старта Grafana; повторный запуск безопасен.
set -eu
. ./monitoring/grafana.env
IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{break}}{{end}}' catalog-magnitola-grafana-1)
API="http://$IP:3000/grafana/api/v1/provisioning"
AUTH="admin:$GF_SECURITY_ADMIN_PASSWORD"
MSG='{{ range .Alerts }}{{ if eq .Status "firing" }}ТРЕВОГА{{ else }}НОРМА{{ end }}: <b>{{ .Labels.alertname }}</b>
{{ .Annotations.summary }}
{{ end }}'
BODY=$(python3 -c 'import json,sys; print(json.dumps({"uid":"telegram","name":"telegram","type":"telegram",
  "disableResolveMessage":True,
  "settings":{"bottoken":sys.argv[1],"chatid":sys.argv[2],"parse_mode":"HTML","message":sys.argv[3]}}))' \
  "$TELEGRAM_BOT_TOKEN" "$TELEGRAM_CHAT_ID" "$MSG")
H='Content-Type: application/json'
code=$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" -H "$H" -H 'X-Disable-Provenance: true' -X PUT "$API/contact-points/telegram" -d "$BODY")
[ "$code" = 202 ] || code=$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" -H "$H" -H 'X-Disable-Provenance: true' -X POST "$API/contact-points" -d "$BODY")
echo "контакт telegram: $code"
curl -s -o /dev/null -w 'маршрут: %{http_code}\n' -u "$AUTH" -H "$H" -H 'X-Disable-Provenance: true' -X PUT "$API/policies" \
  -d '{"receiver":"telegram","group_by":["alertname"],"group_wait":"30s","group_interval":"5m","repeat_interval":"24h"}'
