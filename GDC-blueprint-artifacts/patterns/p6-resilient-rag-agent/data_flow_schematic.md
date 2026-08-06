Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# P6 Resilient RAG Agent - Data Flow Schematic

This document illustrates the end-to-end data flow for the Resilient RAG Agent, from file ingestion to user query.

```mermaid
graph TD
    %% Nodes
    User([User])
    
    subgraph "Frontend / Client"
        GUI[React Frontend]
        CLI[gcloud / gsutil]
    end
    
    subgraph "Google Cloud Storage"
        GCS[Input Bucket\ngs://raw-docs-...]
    end
    
    subgraph "GKE Cluster (Namespace: test-project)"
        subgraph "Ingestion Layer"
            IngestJob["Ingestion CronJob\n(rag-ingest)"]
        end
        
        subgraph "Serving Layer"
            QuerySvc["Query Service\n(FastAPI)"]
        end
        
        subgraph "Data Layer"
            DB[(Postgres + pgvector)]
        end
    end
    
    subgraph "Google Cloud Services (External)"
        Gemini[Vertex AI\nGemini 2.5 Flash]
    end

    %% Flows
    
    %% 1. Upload Flow
    User -- "1. Upload File (Drag & Drop)" --> GUI
    GUI -- "2. Upload (Direct)" --> GCS
    User -- "1b. Batch Upload" --> CLI
    CLI -- "2b. Upload" --> GCS
    
    %% 2. Ingestion Flow
    IngestJob -- "3. Poll/Read New Files" --> GCS
    IngestJob -- "4. Process (OCR/Transcribe/Translate)" --> Gemini
    Gemini -- "5. Return Text" --> IngestJob
    IngestJob -- "6. Generate Embedding" --> IngestJob
    IngestJob -- "7. Store Vector & Content" --> DB
    
    %% 3. Query Flow
    User -- "8. Ask Question" --> GUI
    GUI -- "9. POST /query" --> QuerySvc
    QuerySvc -- "10. Vector Search (Similarity)" --> DB
    DB -- "11. Return Relevant Context" --> QuerySvc
    QuerySvc -- "12. Generate Answer (with Grounding)" --> Gemini
    Gemini -- "13. Return Answer" --> QuerySvc
    QuerySvc -- "14. Return Response + Citation" --> GUI
    GUI -- "15. Display Answer & Source" --> User

    %% Styling
    style User fill:#f9f,stroke:#333,stroke-width:2px
    style Gemini fill:#4285F4,stroke:#333,stroke-width:2px,color:white
    style DB fill:#336791,stroke:#333,stroke-width:2px,color:white
    style GCS fill:#EA4335,stroke:#333,stroke-width:2px,color:white
    linkStyle 1,3,4,5,6,7,10,13,14,15 stroke:blue
```

## Workflow Description

### 1. Data Ingestion (Async)
1.  **Upload**: Users upload files (PDF, Images, Audio) via the React GUI or batch upload tools (`gsutil`) directly to the **GCS Input Bucket**.
2.  **Processing**: The **Ingestion CronJob** runs periodically (every 15 mins) or can be triggered manually.
3.  **Multimodal Transformation**: The Ingest Job reads files from GCS and sends them to **Gemini 2.5 Flash**.
    *   **Audio**: Transcribed to text.
    *   **Images**: OCR / Described as text.
    *   **PDF**: Text extracted.
    *   **Translation**: Non-English text is translated to English.
4.  **Storage**: The extracted text is embedded (vectorized) and stored in **Postgres (pgvector)** along with the original filename.

### 2. Query & Retrieval (Real-time)
1.  **Search**: The user asks a question via the **React Frontend**.
2.  **Retrieval**: The **Query Service** embeds the question and performs a similarity search in **Postgres** to find the most relevant document chunks.
3.  **Generation**: The retrieved context + user question is sent to **Gemini 2.5 Flash** with a strict system prompt ("Answer using ONLY the provided context").
4.  **Response**: The answer and the source document filename are returned to the user.
