package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/krishsinghhura/Auto-Apply-Local/config"
	"github.com/krishsinghhura/Auto-Apply-Local/services/llm"
	"github.com/krishsinghhura/Auto-Apply-Local/services/mailing"
	"github.com/krishsinghhura/Auto-Apply-Local/services/prompts"
	"github.com/krishsinghhura/Auto-Apply-Local/store"
	"github.com/ledongthuc/pdf"
)

type GeneratorRequest struct {
	CompanyName string `json:"company_name"`
	JD          string `json:"jd"`
}

type Person struct {
	Name     string `json:"name"`
	Headline string `json:"headline"`
	Email    string `json:"email"`
}

type FinderResponse struct {
	Results []Person `json:"results"`
}

type GeneratedResult struct {
	Person Person `json:"person"`
	Email  string `json:"email_content"`
	Status string `json:"status"`
	Error  string `json:"error,omitempty"`
}

func main() {
	cfg := config.LoadConfig()
	groqClient := llm.NewGroqClient(cfg)
	mailingService := mailing.NewMailingService(groqClient)

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

	http.HandleFunc("/generate-emails", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Only POST method is allowed", http.StatusMethodNotAllowed)
			return
		}

		var req GeneratorRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		// 1. Hit the Finder API
		finderURL := fmt.Sprintf("http://127.0.0.1:5001/find-people?company=%s&max_results=10&enrich_email=true", req.CompanyName)
		log.Printf("Hitting Finder API: %s", finderURL)

		resp, err := http.Get(finderURL)
		if err != nil {
			log.Printf("Finder API error: %v", err)
			http.Error(w, "Failed to connect to Finder API", http.StatusInternalServerError)
			return
		}
		defer resp.Body.Close()

		var finderRes FinderResponse
		if err := json.NewDecoder(resp.Body).Decode(&finderRes); err != nil {
			log.Printf("Failed to decode Finder response: %v", err)
			http.Error(w, "Invalid response from Finder API", http.StatusInternalServerError)
			return
		}

		// 2. Process in parallel
		log.Printf("Found %d people, generating emails...", len(finderRes.Results))
		resultsChan := make(chan GeneratedResult, len(finderRes.Results))
		var wg sync.WaitGroup

		for _, p := range finderRes.Results {
			wg.Add(1)
			go func(person Person) {
				defer wg.Done()

				var content string
				var genErr error
				maxRetries := 3

				for attempt := 1; attempt <= maxRetries; attempt++ {
					content, genErr = mailingService.GenerateEmail(req.JD, person.Headline)
					if genErr == nil {
						break
					}

					log.Printf("[RETRY] Attempt %d failed for %s: %v", attempt, person.Name, genErr)
					if attempt < maxRetries {
						time.Sleep(2 * time.Second) // Basic backoff
					}
				}

				if genErr != nil {
					resultsChan <- GeneratedResult{
						Person: person,
						Status: "failed",
						Error:  genErr.Error(),
					}
				} else {
					resultsChan <- GeneratedResult{
						Person: person,
						Email:  content,
						Status: "success",
					}
				}
			}(p)
		}

		wg.Wait()
		close(resultsChan)

		var finalResults []GeneratedResult
		for res := range resultsChan {
			finalResults = append(finalResults, res)
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(finalResults)
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
