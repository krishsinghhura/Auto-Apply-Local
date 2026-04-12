package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"

	"github.com/ledongthuc/pdf"
	"github.com/krishsinghhura/Auto-Apply-Local/config"
	"github.com/krishsinghhura/Auto-Apply-Local/services/llm"
	"github.com/krishsinghhura/Auto-Apply-Local/services/prompts"
	"github.com/krishsinghhura/Auto-Apply-Local/store"
)

func main() {
	cfg := config.LoadConfig()
	groqClient := llm.NewGroqClient(cfg)

	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "Healthy")
	})

	http.HandleFunc("/upload-resume", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Only POST method is allowed", http.StatusMethodNotAllowed)
			return
		}

		// 1. Get the uploaded PDF file
		file, _, err := r.FormFile("resume")
		if err != nil {
			http.Error(w, "Failed to read file from 'resume' field", http.StatusBadRequest)
			return
		}
		defer file.Close()

		// 2. Extract text from PDF
		log.Println("Extracting text from PDF...")
		extractedText, err := extractTextFromPDF(file)
		if err != nil {
			log.Printf("PDF Extraction error: %v", err)
			http.Error(w, "Failed to extract text from PDF", http.StatusInternalServerError)
			return
		}

		if len(extractedText) < 10 {
			http.Error(w, "PDF content is too small or blank", http.StatusBadRequest)
			return
		}

		// 3. Combine Resume with Conversion Prompt
		fullPrompt := fmt.Sprintf("%s\n\nRESUME TEXT:\n%s", prompts.CONVERSION_PROMPT, extractedText)

		// 4. Call Groq
		log.Println("Calling Groq to parse resume...")
		resp, err := groqClient.Chat("openai/gpt-oss-120b", fullPrompt)
		if err != nil {
			log.Printf("Groq error: %v", err)
			http.Error(w, "Failed to parse resume via Groq", http.StatusInternalServerError)
			return
		}

		// 5. Update the data store (in-memory)
		store.UpdateResume(resp)

		// 6. Overwrite store/resume.go to make it persistent
		goContent := fmt.Sprintf(`package store

var ParsedResume = %s
`, "`"+resp+"`")
		
		err = os.WriteFile("store/resume.go", []byte(goContent), 0644)
		if err != nil {
			log.Printf("Failed to persist resume: %v", err)
			http.Error(w, "Internal Error saving data", http.StatusInternalServerError)
			return
		}

		log.Println("PDF resume parsed and stored successfully!")
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{
			"message": "Resume uploaded, extracted, and stored successfully!",
			"status":  "success",
		})
	})

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Server starting on port %s...", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}

// Utility to extract text from a PDF stream
func extractTextFromPDF(file io.ReaderAt) (string, error) {
	// Need to calculate file size for the PDF reader
	// Since file is an io.ReaderAt from FormFile, we might need a seeker or a buffer
	// FormFile usually gives a *os.File or similar that implements io.ReaderAt
	
	// Create a temporary buffer to get the size
	buf := new(bytes.Buffer)
	size, err := io.Copy(buf, file.(io.Reader))
	if err != nil {
		return "", err
	}
	
	r, err := pdf.NewReader(bytes.NewReader(buf.Bytes()), size)
	if err != nil {
		return "", err
	}

	var output bytes.Buffer
	for i := 1; i <= r.NumPage(); i++ {
		p := r.Page(i)
		if p.V.IsNull() {
			continue
		}
		
		text, _ := p.GetPlainText(nil)
		output.WriteString(text)
		output.WriteString("\n")
	}

	return output.String(), nil
}
