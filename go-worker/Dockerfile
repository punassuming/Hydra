FROM golang:1.24-alpine AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/hydra-go-worker ./main.go

FROM alpine:3.20

RUN apk add --no-cache ca-certificates bash git python3 openssh-client rsync

WORKDIR /app
COPY --from=build /out/hydra-go-worker /usr/local/bin/hydra-go-worker

ENTRYPOINT ["hydra-go-worker"]
