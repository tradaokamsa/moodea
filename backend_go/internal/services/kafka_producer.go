package services

import (
	"sync"
	"log"
	"os"
	"strings"
	"time"
	"encoding/json"

	"github.com/IBM/sarama"
)

// UserEvent represents a user event sent to Kafka
type UserEvent struct {
	UserID    string                 `json:"user_id"`
	EventType string                 `json:"event_type"`
	Timestamp int64                  `json:"timestamp"`
	Data      map[string]interface{} `json:"data"`
}

// InteractionEvent represents an interaction event sent to Kafka
type InteractionEvent struct {
	UserID          string                 `json:"user_id"`
	TrackID         string                 `json:"track_id"`
	InteractionType string                 `json:"interaction_type"`
	Score           int                    `json:"score"`
	SessionID       string                 `json:"session_id"`
	Timestamp       int64                  `json:"timestamp"`
	Context         map[string]interface{} `json:"context"`
}

var (
	kafkaProducer 		sarama.SyncProducer
	kafkaProducerOnce   sync.Once
	kafkaProducerErr 	error
)

const kafkaTopicUserEvents = "user-events"
const kafkaTopicInteractionEvents = "interaction-events"

// InitializeKafkaProducer initializes the Kafka producer
func InitializeKafkaProducer() error {
	kafkaProducerOnce.Do(func() {
		brokersEnv := os.Getenv("KAFKA_BROKERS")
		if brokersEnv == "" {
			log.Println("[kafka] KAFKA_BROKERS not set; producer disabled (stub mode)")
			return
		}

		brokers := strings.Split(brokersEnv, ",")
		config := sarama.NewConfig()
		config.Producer.Return.Successes = true
		config.Producer.RequiredAcks = sarama.WaitForAll
		config.Producer.Retry.Max = 3

		producer, err := sarama.NewSyncProducer(brokers, config)
		if err != nil {
			kafkaProducerErr = err
			log.Printf("[kafka] Failed to create producer: %v", err)
			return
		}
		kafkaProducer = producer
		log.Println("[kafka] Producer initialized")
	})
	return kafkaProducerErr
}

func produce(topic string, payload interface{}) error {
	// Stub mode: if producer not initialized, just log.
	if kafkaProducer == nil {
		body, _ := json.Marshal(payload)
		log.Printf("[kafka stub] topic=%s payload=%s", topic, string(body))
		return nil
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	msg := &sarama.ProducerMessage{
		Topic: topic,
		Value: sarama.ByteEncoder(body),
		Timestamp: time.Now(),
	}
	_, _, err = kafkaProducer.SendMessage(msg)
	return err
}

// ProduceUserEvent sends user-events to Kafka
func ProduceUserEvent(event *UserEvent) error {
	return produce(kafkaTopicUserEvents, event)
}

// ProduceInteractionEvent sends interaction-events to Kafka
func ProduceInteractionEvent(event *InteractionEvent) error {
	return produce(kafkaTopicInteractionEvents, event)
}

