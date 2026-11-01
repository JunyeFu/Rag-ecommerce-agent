# Official prebuilt distributions are unavailable (401/410 on 2026-10-09).
# Build the exact approved upstream release; keep its AGPL license and source URL.
FROM golang:1.24.2-bookworm AS build
WORKDIR /build
RUN git clone --depth 1 --branch RELEASE.2025-04-22T22-12-26Z https://github.com/minio/minio.git
WORKDIR /build/minio
RUN test "$(git rev-parse HEAD)" = "0d7408fc9969caf07de6a8c3a84f9fbb10a6739e"
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    mkdir -p /go/pkg/mod/cache/download/github.com/klauspost/compress/@v && \
    curl --fail --location --retry 2 https://proxy.golang.org/github.com/klauspost/compress/@v/v1.18.0.zip \
      --output /go/pkg/mod/cache/download/github.com/klauspost/compress/@v/v1.18.0.zip && \
    MINIO_RELEASE=RELEASE CGO_ENABLED=0 go build -trimpath -ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go 2025-04-22T22:12:26Z)" -o /minio . && \
    go mod verify

FROM redis:8.2.2-alpine
LABEL org.opencontainers.image.source="https://github.com/minio/minio/tree/RELEASE.2025-04-22T22-12-26Z" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="0d7408fc9969caf07de6a8c3a84f9fbb10a6739e"
COPY --from=build /minio /usr/local/bin/minio
COPY --from=build /build/minio/LICENSE /usr/share/licenses/minio/LICENSE
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
