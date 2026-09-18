Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Gemma Client Implementation Plan

## Overview
This pattern (`gemma-client`) implements a multi-user chatbot wrapper around Google's Gemma models. Unlike Pattern 6 (RAG), this pattern focuses on **direct context loading**, where user-uploaded documents (Text, PDF, Images) are loaded directly into the model's context window for grounding.

## Architecture

### Components
1.  **Frontend (React + Vite)**:
    *   Based on P6's frontend.
    *   **Features**:
        *   Chat Interface (Streaming responses).
        *   Model Selector (Dropdown).
        *   File Manager (Upload, Delete, Select for Chat).
        *   Multi-User Support (Mock Login for Dev).
        *   "Only use sources" toggle.
2.  **Backend (FastAPI)**:
    *   **API Endpoints**:
        *   `/chat`: Handles Gemma interaction.
        *   `/upload`: Uploads files to GCS.
        *   `/files`: Lists user/shared files.
        *   `/history`: Manages chat history.
    *   **Logic**:
        *   **Context Management**: Checks token count of selected files. If > limit, rejects with helpful message.
        *   **Gemma Integration**: Uses Vertex AI SDK (GCP) or OpenAI-compatible endpoint (GDC) to call Gemma Inference Gateway.
        *   **Translation**: Handles non-English text via Gemma's native capabilities.
3.  **Database (PostgreSQL)**:
    *   Stores Chat History (Sessions, Messages).
    *   Stores File Metadata (Owner, Path, Type).
4.  **Storage (GCS)**:
    *   Stores raw uploaded files (PDFs, Images, Text).
    *   Structure: `gs://<bucket>/shared/` and `gs://<bucket>/users/<user_id>/`.

### Data Flow
1.  **Upload**: User uploads file -> Backend -> GCS (Private/Shared path). Metadata -> Postgres.
2.  **Chat**:
    *   User selects Model + Files + Enters Message.
    *   Backend fetches File Content from GCS.
    *   Backend constructs Prompt (System Prompt + File Content + Chat History + User Message).
    *   Backend calls Gemma Inference Gateway API.
    *   Response streamed to Frontend.
    *   Chat History saved to Postgres.

## Deployment Structure
Follows the standard GDC Blueprint pattern:
*   `manifests/gcp`: GCP-specific manifests (for Stepping Stone).
*   `manifests/gdc`: GDC-specific manifests (Air-gapped).
*   `scripts/`: Build and setup scripts.
*   `tests/`: Validation and verification scripts.

## Implementation Steps

### Phase 1: Scaffolding & Setup
1.  **Initialize Directory**: Create `gemma-client` based on `template-pattern`.
2.  **Define Schema**: Create `init.sql` for Postgres (Chats, Messages, Files).
3.  **Setup Manifests**:
    *   `statefulset-postgres.yaml` (Copy from P1/P6).
    *   `deployment-backend.yaml`.
    *   `deployment-frontend.yaml`.
    *   `service-*.yaml`.

### Phase 2: Backend Development
1.  **Auth Middleware**: Implement `X-User-ID` header parsing (from P6).
2.  **File Management**:
    *   Implement GCS upload/download.
    *   Implement PDF/Image text extraction.
3.  **Gemma Wrapper**:
    *   Implement `ChatSession` logic.
    *   Implement Token Counting.
    *   Implement "Only use sources" system instruction.

### Phase 3: Frontend Development
1.  **UI Layout**: Sidebar (History + Files), Main (Chat), Top (Model Selector).
2.  **State Management**: Handle selected files, selected model.
3.  **Chat Logic**: Handle streaming response, markdown rendering.

### Phase 4: Testing & Verification
1.  **GCP Stepping Stone**:
    *   Deploy to GKE (Standard/Autopilot).
    *   Use Real GCS + Real Gemma.
2.  **Validation**:
    *   Test Multi-user isolation (User A can't see User B's files).
    *   Test Large File rejection.
    *   Test "Only use sources" strictness.

## Constraints & Requirements Checklist
- [ ] **Pattern Name**: `gemma-client`.
- [ ] **Models**: Gemma Only.
- [ ] **Multi-User**: Yes (Pattern 6 approach).
- [ ] **RAG**: No (Direct Context).
- [ ] **File Types**: Text, PDF, Images.
- [ ] **Translation**: Yes (Native).
- [ ] **Environment**: GCP Stepping Stone -> GDC Air-gapped.
- [ ] **Execution**: Commands run on Workstation (Copy/Paste flow).

## Next Steps
1.  Approve this plan.
2.  Begin scaffolding.
