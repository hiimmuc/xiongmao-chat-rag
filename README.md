# Gehihi

Private AI chat over your own documents. Upload PDF, text or Markdown files into a project, ask questions, and get streamed answers that cite the file, page and passage they come from.

## Features

- **Chat:** streamed answers, stop, copy, regenerate, branch from any answer, title search, rename, delete. Tokens and estimated cost under each answer.
- **Projects:** each project has its own documents, chats and search index. Nothing crosses projects.
- **Free chats:** chats outside any project, using only documents uploaded into that chat.
- **Documents:** text PDF, TXT and Markdown up to 10 MiB and 100 pages, by button or drag and drop. Status, retry, rename, download, delete.
- **Citations:** every answer shows file, page and snippet.
- **Models:** pick from the chat models your provider key offers (Gemini, optional OpenAI), narrowed by a shortlist.
- **Usage:** requests, tokens and estimated cost by day and by model.
- **Settings:** light, dark or system mode, themes, fonts, response styles, personal API keys.
- **Accounts:** email and password sign-up and sign-in, password change, profile, account deletion.

## Main workflow

1. Sign up and sign in. The browser keeps a short-lived access token in memory and a refresh cookie.
2. Create a project and upload documents.
3. The API stores each file and queues a job. The worker extracts the text, splits it into chunks, embeds them with Gemini and saves the vectors in PostgreSQL (pgvector). The document shows Ready.
4. Ask a question. The API finds the most relevant chunks with pgvector, sends them with the question to the model, and streams the answer back as Server-Sent Events.
5. The answer is saved with its citations, tokens and estimated cost.

## Stack

React + TypeScript (Vite), FastAPI + one background worker (Python 3.12), PostgreSQL 16 with pgvector, Gemini for chat and embeddings. Hosted on AWS (production) and one GCP VM (staging).

The source code is on the `staging` branch. The assignment brief is in [docs/assignment.pdf](docs/assignment.pdf).
