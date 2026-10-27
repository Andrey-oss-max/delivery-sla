#!/bin/sh
# Клиент mysql под пользователем приложения: docker compose exec db sql -e "SELECT ..."
# Пароль берётся из окружения контейнера, в командной строке и истории его нет.
MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u"$MYSQL_USER" --table "$MYSQL_DATABASE" "$@"
