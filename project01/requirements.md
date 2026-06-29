# General-Domain AI Learning Assistant Requirements

## 1. Project Scope

This project is a demonstration-oriented Web AI learning assistant for general-domain learning. It should not be limited to a fixed subject area. Users can create personal knowledge bases, upload learning materials, start learning sessions, ask questions, receive learning paths, complete quizzes, and get adaptive feedback from an Agent.

The implementation priority is backend and Agent capability. The frontend should provide a clear learning-platform style interface, but the main value of the project is the AI application workflow.

## 2. Confirmed Product Requirements

### 2.1 User System

- The system supports multiple users.
- The implementation should remain simple because this is a demonstration project.
- Users can register and log in.
- Registration only requires account and password.
- Different users must be isolated from each other.
- No administrator role is required.
- All normal users have the same permissions.

### 2.2 Knowledge Bases

- Each user can create multiple knowledge bases.
- Knowledge bases are private user data.
- One user cannot view another user's knowledge bases, documents, learning progress, or learning records.
- Uploaded documents are grouped by knowledge base.
- The knowledge base management page should list different knowledge bases.
- After clicking a knowledge base, the user can view:
  - learning progress
  - uploaded documents
  - learning path
  - extracted knowledge points
  - user learning status related to this knowledge base
- Users can delete knowledge bases.
- Users can delete uploaded materials.
- Deleting a knowledge base must also delete all related documents, vector indexes, learning progress, and related information.

### 2.3 Document Upload

- Supported file types:
  - PDF
  - Markdown
  - TXT
- Upload limits are required.
- Specific upload limits can be decided during implementation.
- Uploaded materials should be parsed, chunked, embedded, indexed, and associated with the selected knowledge base.

### 2.4 Learning Sessions

- Users can create learning sessions.
- A learning session does not need to manually store which knowledge bases were used.
- The Agent or LLM should intelligently select the most relevant knowledge base.
- Only one most relevant knowledge base should be selected for a given learning flow or query.

### 2.5 Learning Path

- The Agent generates a learning path based on user goals, learning status, and the selected knowledge base.
- Users can manually edit the learning path.
- Manual editing should support adding, deleting, reordering, or changing stages.
- Learning path stages must display learning status, such as:
  - not started
  - in progress
  - completed
- The Agent can dynamically adjust the learning path according to user learning performance.
- When the Agent adjusts the path, it directly overwrites the current path.
- Historical versions of learning paths are not required.

### 2.6 Chat and Tutoring

- The system needs a chat window.
- Chat responses should support streaming output.
- Chat content should support Markdown rendering.
- The Agent should use retrieval-augmented generation based on the selected knowledge base.
- The system should support follow-up tutoring around the current learning stage.

### 2.7 Quiz and Feedback

- Main quiz types:
  - multiple choice
  - true or false
  - short answer
- Detailed per-question grading history is not required.
- The system must store enough quiz result information for the Agent to understand user learning performance.
- The Agent should use quiz accuracy to update its understanding of the user's learning status.
- The Agent can use feedback and quiz performance to adjust the learning path.

### 2.8 Frontend Layout

- The frontend style should be closer to a learning platform than an admin dashboard.
- The interface should include or reserve space for:
  - chat window
  - knowledge map area
  - user information page
  - knowledge base management page
- The knowledge map only needs a reserved area in the first version.
- The user information page should show:
  - account information
  - historical sessions
  - learning progress
- Knowledge base information should be managed on a separate page.

### 2.9 LLM Configuration

- API call information will be provided later by the user.
- The project should reserve OpenAI-compatible configuration:

```text
OPENAI_API_KEY
OPENAI_BASE_URL
OPENAI_MODEL
```

- Mock mode is not a current priority.

### 2.10 Django Extension

- Django can be kept in the architecture documentation as a possible future management backend extension.
- Django should not be introduced as the current runtime service.

## 3. Agent-Centered Requirements

The Agent is the core capability of the project. The implementation should prioritize a clear Agent workflow over excessive frontend detail.

Planned Agent responsibilities:

- Understand the user's learning goal.
- Diagnose the user's current level.
- Select the most relevant knowledge base.
- Retrieve relevant chunks from that knowledge base.
- Generate a structured learning path.
- Explain concepts in layered detail.
- Answer follow-up questions with references to uploaded materials.
- Generate quizzes for the current stage.
- Evaluate quiz performance at a summary level.
- Update the user's learning status.
- Dynamically adjust the learning path when needed.

## 4. Planned Technical Stack

- Backend: FastAPI
- Frontend: FastAPI templates and native JavaScript
- Database: SQLite
- Agent orchestration: LangGraph
- Vector storage and retrieval:
  - Chroma for persistent document and chunk metadata
  - FAISS for local similarity search demonstration
- LLM: OpenAI-compatible API

## 5. Planned API Surface

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/me`
- `POST /api/knowledge-bases`
- `GET /api/knowledge-bases`
- `GET /api/knowledge-bases/{id}`
- `PUT /api/knowledge-bases/{id}`
- `DELETE /api/knowledge-bases/{id}`
- `POST /api/knowledge-bases/{id}/documents/upload`
- `GET /api/knowledge-bases/{id}/documents`
- `DELETE /api/documents/{id}`
- `POST /api/learning/sessions`
- `GET /api/learning/sessions/{id}`
- `POST /api/learning/sessions/{id}/plan`
- `PUT /api/learning/sessions/{id}/plan`
- `POST /api/learning/sessions/{id}/chat`
- `POST /api/learning/sessions/{id}/quiz`
- `POST /api/learning/sessions/{id}/quiz/submit`

## 6. Open Questions

These points still need confirmation before implementation:

1. Should knowledge bases only have a name and description, or should they also include tags, cover image, created time, and updated time?
2. Should the Agent workflow be fixed as `diagnose -> select knowledge base -> retrieve -> plan -> explain -> chat -> quiz -> feedback -> adjust path`?
3. What fields should users fill in when creating a learning session: topic, current level, learning goal, available time, preferred style?
4. What information must be used when the Agent selects the most relevant knowledge base: name, description, extracted knowledge points, document summaries, user learning history?
5. Should knowledge point extraction run automatically after upload, or only when the user opens a knowledge base?
6. What fields should each learning path stage include: title, goal, knowledge points, recommended materials, exercises, status, estimated time?
7. What should trigger Agent path adjustment: low quiz accuracy, user request, repeated questions, or stage completion?
8. Should answers show source documents and retrieved chunk summaries?
9. How should short-answer questions be evaluated: score by LLM, text feedback only, or both?
10. Should every user chat message and Agent response be stored for later learning-status analysis?
