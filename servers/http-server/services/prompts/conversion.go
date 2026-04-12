package prompts

const CONVERSION_PROMPT = `Extract every detail from the shared resume and format it as a valid JSON object. 
The object should have the following keys:
- "personal_info": { "name", "email", "phone", "linkedin", "github", "website" }
- "summary": (The professional Summary/Bio)
- "experience": [ { "company", "role", "duration", "location", "description" } ]
- "education": [ { "institution", "degree", "field", "duration" } ]
- "projects": [ { "name", "description", "links" } ]
- "skills": [ { "category", "items" } ]

Output ONLY the raw JSON string without any explanation or markdown formatting. 
If a section is missing, return an empty list or null.`
