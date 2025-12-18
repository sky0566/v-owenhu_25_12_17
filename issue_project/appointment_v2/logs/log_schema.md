Structured log schema:
- timestamp (ISO)
- level (INFO/WARN/ERROR)
- message_id (unique appointment/request ID)
- message (text)
- payload (masked where needed) - email fields masked as ***REDACTED***

Sensitive fields must not be logged in clear text; use mask_sensitive helper in src/service.py
