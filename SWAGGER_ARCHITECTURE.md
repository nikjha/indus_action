Swagger Authorization Architecture

System Overview


┌─────────────────────────────────────────────────────────────────┐
│                          User/Developer                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
            1. POST /login
            (username, password)
                     │
                     ▼
        ┌────────────────────────┐
        │   Auth Service :8001   │
        │   ┌────────────────┐   │
        │   │ POST /login    │   │
        │   │ Returns Token  │   │
        │   └────────────────┘   │
        └────┬───────────────────┘
             │
             │ 2. JWT Token
             │ (access_token)
             │
             ▼
    ┌────────────────────────┐
    │  Token in Browser      │
    │  "eyJ0eXAiOiJKV1QiLi.." │
    └────┬───────────────────┘
         │
         │ 3. Authorization Header
         │ Bearer eyJ0eXA...
         │
         ├─────────────────────────────────────────────┐
         │                                             │
         ▼                                             ▼
    ┌────────────────┐                        ┌──────────────────┐
    │ Swagger UI     │                        │ API Endpoints    │
    │ /docs          │                        │ /users, /tasks   │
    │                │                        │                  │
    │ ┌────────────┐ │                        │ ┌──────────────┐ │
    │ │ Authorize  │ │                        │ │ Validate     │ │
    │ │ Button     │ │                        │ │ Bearer Token │ │
    │ │            │ │                        │ │              │ │
    │ │ [Bearer]   │ │                        │ └──────────────┘ │
    │ │ [Token]    │ │                        │                  │
    │ └────────────┘ │                        │ ┌──────────────┐ │
    │                │                        │ │ Return Data  │ │
    │ ┌────────────┐ │                        │ │ or 401/403   │ │
    │ │ Try it out │ │                        │ └──────────────┘ │
    │ │ Execute    │ │                        │                  │
    │ └────────────┘ │                        │                  │
    └────────────────┘                        └──────────────────┘
         │                                             ▲
         │                                             │
         └─────────────────────────────────────────────┘
                 Bearer Token in Header




Authentication Flow Diagram


START
  │
  ▼
┌─────────────────────────────────┐
│ User opens /docs in browser     │
│ (e.g., http://localhost:8000)   │
└──────────────┬──────────────────┘
               │
               ▼
        ┌──────────────┐
        │ Check Auth   │
        │ Header?      │
        └──┬───────┬───┘
           │       │
         YES      NO
           │       │
           │       ▼
           │    ┌──────────────────┐
           │    │ Prompt for Auth  │
           │    │ ┌──────────────┐ │
           │    │ │ 1. Basic Auth│ │
           │    │ │ 2. Bearer    │ │
           │    │ └──────────────┘ │
           │    └────────┬─────────┘
           │             │
           │         User selects
           │             │
           ▼             ▼
    ┌────────────┐  ┌───────────────┐
    │ Bearer     │  │ Basic (docs:   │
    │ Token      │  │ docs123)       │
    └─────┬──────┘  └───────┬───────┘
          │                 │
          ▼                 ▼
    ┌─────────────────────────────┐
    │ Validate Credentials        │
    └──┬────────────────────────┬─┘
       │ Valid?                 │
       │ YES            NO ─────┘
       ▼
    ┌──────────────────────────┐
    │ Return Swagger UI        │
    │ (HTML + Assets)          │
    │                          │
    │ ┌────────────────────┐   │
    │ │ Authorize          │   │
    │ │ Try it out         │   │
    │ │ Execute            │   │
    │ │ View Responses     │   │
    │ └────────────────────┘   │
    └──────────────┬───────────┘
                   │
                   ▼
            ┌────────────────┐
            │ User can test  │
            │ API endpoints  │
            │ interactively  │
            └────────────────┘
                   │
                   ▼
                 END



Service Architecture


                    ┌─────────────────────────────────────────┐
                    │      User/Developer Browser             │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
                    ▼                                     ▼
            ┌──────────────────┐            ┌──────────────────┐
            │  Swagger UI      │            │  ReDoc UI        │
            │  /docs           │            │  /redoc          │
            │                  │            │                  │
            │  - Interactive   │            │  - Alternative   │
            │  - Try endpoints │            │  - Read-only     │
            │  - Bearer auth   │            │  - Clean layout  │
            └────────┬─────────┘            └────────┬─────────┘
                     │                               │
                     │    ┌─────────────────────────┘
                     │    │
                     ▼    ▼
        ┌─────────────────────────────────┐
        │   OpenAPI Security Handler      │
        │                                 │
        │ 1. Check Bearer Token           │
        │    └─ JWT.decode()              │
        │    └─ Validate signature        │
        │ 2. Check Basic Auth (fallback)  │
        │    └─ base64.decode()           │
        │    └─ Compare password          │
        └────────────┬────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │   FastAPI Application           │
        │                                 │
        │   @app.get("/docs")             │
        │   @app.get("/redoc")            │
        │   @app.get("/openapi.json")     │
        │                                 │
        │   + Custom OpenAPI schema       │
        │   + Security scheme: Bearer     │
        │   + Global security: [Bearer]   │
        └────────────────┬────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
    ┌─────────┐    ┌─────────┐    ┌──────────────┐
    │ Auth    │    │ User    │    │ Task Service │
    │ Service │    │ Service │    │              │
    │         │    │         │    │              │
    │ :8001  │    │ :8002  │    │ :8003        │
    └─────────┘    └─────────┘    └──────────────┘
        │              │                │
        │              │                ▼
        │              │        ┌──────────────┐
        │              │        │ Eligibility  │
        │              │        │ Engine       │
        │              │        │ :8004        │
        │              │        └──────────────┘
        │              │                │
        └──────────────┴────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │   API Gateway :8000             │
        │   Main entry point for clients  │
        │   Unified /docs for all APIs    │
        └─────────────────────────────────┘




Authentication Layer


┌───────────────────────────────────────────────────────────────┐
│              Request to /docs or /openapi.json                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
                ┌────────────────────────┐
                │ Extract Authorization  │
                │ Header                 │
                └────┬───────────┬───────┘
                     │           │
            ┌────────┘           └──────────┐
            │                               │
            ▼                               ▼
    ┌───────────────────┐        ┌──────────────────┐
    │ Bearer Token?     │        │ Basic Auth?      │
    │ Bearer eyJhb...   │        │ Basic ZG9jczp...│
    └─────┬─────────────┘        └────┬─────────────┘
          │                           │
          ▼                           ▼
    ┌───────────────────┐    ┌──────────────────┐
    │ JWT.decode()      │    │ base64.decode()  │
    │ ├─ Check expiry   │    │ ├─ Extract user  │
    │ ├─ Verify sig     │    │ ├─ Extract pass  │
    │ └─ Get claims     │    │ └─ Compare creds │
    └─────┬─────────────┘    └────┬─────────────┘
          │                       │
          │        ┌──────────────┘
          │        │
          ▼        ▼
    ┌─────────────────────┐
    │ Token/Auth Valid?   │
    └──┬────────────────┬─┘
       │                │
      YES               NO
       │                │
       ▼                ▼
    ┌──────────┐    ┌─────────────────┐
    │ Grant    │    │ Return 401      │
    │ Access   │    │ Unauthorized    │
    └──────────┘    └─────────────────┘




Token Lifecycle


1. LOGIN
   ┌──────────────────────┐
   │ POST /login          │
   │ {user, password}     │
   └──────┬───────────────┘
          │
          ▼
   ┌──────────────────────────────┐
   │ Auth Service                 │
   │ - Verify credentials         │
   │ - Generate JWT token         │
   │ - Set expiry: 60 minutes     │
   └──────┬───────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────┐
   │ Return Token                         │
   │ {                                    │
   │   "access_token": "eyJ...",         │
   │   "refresh_token": "...",           │
   │   "role": "ADMIN"                   │
   │ }                                    │
   └──────┬───────────────────────────────┘
          │
2. STORE  │
   ┌──────▼──────────────────┐
   │ Browser Session Storage │
   │ (Swagger remembers)     │
   └──────┬───────────────────┘
          │
3. USE    │
   │      ▼
   │   ┌─────────────────────────────┐
   │   │ Authorization: Bearer <tok> │
   │   └─────┬───────────────────────┘
   │         │
   │         ▼
   │   ┌─────────────────────────────┐
   │   │ Service receives request    │
   │   │ - Extract token             │
   │   │ - Validate JWT              │
   │   │ - Check expiry              │
   │   │ - Check role/permissions    │
   │   └──────┬──────────────────────┘
   │          │
   │    Success or Error
   │          │
   └──────────┘
          │
4. EXPIRE │
   │      ▼
   │   ┌──────────────────────────────┐
   │   │ 60 minutes pass             │
   │   │ Token becomes invalid       │
   │   │ JWT.decode() raises error   │
   │   └──────┬───────────────────────┘
   │          │
   │          ▼
   │   ┌──────────────────────────┐
   │   │ Return 401 Unauthorized  │
   │   │ User must login again    │
   │   └──────────────────────────┘
   │
   └─ Go back to step 1




Code Flow: Request to /docs


User Request
  │
  │ GET /docs
  │ Authorization: Bearer eyJ...
  │
  ▼
┌──────────────────────────────────┐
│ FastAPI Router                   │
│ Matches: @app.get("/docs")       │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ protected_docs() Function        │
│ (in each service's main.py)      │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ Extract Authorization Header     │
│ if not header:                   │
│   raise 401                      │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ Check if Bearer Token            │
│ startswith("Bearer ")             │
└────┬──────────────────────┬───────┘
     │                      │
    YES                     NO
     │                      │
     ▼                      ▼
┌──────────────────┐  ┌──────────────────┐
│ Call validate_   │  │ Call _check_     │
│ bearer_token()   │  │ basic_auth()     │
│                  │  │                  │
│ from shared_auth │  │ base64 compare   │
└────┬─────────────┘  └────┬─────────────┘
     │                     │
     ▼                     ▼
┌──────────────────────────────────┐
│ Validation Success               │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ Return get_swagger_ui_html()     │
│ openapi_url="/openapi.json"      │
│ persistAuthorization=True        │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ User receives Swagger UI         │
│ - Can see all endpoints          │
│ - Can test with token            │
│ - Authorization persists         │
└──────────────────────────────────┘




Multi-Service Architecture


                    ┌──────────────────────┐
                    │   Browser Session    │
                    │  With Bearer Token   │
                    └─────────┬────────────┘
                              │
                Token: eyJ...│
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
    ┌────────────┐       ┌────────────┐       ┌────────────┐
    │ Service A  │       │ Service B  │       │ Service C  │
    │ /docs      │       │ /docs      │       │ /docs      │
    │            │       │            │       │            │
    │ Bearer:    │       │ Bearer:    │       │ Bearer:    │
    │ eyJ...(✓) │       │ eyJ...(✓) │       │ eyJ...(✓) │
    └────────────┘       └────────────┘       └────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
    Swagger UI          Swagger UI          Swagger UI
    Authorized          Authorized          Authorized




Error Handling


Request to Protected Endpoint
       │
       ▼
┌──────────────────────┐
│ Check Auth Header    │
└───┬────────────────┬─┘
    │                │
  Valid           Invalid
    │                │
    ▼                ▼
Process             ┌────────────────┐
Request             │ 401 Response   │
    │               │ "Unauthorized" │
    │               │ WWW-Authenticate
    │               │ Bearer realm=..│
    │               └────────────────┘
    │
    ▼
┌──────────────────────┐
│ Check Permissions    │
│ (role, etc)          │
└───┬────────────────┬─┘
    │                │
  Allowed         Denied
    │                │
    ▼                ▼
Process             ┌────────────────┐
Request             │ 403 Response   │
    │               │ "Forbidden"    │
    │               │ Insufficient   │
    │               │ permissions    │
    │               └────────────────┘
    │
    ▼
┌──────────────────────┐
│ Execute Endpoint     │
│ Return 200 + Data    │
└──────────────────────┘

