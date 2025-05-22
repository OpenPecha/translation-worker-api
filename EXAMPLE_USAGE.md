# Translation Queue API Usage Examples

This document provides examples of how to use the Translation Queue API.

## Adding a Translation Job

**Endpoint:** `POST /messages`

### Simple Translation Request

```json
{
  "content": "Hello world! This text needs to be translated.",
  "model_name": "gpt-4",
  "api_key": "sk-your-api-key-here"
}
```

### Translation with Priority and Metadata

```json
{
  "content": "This is an urgent message that needs translation.",
  "model_name": "gpt-4",
  "api_key": "sk-your-api-key-here",
  "priority": 10,
  "metadata": {
    "source_language": "en",
    "target_language": "es",
    "domain": "technical",
    "urgency": "high"
  }
}
```

## Checking Translation Status

**Endpoint:** `GET /messages/{message_id}`

Replace `{message_id}` with the ID returned when you added the message.

## Updating Translation Status

**Endpoint:** `POST /messages/{message_id}/status`

### Update Progress

```json
{
  "progress": 25.0,
  "status_type": "started",
  "message": "Translation 25% complete"
}
```

### Mark as Completed

```json
{
  "progress": 100.0,
  "status_type": "completed",
  "message": "Translation completed successfully"
}
```

### Mark as Failed

```json
{
  "progress": 0.0,
  "status_type": "failed",
  "message": "Translation failed: Invalid API key"
}
```

## Getting Queue Statistics

**Endpoint:** `GET /queue/stats`

This will return information about the current state of the queue, including counts of messages in different status states.
