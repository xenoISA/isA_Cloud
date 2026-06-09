FROM alpine:3.19
RUN apk add --no-cache bash curl jq
COPY sync_routes.sh /scripts/sync_routes.sh
RUN chmod +x /scripts/sync_routes.sh
CMD ["bash","/scripts/sync_routes.sh"]
