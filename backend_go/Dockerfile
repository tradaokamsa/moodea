# Start from the official Golang image
FROM golang:1.21-alpine AS builder

WORKDIR /app

COPY go.mod .
COPY go.sum .
RUN go mod download

COPY . .

RUN go build -o moodea-go-backend main.go

# Use a minimal image for running
FROM alpine:latest
WORKDIR /root/

COPY --from=builder /app/moodea-go-backend .

EXPOSE 8080

CMD ["./moodea-go-backend"] 