package config

import (
	"log"
	"os"

	"github.com/joho/godotenv"
)

type Config struct {
	GroqAPIKey string
}

func LoadConfig() *Config {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, loading from environment variables")
	}

	apiKey := os.Getenv("GROQ_API_KEY")
	if apiKey == "" {
		log.Fatal("GROQ_API_KEY not found in environment")
	}

	return &Config{
		GroqAPIKey: apiKey,
	}
}
