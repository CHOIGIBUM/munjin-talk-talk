# Serverless Backend

AWS SAM backend for the 문진톡톡 MVP.

## Endpoints

```text
POST /sessions
POST /transcribe-stream-url
POST /process-answer
POST /extract
POST /match
POST /validate
GET  /doctor/queue
GET  /onepager/{session_id}
POST /doctor-response
GET  /guide/{session_id}
```

## Runtime

- Python 3.12 Lambda
- API Gateway HTTP API
- DynamoDB session table
- Amazon Transcribe Streaming
- Amazon Bedrock Nova Pro/Lite
- Amazon Titan Text Embeddings for symptom IR
- Pydantic fixed-schema validation for LLM JSON outputs

## Required AWS Resources

Create or prepare these before `sam deploy`:

- DynamoDB table with partition key `session_id` as string
- S3 bucket for deployment/transient artifacts only. Patient audio is not uploaded or stored.
- Lambda execution role with:
  - CloudWatch Logs
  - DynamoDB read/write
  - S3 read/write for deployment artifacts if the bucket is still used by the stack
  - `transcribe:StartStreamTranscriptionWebSocket`
  - Bedrock invoke

## Deploy

```powershell
sam build
sam deploy --guided
```

SAM parameters:

```text
Stack Name: munjin-mvp-backend
AWS Region: ap-northeast-2
SessionsTableName: <DynamoDB table name>
ArtifactsBucketName: <S3 bucket name>
LambdaRoleArn: <Lambda execution role ARN>
CustomVocabularyName: <optional>
Allow SAM CLI IAM role creation: N
```

Copy the CloudFormation output `ApiEndpoint` into the frontend environment:

```text
VITE_API_BASE_URL=https://<api-id>.execute-api.ap-northeast-2.amazonaws.com
```

## Audio Handling

Patient audio storage is disabled. The frontend requests `POST /transcribe-stream-url`,
opens a browser WebSocket to Amazon Transcribe Streaming, and sends PCM audio directly.
Only the recognized text is submitted to `POST /process-answer`.

Legacy `POST /upload-url` and `GET /transcribe-result` return disabled responses and
must not be used for real patient audio.

## Model Routing

Default Bedrock model routing:

- Q1/progress/new-symptom extraction: `apac.amazon.nova-pro-v1:0`
- Q2/Q3/Q4 structured extraction and standardization: `apac.amazon.nova-lite-v1:0`
- Symptom matching: BM25 over `diseases_cleaned.json` + `symptom_index.json`, reranked with `amazon.titan-embed-text-v2:0`
- Onepaper review: `apac.amazon.nova-pro-v1:0`
- Patient guide rewriting: `apac.amazon.nova-lite-v1:0`

## LLM Output Validation

LLM output is not accepted just because it is valid JSON. The Lambda validates model outputs with
Pydantic schemas under `src/schemas/`:

- required fields must exist
- enum values must match the fixed schema
- unexpected fields such as `score`, `confidence`, or `probability` are rejected
- `source_quote` and `original_quote` must be grounded in the exact patient transcript

Extraction uses `src/schemas/extraction.py`, onepaper final review uses `src/schemas/review.py`,
and patient guide generation uses `src/schemas/guide.py`.

If extraction validation fails, the error list is sent back to the LLM in a bounded repair loop. With
`ALLOW_RULE_FALLBACK=false`, persistent validation failure returns an error instead of silently
falling back to rule-based extraction.

## Symptom IR Data

Runtime symptom search uses only these source files under `src/data/`:

- `diseases_cleaned.json`
- `symptom_index.json`

At cold-start, Lambda builds concise symptom search documents from those two files by deterministic rules. The packaged `symptom_embeddings_*.json` file is a numeric Titan vector index for those generated documents, so `/match` can run full hybrid retrieval without waiting for document embeddings on the first request. No LLM-written `symptom_retrieval_dataset.json` is required.

Production-like testing should use:

```text
USE_BEDROCK_LLM=true
ALLOW_RULE_FALLBACK=false
```

## Notes

- Staff and doctor routes are not protected by this backend yet.
- Do not use real patient data before access control and retention policies are defined.
