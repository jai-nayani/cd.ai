# LLM Council - Complete Project Flow Documentation

This document provides a comprehensive end-to-end explanation of how the LLM Council application works, from startup to final response delivery.

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Application Startup](#application-startup)
3. [User Interaction Flow](#user-interaction-flow)
4. [The 3-Stage Deliberation Process](#the-3-stage-deliberation-process)
5. [Data Storage & Persistence](#data-storage--persistence)
6. [Frontend State Management](#frontend-state-management)
7. [Key Technical Decisions](#key-technical-decisions)
8. [Complete Data Flow Diagram](#complete-data-flow-diagram)

---

## Architecture Overview

### Tech Stack
- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter API
- **Frontend:** React + Vite, react-markdown
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv (Python), npm (JavaScript)
- **Backend Port:** 8001
- **Frontend Port:** 5173

### Project Structure
```
llm-council/
├── backend/
│   ├── config.py          # Model configuration & API keys
│   ├── openrouter.py      # OpenRouter API client
│   ├── council.py         # Core 3-stage orchestration logic
│   ├── storage.py         # JSON-based conversation persistence
│   └── main.py            # FastAPI application & endpoints
├── frontend/
│   └── src/
│       ├── App.jsx        # Main orchestrator
│       ├── api.js         # Backend API client
│       └── components/
│           ├── ChatInterface.jsx  # Main chat UI
│           ├── Sidebar.jsx        # Conversations list
│           ├── Stage1.jsx         # Individual responses view
│           ├── Stage2.jsx         # Peer rankings view
│           └── Stage3.jsx         # Final synthesis view
└── data/
    └── conversations/     # Persisted conversation JSON files
```

---

## Application Startup

### Backend Initialization
```bash
uv run python -m backend.main
```

**What happens:**
1. FastAPI server starts on **port 8001**
2. Loads configuration from `backend/config.py`:
   - `COUNCIL_MODELS`: List of OpenRouter LLM identifiers
     - Example: `["openai/gpt-5.1", "google/gemini-3-pro-preview", "anthropic/claude-sonnet-4.5", "x-ai/grok-4"]`
   - `CHAIRMAN_MODEL`: The model that synthesizes the final answer
   - `OPENROUTER_API_KEY`: Loaded from `.env` file
3. Enables CORS for `localhost:5173` and `localhost:3000`
4. Exposes REST API endpoints:
   - `GET /` - Health check
   - `GET /api/conversations` - List all conversations
   - `POST /api/conversations` - Create new conversation
   - `GET /api/conversations/{id}` - Get specific conversation
   - `POST /api/conversations/{id}/message` - Send message (non-streaming)
   - `POST /api/conversations/{id}/message/stream` - Send message (SSE streaming)

### Frontend Initialization
```bash
cd frontend && npm run dev
```

**What happens:**
1. React app starts on **port 5173**
2. Vite dev server initialized
3. `main.jsx` renders `App.jsx`
4. `App.jsx` loads on mount:
   - Fetches conversation list from `GET /api/conversations`
   - Populates sidebar with existing conversations
5. User sees empty state: "Welcome to LLM Council"

---

## User Interaction Flow

### 1. Creating a New Conversation

**User Action:** Clicks "New Conversation" button in Sidebar

**Frontend (`App.jsx`):**
```javascript
handleNewConversation() {
  const newConv = await api.createConversation();
  setConversations([newConv, ...conversations]);
  setCurrentConversationId(newConv.id);
}
```

**API Call:** `POST /api/conversations`

**Backend (`main.py` → `storage.py`):**
1. Generates UUID: `uuid.uuid4()`
2. Creates conversation object:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2024-12-11T10:00:00.000000",
  "title": "New Conversation",
  "messages": []
}
```
3. Saves to `data/conversations/{uuid}.json`
4. Returns conversation object

**Frontend Update:**
- New conversation appears at top of sidebar
- Becomes active conversation
- Chat interface shows "Start a conversation" prompt

---

### 2. Sending a Message (The Main Flow)

**User Action:** Types question and presses Enter

**Frontend (`ChatInterface.jsx`):**
```javascript
// User types in multiline textarea (3 rows)
// Press Enter to send, Shift+Enter for new line
handleSubmit(e) {
  e.preventDefault();
  onSendMessage(input);
  setInput('');
}
```

**Frontend (`App.jsx`):**
```javascript
handleSendMessage(content) {
  // Optimistically add user message to UI
  const userMessage = { role: 'user', content };
  
  // Create placeholder assistant message with loading states
  const assistantMessage = {
    role: 'assistant',
    stage1: null,
    stage2: null,
    stage3: null,
    metadata: null,
    loading: { stage1: false, stage2: false, stage3: false }
  };
  
  // Send message with SSE streaming
  await api.sendMessageStream(conversationId, content, handleEvent);
}
```

**API Call:** `POST /api/conversations/{id}/message/stream`

---

## The 3-Stage Deliberation Process

This is the core innovation of LLM Council: a structured, transparent deliberation where multiple LLMs collaborate.

### Stage 1: Individual Responses

**Goal:** Collect independent answers from each council member

**Backend Flow (`council.py` - `stage1_collect_responses()`):**

1. **Event Emitted:** `stage1_start`
   - Frontend displays spinner: "Collecting individual responses..."

2. **Prepare Query:**
```python
messages = [{"role": "user", "content": user_query}]
```

3. **Parallel Execution (`openrouter.py` - `query_models_parallel()`):**
```python
# Creates async tasks for ALL council models simultaneously
tasks = [query_model(model, messages) for model in COUNCIL_MODELS]

# Executes in parallel using asyncio.gather()
responses = await asyncio.gather(*tasks)
```

4. **Individual Model Query (`openrouter.py` - `query_model()`):**
```python
async def query_model(model, messages, timeout=120.0):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": model, "messages": messages}
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
        data = response.json()
        return {
            'content': data['choices'][0]['message']['content'],
            'reasoning_details': data['choices'][0]['message'].get('reasoning_details')
        }
```

5. **Graceful Degradation:**
```python
# If some models fail, continues with successful responses
stage1_results = []
for model, response in responses.items():
    if response is not None:  # Only include successful responses
        stage1_results.append({
            "model": model,
            "response": response.get('content', '')
        })
```

6. **Event Emitted:** `stage1_complete` with data:
```json
[
  {"model": "openai/gpt-5.1", "response": "Quantum computing uses..."},
  {"model": "google/gemini-3-pro-preview", "response": "A quantum computer..."},
  {"model": "anthropic/claude-sonnet-4.5", "response": "Quantum computers leverage..."},
  {"model": "x-ai/grok-4", "response": "Think of quantum computing as..."}
]
```

**Frontend Rendering (`Stage1.jsx`):**
- Tab view with one tab per model
- Shows shortened model name (e.g., "gpt-5.1" from "openai/gpt-5.1")
- Active tab displays full response with markdown rendering
- User can click tabs to inspect each model's answer

---

### Stage 2: Peer Rankings (The Innovation!)

**Goal:** Each model evaluates all responses anonymously, preventing bias

**Backend Flow (`council.py` - `stage2_collect_rankings()`):**

1. **Event Emitted:** `stage2_start`
   - Frontend displays spinner: "Peer rankings..."

2. **Anonymization Step:**
```python
# Create anonymous labels
labels = [chr(65 + i) for i in range(len(stage1_results))]  # ['A', 'B', 'C', 'D']

# Create mapping for de-anonymization (not sent to models)
label_to_model = {
    f"Response {label}": result['model']
    for label, result in zip(labels, stage1_results)
}
# Example: {"Response A": "openai/gpt-5.1", "Response B": "google/gemini-3-pro-preview", ...}
```

**Why anonymization?** To prevent models from:
- Playing favorites based on brand reputation
- Being biased by model names
- Giving preferential treatment to specific providers

3. **Build Ranking Prompt:**
```python
responses_text = "\n\n".join([
    f"Response {label}:\n{result['response']}"
    for label, result in zip(labels, stage1_results)
])

ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""
```

**Why strict format?** Ensures reliable parsing of rankings for aggregation.

4. **Parallel Ranking Queries:**
```python
messages = [{"role": "user", "content": ranking_prompt}]
responses = await query_models_parallel(COUNCIL_MODELS, messages)
```
- Each council model evaluates ALL anonymized responses
- Models evaluate their own responses unknowingly (blind review)
- Returns detailed evaluation text

5. **Parse Rankings (`parse_ranking_from_text()`):**
```python
def parse_ranking_from_text(ranking_text):
    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        ranking_section = ranking_text.split("FINAL RANKING:")[1]
        
        # Extract numbered list: "1. Response A", "2. Response B", etc.
        numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
        if numbered_matches:
            return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]
        
        # Fallback: Extract all "Response X" patterns in order
        matches = re.findall(r'Response [A-Z]', ranking_section)
        return matches
    
    # Fallback: try to find any "Response X" patterns
    return re.findall(r'Response [A-Z]', ranking_text)
```

Example parsed result: `["Response C", "Response A", "Response B", "Response D"]`

6. **Calculate Aggregate Rankings (`calculate_aggregate_rankings()`):**
```python
def calculate_aggregate_rankings(stage2_results, label_to_model):
    model_positions = defaultdict(list)
    
    # Collect all positions for each model across all peer reviews
    for ranking in stage2_results:
        parsed_ranking = parse_ranking_from_text(ranking['ranking'])
        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)
    
    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })
    
    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])
    return aggregate
```

Example result:
```json
[
  {"model": "openai/gpt-5.1", "average_rank": 1.33, "rankings_count": 3},
  {"model": "anthropic/claude-sonnet-4.5", "average_rank": 2.00, "rankings_count": 3},
  {"model": "google/gemini-3-pro-preview", "average_rank": 2.67, "rankings_count": 3},
  {"model": "x-ai/grok-4", "average_rank": 3.00, "rankings_count": 3}
]
```

7. **Event Emitted:** `stage2_complete` with data and metadata:
```json
{
  "type": "stage2_complete",
  "data": [
    {
      "model": "openai/gpt-5.1",
      "ranking": "Response A provides excellent depth...\n\nFINAL RANKING:\n1. Response C\n2. Response A\n3. Response B\n4. Response D",
      "parsed_ranking": ["Response C", "Response A", "Response B", "Response D"]
    },
    ...
  ],
  "metadata": {
    "label_to_model": {
      "Response A": "openai/gpt-5.1",
      "Response B": "google/gemini-3-pro-preview",
      "Response C": "anthropic/claude-sonnet-4.5",
      "Response D": "x-ai/grok-4"
    },
    "aggregate_rankings": [...]
  }
}
```

**Frontend Rendering (`Stage2.jsx`):**

**Raw Evaluations Tab View:**
```javascript
function deAnonymizeText(text, labelToModel) {
  let result = text;
  Object.entries(labelToModel).forEach(([label, model]) => {
    const modelShortName = model.split('/')[1] || model;
    result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
  });
  return result;
}
```
- Tab view showing each model's evaluation
- **Client-side de-anonymization**: Replaces "Response A" with **bold model names**
- Important note: "model names shown in **bold** for readability, but original evaluation used anonymous labels"
- Shows "Extracted Ranking" below each evaluation for transparency

**Aggregate Rankings ("Street Cred") Display:**
```jsx
<div className="aggregate-rankings">
  <h4>Aggregate Rankings (Street Cred)</h4>
  <p>Combined results across all peer evaluations (lower score is better):</p>
  {aggregateRankings.map((agg, index) => (
    <div key={index} className="aggregate-item">
      <span className="rank-position">#{index + 1}</span>
      <span className="rank-model">{agg.model.split('/')[1]}</span>
      <span className="rank-score">Avg: {agg.average_rank.toFixed(2)}</span>
      <span className="rank-count">({agg.rankings_count} votes)</span>
    </div>
  ))}
</div>
```

Example display:
```
#1 gpt-5.1         Avg: 1.33  (3 votes)
#2 claude-sonnet-4.5  Avg: 2.00  (3 votes)
#3 gemini-3-pro-preview  Avg: 2.67  (3 votes)
#4 grok-4         Avg: 3.00  (3 votes)
```

---

### Stage 3: Final Synthesis

**Goal:** Chairman model synthesizes all information into coherent final answer

**Backend Flow (`council.py` - `stage3_synthesize_final()`):**

1. **Event Emitted:** `stage3_start`
   - Frontend displays spinner: "Final synthesis..."

2. **Build Comprehensive Context for Chairman:**
```python
stage1_text = "\n\n".join([
    f"Model: {result['model']}\nResponse: {result['response']}"
    for result in stage1_results
])

stage2_text = "\n\n".join([
    f"Model: {result['model']}\nRanking: {result['ranking']}"
    for result in stage2_results
])

chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""
```

**Key Point:** Chairman has **complete visibility** into:
- All individual responses from Stage 1
- All peer evaluations and rankings from Stage 2
- The original question

3. **Query Chairman Model:**
```python
messages = [{"role": "user", "content": chairman_prompt}]
response = await query_model(CHAIRMAN_MODEL, messages)
```
- Single query to designated chairman (e.g., `google/gemini-3-pro-preview`)
- Synthesizes "collective wisdom" of the council

4. **Fallback on Failure:**
```python
if response is None:
    return {
        "model": CHAIRMAN_MODEL,
        "response": "Error: Unable to generate final synthesis."
    }
```

5. **Event Emitted:** `stage3_complete` with data:
```json
{
  "type": "stage3_complete",
  "data": {
    "model": "google/gemini-3-pro-preview",
    "response": "Based on the council's deliberations, quantum computing represents..."
  }
}
```

**Frontend Rendering (`Stage3.jsx`):**
- **Green-tinted background** (#f0fff0) to highlight this is the conclusion
- Shows chairman model name: "Chairman: gemini-3-pro-preview"
- Markdown-rendered final answer
- This is the "official" council answer presented to the user

---

### Additional: Parallel Title Generation

**Backend (`council.py` - `generate_conversation_title()`):**

If this is the first message in a conversation:
```python
if is_first_message:
    title_task = asyncio.create_task(generate_conversation_title(request.content))
```

**Process:**
1. Runs in parallel with stages (doesn't block)
2. Uses fast, cheap model: `google/gemini-2.5-flash`
3. Prompt: "Generate a very short title (3-5 words maximum) that summarizes the following question..."
4. Cleans up result: removes quotes, truncates if > 50 chars
5. Fallback: "New Conversation" if generation fails

**Event Emitted:** `title_complete`
- Frontend reloads conversations list
- Title updates in sidebar

---

## Data Storage & Persistence

### Conversation Storage (`storage.py`)

**Location:** `data/conversations/{conversation_id}.json`

**Structure:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2024-12-11T10:00:00.000000",
  "title": "Quantum Computing Basics",
  "messages": [
    {
      "role": "user",
      "content": "What is quantum computing?"
    },
    {
      "role": "assistant",
      "stage1": [
        {"model": "openai/gpt-5.1", "response": "Quantum computing uses..."},
        {"model": "google/gemini-3-pro-preview", "response": "A quantum computer..."}
      ],
      "stage2": [
        {
          "model": "openai/gpt-5.1",
          "ranking": "Response A provides...\n\nFINAL RANKING:\n1. Response C\n2. Response A",
          "parsed_ranking": ["Response C", "Response A"]
        }
      ],
      "stage3": {
        "model": "google/gemini-3-pro-preview",
        "response": "Based on the council's deliberations..."
      }
    }
  ]
}
```

**Important:** `metadata` (label_to_model, aggregate_rankings) is **NOT persisted**
- Only returned in API responses
- Frontend stores in React state for active conversations
- Reduces storage size
- Can be regenerated if needed

### Storage Operations

**Create Conversation:**
```python
def create_conversation(conversation_id):
    conversation = {
        "id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": "New Conversation",
        "messages": []
    }
    path = get_conversation_path(conversation_id)
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)
    return conversation
```

**Add User Message:**
```python
def add_user_message(conversation_id, content):
    conversation = get_conversation(conversation_id)
    conversation["messages"].append({
        "role": "user",
        "content": content
    })
    save_conversation(conversation)
```

**Add Assistant Message:**
```python
def add_assistant_message(conversation_id, stage1, stage2, stage3):
    conversation = get_conversation(conversation_id)
    conversation["messages"].append({
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3
    })
    save_conversation(conversation)
```

**List Conversations (Metadata Only):**
```python
def list_conversations():
    conversations = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            data = json.load(open(path))
            conversations.append({
                "id": data["id"],
                "created_at": data["created_at"],
                "title": data.get("title", "New Conversation"),
                "message_count": len(data["messages"])
            })
    conversations.sort(key=lambda x: x["created_at"], reverse=True)
    return conversations
```

---

## Frontend State Management

### Main State (`App.jsx`)

```javascript
const [conversations, setConversations] = useState([]);           // List of all conversations
const [currentConversationId, setCurrentConversationId] = useState(null);  // Active conversation ID
const [currentConversation, setCurrentConversation] = useState(null);      // Full conversation data
const [isLoading, setIsLoading] = useState(false);                        // Global loading state
```

### Progressive Message Updates

**SSE Event Handling:**
```javascript
await api.sendMessageStream(conversationId, content, (eventType, event) => {
  switch (eventType) {
    case 'stage1_start':
      // Set loading.stage1 = true
      setCurrentConversation(prev => {
        const messages = [...prev.messages];
        const lastMsg = messages[messages.length - 1];
        lastMsg.loading.stage1 = true;
        return { ...prev, messages };
      });
      break;

    case 'stage1_complete':
      // Populate stage1 data, set loading.stage1 = false
      setCurrentConversation(prev => {
        const messages = [...prev.messages];
        const lastMsg = messages[messages.length - 1];
        lastMsg.stage1 = event.data;
        lastMsg.loading.stage1 = false;
        return { ...prev, messages };
      });
      break;

    case 'stage2_complete':
      // Populate stage2 data + metadata
      setCurrentConversation(prev => {
        const messages = [...prev.messages];
        const lastMsg = messages[messages.length - 1];
        lastMsg.stage2 = event.data;
        lastMsg.metadata = event.metadata;  // Contains label_to_model & aggregate_rankings
        lastMsg.loading.stage2 = false;
        return { ...prev, messages };
      });
      break;

    case 'stage3_complete':
      // Populate stage3 data
      setCurrentConversation(prev => {
        const messages = [...prev.messages];
        const lastMsg = messages[messages.length - 1];
        lastMsg.stage3 = event.data;
        lastMsg.loading.stage3 = false;
        return { ...prev, messages };
      });
      break;

    case 'complete':
      loadConversations();  // Refresh conversation list
      setIsLoading(false);
      break;
  }
});
```

### Optimistic UI Updates

```javascript
// Add user message immediately (before API call completes)
const userMessage = { role: 'user', content };
setCurrentConversation(prev => ({
  ...prev,
  messages: [...prev.messages, userMessage]
}));

// Add placeholder assistant message with loading states
const assistantMessage = {
  role: 'assistant',
  stage1: null,
  stage2: null,
  stage3: null,
  metadata: null,
  loading: { stage1: false, stage2: false, stage3: false }
};
setCurrentConversation(prev => ({
  ...prev,
  messages: [...prev.messages, assistantMessage]
}));
```

**Benefits:**
- Immediate user feedback
- Progressive rendering as stages complete
- No waiting for entire process to finish
- User can see real-time progress

---

## Key Technical Decisions

### 1. Async/Parallel Execution
**Decision:** Use `asyncio.gather()` for concurrent model queries

**Implementation:**
```python
tasks = [query_model(model, messages) for model in models]
responses = await asyncio.gather(*tasks)
```

**Benefit:** Minimizes latency (limited by slowest model, not sum of all models)

**Example:** 4 models with 30s response time = 30s total (not 120s)

---

### 2. Graceful Degradation
**Decision:** Continue with partial results if some models fail

**Implementation:**
```python
for model, response in responses.items():
    if response is not None:  # Only include successful responses
        results.append(...)
```

**Benefit:** System remains functional even if 1-2 models have issues

**Trade-off:** Fewer perspectives in deliberation, but better than complete failure

---

### 3. Anonymized Peer Review
**Decision:** Models evaluate anonymous "Response A, B, C" instead of "GPT-5.1, Claude, etc."

**Implementation:**
```python
# Backend creates mapping
label_to_model = {"Response A": "openai/gpt-5.1", "Response B": "google/gemini-3-pro-preview"}

# Models receive anonymous labels
ranking_prompt = """
Response A:
[content]

Response B:
[content]

Rank these responses...
"""

# Frontend de-anonymizes for display
function deAnonymizeText(text, labelToModel) {
  Object.entries(labelToModel).forEach(([label, model]) => {
    result = result.replace(new RegExp(label, 'g'), `**${model}**`);
  });
}
```

**Benefit:** Prevents confirmation bias, brand loyalty, reputation effects

**Transparency:** Users still see which model wrote what (client-side de-anonymization)

---

### 4. Strict Ranking Format with Fallback Parsing
**Decision:** Require specific "FINAL RANKING:" format but have fallback regex

**Implementation:**
```python
def parse_ranking_from_text(ranking_text):
    if "FINAL RANKING:" in ranking_text:
        # Try strict numbered format: "1. Response A"
        numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
        if numbered_matches:
            return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]
        
        # Fallback: Extract any "Response X" in order
        matches = re.findall(r'Response [A-Z]', ranking_section)
        return matches
    
    # Final fallback: scan entire text
    return re.findall(r'Response [A-Z]', ranking_text)
```

**Benefit:** Reliable parsing when models follow format, graceful degradation when they don't

---

### 5. Ephemeral Metadata
**Decision:** Don't persist `label_to_model` and `aggregate_rankings` to storage

**Rationale:**
- Reduces JSON file size
- Metadata is for real-time display during active session
- Can be regenerated from stage2 data if needed
- Not essential for conversation history

**Trade-off:** Historical conversations don't show aggregate rankings (acceptable)

---

### 6. Server-Sent Events (SSE) for Streaming
**Decision:** Use SSE instead of WebSockets or polling

**Implementation:**
```python
async def event_generator():
    yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
    stage1_results = await stage1_collect_responses(request.content)
    yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"
    # ... more stages ...
    yield f"data: {json.dumps({'type': 'complete'})}\n\n"

return StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
)
```

**Frontend:**
```javascript
const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const chunk = decoder.decode(value);
  const lines = chunk.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = line.slice(6);
      const event = JSON.parse(data);
      onEvent(event.type, event);
    }
  }
}
```

**Benefit:**
- Simple unidirectional communication (server → client)
- Built-in browser support
- Automatic reconnection
- No need for WebSocket infrastructure

---

### 7. Relative Backend Imports
**Decision:** Use relative imports in all backend modules

**Implementation:**
```python
# In council.py
from .openrouter import query_models_parallel, query_model
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL

# NOT absolute imports like:
# from backend.openrouter import ...
```

**Reason:** Python's module system requires relative imports when running as package

**Usage:** `python -m backend.main` (NOT `cd backend && python main.py`)

---

### 8. Client-Side De-anonymization
**Decision:** Backend creates mapping, frontend applies it for display

**Why not server-side?**
- Keeps backend simple and stateless
- Frontend controls presentation
- Easier to modify display logic without backend changes

**Implementation:**
```javascript
// Backend sends:
{
  "data": [...rankings with "Response A", "Response B"...],
  "metadata": {
    "label_to_model": {"Response A": "openai/gpt-5.1", ...}
  }
}

// Frontend displays with **bold** model names for readability
```

---

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUT                              │
│                  "What is quantum computing?"                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (React/Vite)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ App.jsx                                                  │  │
│  │ - Optimistic UI update (add user message)                │  │
│  │ - Create placeholder assistant message                   │  │
│  │ - Call api.sendMessageStream()                           │  │
│  └──────────────────────┬───────────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────────────┘
                          │ HTTP POST
                          │ /api/conversations/{id}/message/stream
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI/Python)                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ main.py: send_message_stream()                           │  │
│  │ - Save user message to storage                           │  │
│  │ - Start title generation (parallel, async)               │  │
│  │ - Begin SSE stream                                       │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────────────────┐  │
│  │ STAGE 1: council.py - stage1_collect_responses()        │  │
│  │                                                           │  │
│  │ SSE Event: "stage1_start"                                │  │
│  │                                                           │  │
│  │ ┌─────────────────────────────────────────────────────┐ │  │
│  │ │ openrouter.py: query_models_parallel()              │ │  │
│  │ │                                                      │ │  │
│  │ │ asyncio.gather([                                    │ │  │
│  │ │   query_model("openai/gpt-5.1", messages),         │ │  │
│  │ │   query_model("google/gemini-3-pro-preview", ...),  │ │  │
│  │ │   query_model("anthropic/claude-sonnet-4.5", ...),  │ │  │
│  │ │   query_model("x-ai/grok-4", messages)             │ │  │
│  │ │ ])                                                   │ │  │
│  │ │                                                      │ │  │
│  │ │         ┌──────────────────────┐                    │ │  │
│  │ │         │  OpenRouter API      │                    │ │  │
│  │ │    ┌────│  https://openrouter  │────┐               │ │  │
│  │ │    │    │  .ai/api/v1/chat/    │    │               │ │  │
│  │ │    │    │  completions         │    │               │ │  │
│  │ │    │    └──────────────────────┘    │               │ │  │
│  │ │    │              │                 │               │ │  │
│  │ │    ▼              ▼                 ▼               │ │  │
│  │ │  GPT-5.1      Gemini-3.0       Claude-4.5   Grok-4 │ │  │
│  │ │  Response      Response          Response   Response│ │  │
│  │ │    │              │                 │          │    │ │  │
│  │ │    └──────────────┴─────────────────┴──────────┘    │ │  │
│  │ │                   │                                  │ │  │
│  │ │    [Graceful degradation: continue if some fail]    │ │  │
│  │ └──────────────────┬──────────────────────────────────┘ │  │
│  │                    │                                     │  │
│  │ SSE Event: "stage1_complete"                            │  │
│  │ Data: [{model, response}, {model, response}, ...]      │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────────────────┐  │
│  │ STAGE 2: council.py - stage2_collect_rankings()         │  │
│  │                                                           │  │
│  │ SSE Event: "stage2_start"                                │  │
│  │                                                           │  │
│  │ 1. Anonymization:                                        │  │
│  │    labels = ['A', 'B', 'C', 'D']                         │  │
│  │    label_to_model = {                                    │  │
│  │      "Response A": "openai/gpt-5.1",                     │  │
│  │      "Response B": "google/gemini-3-pro-preview",        │  │
│  │      "Response C": "anthropic/claude-sonnet-4.5",        │  │
│  │      "Response D": "x-ai/grok-4"                         │  │
│  │    }                                                      │  │
│  │                                                           │  │
│  │ 2. Build ranking prompt with anonymous labels:           │  │
│  │    "Response A: [content from GPT-5.1]                   │  │
│  │     Response B: [content from Gemini]                    │  │
│  │     Response C: [content from Claude]                    │  │
│  │     Response D: [content from Grok]                      │  │
│  │     Evaluate and rank these responses..."                │  │
│  │                                                           │  │
│  │ 3. Parallel ranking queries to all models:               │  │
│  │    query_models_parallel(COUNCIL_MODELS, ranking_prompt) │  │
│  │    → Each model ranks all responses (blind review)       │  │
│  │                                                           │  │
│  │ 4. Parse rankings:                                       │  │
│  │    parse_ranking_from_text()                             │  │
│  │    → Extract "FINAL RANKING:" section                    │  │
│  │    → Parse numbered list: "1. Response C", etc.          │  │
│  │                                                           │  │
│  │ 5. Calculate aggregate rankings:                         │  │
│  │    calculate_aggregate_rankings()                        │  │
│  │    → Average position across all peer reviews            │  │
│  │    → Sort by average_rank (lower is better)              │  │
│  │                                                           │  │
│  │ SSE Event: "stage2_complete"                             │  │
│  │ Data: rankings array with parsed_ranking                 │  │
│  │ Metadata: {label_to_model, aggregate_rankings}           │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────────────────┐  │
│  │ STAGE 3: council.py - stage3_synthesize_final()         │  │
│  │                                                           │  │
│  │ SSE Event: "stage3_start"                                │  │
│  │                                                           │  │
│  │ 1. Build comprehensive chairman prompt:                  │  │
│  │    "You are the Chairman of an LLM Council.              │  │
│  │                                                           │  │
│  │     Original Question: [user query]                      │  │
│  │                                                           │  │
│  │     STAGE 1 - Individual Responses:                      │  │
│  │     Model: openai/gpt-5.1                                │  │
│  │     Response: [full response]                            │  │
│  │     ...                                                   │  │
│  │                                                           │  │
│  │     STAGE 2 - Peer Rankings:                             │  │
│  │     Model: openai/gpt-5.1                                │  │
│  │     Ranking: [full evaluation]                           │  │
│  │     ...                                                   │  │
│  │                                                           │  │
│  │     Synthesize into comprehensive answer..."             │  │
│  │                                                           │  │
│  │ 2. Query CHAIRMAN_MODEL with full context:               │  │
│  │    query_model(CHAIRMAN_MODEL, chairman_prompt)          │  │
│  │    → Single model synthesizes all information            │  │
│  │                                                           │  │
│  │ SSE Event: "stage3_complete"                             │  │
│  │ Data: {model: CHAIRMAN_MODEL, response: "..."}           │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────────────────┐  │
│  │ Parallel: generate_conversation_title()                  │  │
│  │ (if first message)                                       │  │
│  │ - Uses google/gemini-2.5-flash (fast & cheap)            │  │
│  │ - Generates 3-5 word title                               │  │
│  │                                                           │  │
│  │ SSE Event: "title_complete"                              │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────────────────┐  │
│  │ storage.py: add_assistant_message()                      │  │
│  │ - Save to data/conversations/{id}.json                   │  │
│  │ - Persist: stage1, stage2, stage3 data                   │  │
│  │ - Note: metadata NOT persisted (ephemeral)               │  │
│  │                                                           │  │
│  │ SSE Event: "complete"                                    │  │
│  └──────────────────────┬───────────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────────────┘
                          │ SSE Stream Complete
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND RENDERING                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ChatInterface.jsx                                        │  │
│  │                                                           │  │
│  │ ┌──────────────────────────────────────────────────────┐│  │
│  │ │ USER MESSAGE                                         ││  │
│  │ │ "What is quantum computing?"                         ││  │
│  │ └──────────────────────────────────────────────────────┘│  │
│  │                                                           │  │
│  │ ┌──────────────────────────────────────────────────────┐│  │
│  │ │ ASSISTANT MESSAGE                                    ││  │
│  │ │                                                      ││  │
│  │ │ ┌────────────────────────────────────────────────┐ ││  │
│  │ │ │ Stage1.jsx: Individual Responses               │ ││  │
│  │ │ │ [Tab: gpt-5.1] [Tab: gemini-3-pro] [Tab: ...]  │ ││  │
│  │ │ │                                                │ ││  │
│  │ │ │ Active tab shows full response with markdown  │ ││  │
│  │ │ └────────────────────────────────────────────────┘ ││  │
│  │ │                                                      ││  │
│  │ │ ┌────────────────────────────────────────────────┐ ││  │
│  │ │ │ Stage2.jsx: Peer Rankings                      │ ││  │
│  │ │ │                                                │ ││  │
│  │ │ │ Raw Evaluations (tabs):                        │ ││  │
│  │ │ │ - Shows evaluation text                        │ ││  │
│  │ │ │ - Client-side de-anonymization                 │ ││  │
│  │ │ │ - "Response A" → **gpt-5.1** (bold)           │ ││  │
│  │ │ │ - Shows extracted ranking for validation       │ ││  │
│  │ │ │                                                │ ││  │
│  │ │ │ Aggregate Rankings (Street Cred):              │ ││  │
│  │ │ │ #1 gpt-5.1         Avg: 1.33  (3 votes)       │ ││  │
│  │ │ │ #2 claude-sonnet   Avg: 2.00  (3 votes)       │ ││  │
│  │ │ │ #3 gemini-3-pro    Avg: 2.67  (3 votes)       │ ││  │
│  │ │ │ #4 grok-4          Avg: 3.00  (3 votes)       │ ││  │
│  │ │ └────────────────────────────────────────────────┘ ││  │
│  │ │                                                      ││  │
│  │ │ ┌────────────────────────────────────────────────┐ ││  │
│  │ │ │ Stage3.jsx: Final Council Answer               │ ││  │
│  │ │ │ [Green background: #f0fff0]                    │ ││  │
│  │ │ │                                                │ ││  │
│  │ │ │ Chairman: gemini-3-pro-preview                 │ ││  │
│  │ │ │                                                │ ││  │
│  │ │ │ Based on the council's deliberations,          │ ││  │
│  │ │ │ quantum computing represents a revolutionary   │ ││  │
│  │ │ │ approach to computation that leverages...      │ ││  │
│  │ │ │ [Full synthesized answer with markdown]        │ ││  │
│  │ │ └────────────────────────────────────────────────┘ ││  │
│  │ └──────────────────────────────────────────────────────┘│  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Sidebar updated with conversation title:                      │
│  "Quantum Computing Basics"                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Error Handling & Edge Cases

### Backend Error Handling

**Individual Model Failures:**
```python
try:
    response = await client.post(...)
except Exception as e:
    print(f"Error querying model {model}: {e}")
    return None  # Graceful degradation
```
- Continues with successful responses
- Doesn't fail entire stage if 1-2 models fail

**Chairman Failure:**
```python
if response is None:
    return {
        "model": CHAIRMAN_MODEL,
        "response": "Error: Unable to generate final synthesis."
    }
```
- Returns error message
- User still sees Stage 1 & 2 results

**Title Generation Failure:**
```python
if response is None:
    return "New Conversation"
```
- Fallback to generic title
- Doesn't block main flow

### Frontend Error Handling

**SSE Stream Errors:**
```javascript
case 'error':
  console.error('Stream error:', event.message);
  setIsLoading(false);
  // Remove optimistic messages
  setCurrentConversation(prev => ({
    ...prev,
    messages: prev.messages.slice(0, -2)  // Remove user + assistant placeholders
  }));
```

**Network Failures:**
```javascript
try {
  await api.sendMessageStream(...)
} catch (error) {
  console.error('Failed to send message:', error);
  // Rollback optimistic updates
  setCurrentConversation(prev => ({
    ...prev,
    messages: prev.messages.slice(0, -2)
  }));
  setIsLoading(false);
}
```

### Edge Cases

**No Models Respond in Stage 1:**
```python
if not stage1_results:
    return [], [], {
        "model": "error",
        "response": "All models failed to respond. Please try again."
    }, {}
```

**Ranking Parse Failures:**
- Multiple fallback regex patterns
- Worst case: extracts any "Response X" mentions
- Displays raw text for user validation

**Missing Metadata in Frontend:**
```javascript
labelToModel={msg.metadata?.label_to_model}  // Optional chaining
aggregateRankings={msg.metadata?.aggregate_rankings}
```
- Component handles undefined metadata gracefully
- Shows what's available

---

## Performance Characteristics

### Typical Timing (4 models)

- **Stage 1:** 20-40 seconds (parallel execution, limited by slowest model)
- **Stage 2:** 30-60 seconds (parallel ranking, more complex prompt)
- **Stage 3:** 15-30 seconds (single chairman query)
- **Total:** ~65-130 seconds (~1-2 minutes)

### Optimization Strategies

**Parallel Execution:**
- Stage 1: All models queried simultaneously
- Stage 2: All ranking queries simultaneous
- Title generation: Runs in parallel with stages

**Streaming Updates:**
- User sees progress in real-time
- Can start reading Stage 1 responses while Stage 2 runs
- Perceived performance much better than batch processing

**Fast Model for Title:**
- Uses `gemini-2.5-flash` for quick title generation
- Doesn't block critical path

### Resource Usage

**Backend:**
- Async I/O: minimal CPU/memory usage during API waits
- Each conversation: ~10-50KB JSON storage

**Frontend:**
- Single SSE connection per message
- Minimal memory footprint
- React state updates are incremental

---

## Configuration & Customization

### Changing Council Members

**Edit `backend/config.py`:**
```python
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
    "meta-llama/llama-4-90b",  # Add new model
]
```

**Supported Models:** Any model available on OpenRouter

**Considerations:**
- More models = longer Stage 1 & 2 times (but still parallel)
- More models = richer perspectives & better peer review
- Check OpenRouter pricing for each model

### Changing Chairman

**Edit `backend/config.py`:**
```python
CHAIRMAN_MODEL = "anthropic/claude-sonnet-4.5"
```

**Chairman can be:**
- Same as a council member
- Different from all council members
- Any OpenRouter model

**Best Chairman Characteristics:**
- Strong synthesis capabilities
- Good at summarizing multiple viewpoints
- Balanced reasoning

### Port Configuration

**Backend (`backend/main.py`):**
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)  # Change port here
```

**Frontend (`frontend/src/api.js`):**
```javascript
const API_BASE = 'http://localhost:8001';  // Match backend port
```

**Note:** Also update CORS allowed origins in `main.py` if changing frontend port

---

## Troubleshooting

### "Module not found" errors
**Problem:** Running backend incorrectly

**Solution:** Always run as module from project root:
```bash
# ✅ Correct
uv run python -m backend.main

# ❌ Incorrect
cd backend && python main.py
```

### All models failing
**Problem:** Invalid API key or no credits

**Solution:**
1. Check `.env` file: `OPENROUTER_API_KEY=sk-or-v1-...`
2. Verify API key at openrouter.ai
3. Check account credits/balance
4. Test with `backend/test_openrouter.py`

### CORS errors in browser
**Problem:** Frontend port not allowed

**Solution:** Add frontend origin to `backend/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:YOUR_PORT"],
    ...
)
```

### SSE stream disconnects
**Problem:** Long-running requests timing out

**Solution:** Increase timeout in `openrouter.py`:
```python
async def query_model(model, messages, timeout=240.0):  # Increase to 240s
```

### Rankings not parsing correctly
**Problem:** Model not following format

**Solution:**
1. Check "Extracted Ranking" in Stage 2 UI
2. Fallback regex should catch most cases
3. Consider adding more specific instructions to prompt in `council.py`

---

## Security Considerations

### API Key Protection
- Store in `.env` file (gitignored)
- Never commit to version control
- Use environment variables in production

### CORS Configuration
- Currently allows localhost only
- Update for production deployment
- Consider restricting to specific domains

### Input Validation
- No sensitive data is logged
- User messages stored locally only
- Consider adding input sanitization for production

### Rate Limiting
- Not implemented (assumes single user)
- Add rate limiting for multi-user deployments
- Consider per-user quotas

---

## Future Enhancement Ideas

1. **Configurable Council via UI**
   - No code editing required
   - Save/load council configurations
   - A/B test different council compositions

2. **Streaming Token-by-Token Responses**
   - Currently batch loads each stage
   - Could stream individual model tokens
   - Better real-time experience

3. **Export Conversations**
   - Export to Markdown
   - Export to PDF with formatting
   - Share links to conversations

4. **Model Performance Analytics**
   - Track aggregate rankings over time
   - Show "leaderboard" across conversations
   - Identify consistently high-performing models

5. **Custom Ranking Criteria**
   - Beyond accuracy/insight
   - User-defined evaluation dimensions
   - Weighted scoring

6. **Support for Reasoning Models**
   - Special handling for o1, o3, etc.
   - Display reasoning traces
   - Separate ranking for reasoning quality

7. **Multi-User Support**
   - User authentication
   - Private conversations
   - Shared council configurations

8. **Cost Tracking**
   - Token usage per conversation
   - Cost estimation per model
   - Budget alerts

---

## Conclusion

LLM Council is a transparent, democratic system for collaborative AI deliberation. The key innovations are:

1. **Anonymized Peer Review:** Prevents bias in Stage 2 evaluations
2. **Parallel Execution:** Minimizes latency despite multiple model queries
3. **Progressive Streaming:** Real-time UI updates via SSE
4. **Complete Transparency:** Users can inspect every step of the process
5. **Aggregate Rankings:** "Street cred" scores show which models excel

The system balances **sophistication** (3-stage deliberation with peer review) with **simplicity** (JSON storage, straightforward React UI, minimal dependencies).

**Core Philosophy:** Like a panel discussion where you can see everyone's notes, all peer evaluations, and the final consensus—completely transparent and democratic.

---

## Quick Reference

### Start Application
```bash
# Option 1: Start script
./start.sh

# Option 2: Manual
# Terminal 1: Backend
uv run python -m backend.main

# Terminal 2: Frontend
cd frontend && npm run dev

# Access: http://localhost:5173
```

### File Locations
- **Config:** `backend/config.py`
- **API Client:** `frontend/src/api.js`
- **Stage Logic:** `backend/council.py`
- **Storage:** `data/conversations/*.json`
- **Components:** `frontend/src/components/*`

### Key Endpoints
- `POST /api/conversations` - Create conversation
- `POST /api/conversations/{id}/message/stream` - Send message (SSE)
- `GET /api/conversations` - List conversations
- `GET /api/conversations/{id}` - Get conversation

### Environment Variables
```bash
# .env file in project root
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

---

*This documentation is comprehensive but the code is intentionally simple. As noted in the README: "Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like."*
