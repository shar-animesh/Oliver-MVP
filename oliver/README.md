# Oliver

Oliver is one tool-using agent governed by one system prompt. The FastAPI email endpoint stores complete conversations, retrieves related internal initiatives from Azure SQL, and returns either a branded email response or a no-reply instruction.

## Runtime flow

1. `POST /api/v1/email/respond` persists the inbound message and reconstructs its complete thread.
2. Oliver creates a `text-embedding-3-large` vector for the readable transcript and stores it in Azure SQL as `VECTOR(1536)`.
3. Azure SQL cosine search retrieves a bounded set of similar conversations belonging to other internal participants.
4. Oliver receives the current thread plus complete related transcripts and may recommend a relevant internal contact.
5. The model returns parsed `OliverResponse` JSON. The endpoint wraps `SEND_EMAIL` content in the branded shell, records the run and semantic matches, and returns it to the Logic App. `NO_REPLY` records the decision without sending mail.

```python
from utils.models import OliverResponse
from utils.prompts import build_system_prompt
from utils.templates import render_oliver_email

messages = [
    {
        "role": "system",
        "content": build_system_prompt(email_thread),
    }
]

raw_response = model.complete(messages, tools=runtime_tools)
response = OliverResponse.model_validate_json(raw_response)

if response.action == "SEND_EMAIL":
    email_html = render_oliver_email(
        subject=response.subject,
        content_html=response.content_html,
    )
```

## Final response

Oliver always returns one valid JSON object:

```json
{
    "action": "SEND_EMAIL",
    "subject": "Re: AI initiative proposal",
    "content_html": "<h1>Initiative Name: Initiative Assessment</h1><p>...</p>"
}
```

Allowed actions are:

- `SEND_EMAIL`: the host may render and send the generated subject and content.
- `NO_REPLY`: no email is needed; subject and content are null.

The response model defines only the structured fields and allowed actions. The system prompt is responsible for the generated HTML rules. The branded shell applies all typography, colors, spacing, list styling, and table styling.

## Behavior

Oliver handles the latest inbound message according to its actual intent rather than forcing every email through an assessment:

- ordinary and follow-up questions receive concise conversational answers;
- missing material information produces a focused information request;
- sufficiently detailed AI initiatives receive a holistic, evidence-led assessment;
- existing initiatives receive lifecycle, monitoring, value, risk, or next-step guidance as appropriate;
- consequential or insufficiently authorized actions are not performed; Oliver sends an email identifying the decision or authorization needed.

The system prompt defines proactive tool use, source and instruction boundaries, prompt-injection resistance, authorization requirements, inline web citations, assessment considerations, report composition, and Outlook/Gmail-safe fragment requirements.

## Rendering

`build_system_prompt` accepts one plain Python string and inserts it into a delimited `<email_thread>` element. The email thread is treated as untrusted content.

```python
from utils.prompts import build_system_prompt

system_prompt = build_system_prompt(email_thread)
```

`render_oliver_email` inserts the model-generated fragment into an autoescaped `.jinja2.html` shell. The fragment is trusted because the system prompt owns its HTML requirements; the subject and preheader remain escaped. The official white Siemens Energy logo is packaged locally and embedded into each rendered email as a base64 PNG data URI, so rendering does not request an external image.

```python
from utils.templates import render_oliver_email

email_html = render_oliver_email(
    subject=response.subject,
    content_html=response.content_html,
)
```

The shell fixes only the brand frame: the official logo, dark-purple/violet color treatment, header, footer, 660px email container, and Gmail/Outlook-safe outer tables. Oliver owns every useful content section inside it.

## Development

The project uses Poetry Core and uv:

```bash
uv lock
uv sync
uv run ruff check .
uv run ruff format --check .
uvx poetry check
uvx poetry build
```

The Azure deployment applies the single initial Alembic migration before the Container Apps start. New conversations are indexed as Oliver processes them, and cross-team contact discovery is limited to Siemens Energy email addresses.
