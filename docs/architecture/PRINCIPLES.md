# Architecture and Engineering Principles

This document defines the default architectural and engineering principles for this project.

These principles apply to human contributors and AI coding agents.

They are defaults, not dogma. A principle may be intentionally violated when there is a concrete engineering reason, but the trade-off must be made explicit. Significant exceptions must be documented through an Architecture Decision Record (ADR).

---

# 1. Architectural Direction

The system follows a **microservice-oriented architecture**.

Major capabilities should be isolated behind explicit service boundaries when this provides meaningful separation of:

* responsibilities;
* dependencies;
* runtime requirements;
* hardware requirements;
* scaling;
* failure domains;
* deployment lifecycle.

The primary motivation for service boundaries is **strong decoupling between major system capabilities**.

However:

> Do not create a microservice merely to achieve code modularity.

Inside each service, normal software modularity should be achieved through modules, interfaces, dependency injection, adapters, and clear responsibilities.

The preferred structure is therefore:

```text
System
│
├── Service A
│   ├── domain
│   ├── application
│   ├── ports
│   └── adapters
│
├── Service B
│   ├── domain
│   ├── application
│   ├── ports
│   └── adapters
│
└── Service C
    ├── domain
    ├── application
    ├── ports
    └── adapters
```

A service is a deployment boundary.

A module is a code organization boundary.

Do not confuse the two.

---

# 2. Service Boundary Principle

A service should represent a cohesive capability of the system.

Good candidates for independent services typically have one or more of the following characteristics:

* distinct dependencies;
* distinct hardware requirements;
* independent scaling requirements;
* meaningful failure isolation;
* independent deployment lifecycle;
* clearly defined external contract;
* computationally expensive or specialized execution;
* realistic possibility of replacing the implementation independently.

Examples may include capabilities such as:

```text
OCR
LLM inference
document processing
search
embedding generation
```

depending on the actual requirements of the project.

A class, repository, utility, database table, or small domain operation is not automatically a service.

---

# 3. Strong Service Decoupling

Services must interact through explicit contracts.

A service must not depend on another service's:

* source code;
* internal classes;
* internal Python modules;
* internal implementation details;
* private configuration;
* database schema.

Prefer:

```text
Service A
    │
    │ documented contract
    ▼
Service B
```

over:

```text
Service A
    │
    ├── imports Service B code
    ├── accesses Service B database
    └── depends on Service B internals
```

A service should ideally be replaceable by another implementation preserving the same contract.

---

# 4. HTTP/REST as the Default Service Communication Mechanism

HTTP/REST is the default mechanism for synchronous communication between services.

Prefer simple and explicit communication:

```text
Service A
    │
    │ HTTP
    ▼
Service B
```

Services should expose documented APIs.

When practical, HTTP services should expose an OpenAPI specification.

Examples:

```text
GET  /health
GET  /v1/jobs/{id}
POST /v1/ocr
POST /v1/generate
```

HTTP contracts should be treated as public interfaces between services even when the services are currently deployed on the same machine.

---

# 5. Do Not Introduce Distributed Infrastructure Without Need

Message brokers, distributed queues, event buses, service meshes, distributed caches, and similar infrastructure must solve a concrete problem.

Do not introduce technologies such as RabbitMQ or Kafka solely because the architecture uses microservices.

Introduce asynchronous infrastructure when requirements such as the following actually arise:

* durable background jobs;
* buffering of bursts;
* temporary consumer unavailability;
* independent event consumers;
* asynchronous retry;
* high-throughput worker pools;
* persistent job delivery.

Until such requirements exist, prefer simpler communication mechanisms.

The architectural principle is:

> Use the simplest communication mechanism that preserves the required service independence.

---

# 6. Network Boundaries Are Expensive

Every network boundary introduces possible:

* timeouts;
* partial failures;
* serialization errors;
* network errors;
* version incompatibilities;
* latency;
* retries;
* observability requirements.

Therefore, creating a service boundary must provide enough architectural value to justify these costs.

Do not replace cheap local function calls with network calls without a clear reason.

---

# 7. Explicit API Contracts

Service APIs are architectural contracts.

Contracts should define:

* request schema;
* response schema;
* error behavior;
* status codes;
* semantic meaning;
* compatibility expectations.

Contracts should not expose unnecessary implementation details.

Prefer:

```json
{
  "document_id": "123",
  "text": "...",
  "confidence": 0.94
}
```

over structures mirroring internal ORM objects or implementation-specific classes.

Breaking API changes should result in explicit contract version changes when compatibility cannot be preserved.

For example:

```text
/v1/ocr
/v2/ocr
```

rather than silently changing semantics.

---

# 8. No Shared Internal Database Ownership

A service owns its internal persistence.

Other services must not directly query or modify tables owned by that service.

Avoid:

```text
Service A ─────┐
               │
Service B ─────┼──► shared internal tables
               │
Service C ─────┘
```

Prefer explicit ownership:

```text
Service A
    │
    ▼
Data owned by A


Service B
    │
    ▼
Data owned by B
```

When Service B needs information owned by Service A, it should normally obtain it through the documented contract of Service A.

Physical database infrastructure may be shared when operationally convenient, but **logical data ownership must remain explicit**.

---

# 9. Low Coupling

Components should know as little as reasonably possible about other components.

This principle applies both:

* between microservices;
* inside individual microservices.

A change inside one component should have minimal impact on unrelated components.

### Review question

> If this implementation changes, what else must change?

Large propagation of changes indicates excessive coupling.

---

# 10. High Cohesion

Every service and internal module should have a clear responsibility.

A service should represent a cohesive capability.

A module inside that service should represent an even more focused responsibility.

Avoid arbitrary grouping of unrelated functionality merely because it is convenient to place it in the same process.

---

# 11. Dependency Inversion

Inside each service, high-level application logic should depend on abstractions rather than concrete infrastructure implementations.

Prefer:

```text
DocumentProcessor
       ↓
     OCRPort
       ↑
       ├── QwenAdapter
       ├── PaddleAdapter
       └── RemoteOCRAdapter
```

instead of:

```text
DocumentProcessor
       ↓
 QwenConcreteClient
```

External technology should be replaceable without requiring changes to core application logic.

---

# 12. Explicit Dependency Injection

Dependencies should preferably be supplied explicitly.

Prefer:

```python
processor = DocumentProcessor(ocr=ocr_backend)
```

over:

```python
class DocumentProcessor:
    def __init__(self):
        self.ocr = QwenOCR()
```

Avoid hidden dependencies and unnecessary global state.

Dependencies should be visible through constructors or function signatures whenever practical.

---

# 13. Ports and Adapters Inside Services

Each sufficiently complex service should isolate application logic from external infrastructure.

Conceptually:

```text
                   Application
                        │
               ┌────────┼────────┐
               │        │        │
             Port     Port     Port
               │        │        │
               ▼        ▼        ▼
             HTTP       DB      Model
            Adapter   Adapter   Adapter
```

Application and domain logic should not directly depend on external frameworks when an appropriate abstraction can reasonably isolate them.

---

# 14. Adapter Boundary for External Systems

External libraries and APIs should be isolated behind adapters when they represent infrastructure dependencies.

Examples include:

* OCR libraries;
* LLM providers;
* ML runtimes;
* databases;
* cloud APIs;
* external HTTP APIs;
* object storage.

Prefer:

```text
Application
    ↓
 OCRPort
    ↓
QwenAdapter
    ↓
Qwen API
```

The adapter owns translation between the external system and the application's internal representation.

---

# 15. Strategy for Interchangeable Implementations

When multiple implementations provide the same conceptual capability, model them behind a common contract.

Example:

```text
OCRBackend
├── QwenOCR
├── PaddleOCR
└── TesseractOCR
```

or:

```text
LLMBackend
├── OpenAI
├── Anthropic
└── LocalVLLM
```

Consumers should not need to know which concrete implementation is active.

This applies inside a service.

At the distributed-system level, an entire microservice may also eventually be replaced if the replacement preserves its external API contract.

---

# 16. Factory for Object Construction

Complex implementation construction should be centralized.

Avoid scattered implementation selection:

```python
if backend == "qwen":
    ...
elif backend == "paddle":
    ...
```

throughout application code.

Prefer:

```text
Configuration
      ↓
    Factory
      ↓
Implementation
```

Object construction and business behavior should remain separate concerns.

---

# 17. Registry for Implementation Discovery

When a service supports several interchangeable implementations, a Registry may associate implementation names with implementations.

For example:

```text
OCR Registry

qwen      → QwenOCRAdapter
paddle    → PaddleOCRAdapter
tesseract → TesseractOCRAdapter
```

Adding another implementation should ideally require:

```text
new implementation
+
registration
+
tests
```

rather than modification across unrelated modules.

---

# 18. Avoid the Service Locator Anti-pattern

Registries must not become global dependency containers.

Avoid arbitrary application code such as:

```python
registry.get("database")
registry.get("ocr")
registry.get("storage")
registry.get("llm")
```

This creates hidden dependencies.

Prefer:

```text
Registry
    ↓
Factory
    ↓
Composition Root
    ↓
Dependency Injection
    ↓
Application
```

---

# 19. Composition Root

Each service should have a clear location where concrete dependencies are assembled.

For example:

```python
ocr = OCRFactory.create(settings.ocr)
repository = Repository(settings.database)

application = OCRApplication(
    ocr=ocr,
    repository=repository,
)
```

The Composition Root is allowed to know concrete implementations.

Core application modules should generally not.

---

# 20. Independent Service ConfigurationR

Each service should explicitly declare the configuration it requires.

Avoid a single global configuration object containing implementation details for the entire distributed system.

Prefer service-specific configuration such as:

```text
OCR Service
    OCR_MODEL
    DEVICE
    TIMEOUT

API Service
    DATABASE_URL
    OCR_SERVICE_URL
```

A service should not require unrelated configuration to start.

---

# 21. Failure Isolation

Failure of one service should not unnecessarily corrupt or destabilize unrelated services.

Callers of remote services must consider:

* connection failure;
* timeout;
* malformed response;
* service unavailable;
* unexpected status code.

External service calls must have explicit timeout behavior.

Retries should only be introduced when they are semantically safe and justified.

A network call must never be assumed to succeed merely because the target service normally runs on the same machine.

---

# 22. Explicit Health Interfaces

Independently deployed services should provide a minimal health interface when appropriate.

For example:

```text
GET /health
```

Health endpoints should be simple and suitable for:

* Docker;
* development tooling;
* orchestration;
* debugging.

Readiness and liveness may be separated later if operational requirements justify the distinction.

---

# 23. Observability Across Service Boundaries

Distributed calls should remain traceable.

Important operations should carry a request or correlation identifier when practical.

For example:

```text
request_id = 91e2...
```

should allow logs from:

```text
API
 ↓
Document Service
 ↓
OCR Service
```

to be associated with the same operation.

Logging should make service boundaries easier to understand rather than hiding them.

Do not introduce a complex distributed tracing platform until necessary.

---

# 24. Open for Extension

Prefer architectures where implementations can be added with minimal modification to existing working code.

Ask:

> What must change if we add another implementation tomorrow?R

For an internal backend, ideally:

```text
new adapter
+
registration
+
tests
```

For a replacement microservice, ideally:

```text
new service
+
same contract
+
configuration change
```

Consumers should remain unchanged whenever the existing contract remains valid.

This is a practical application of the Open/Closed Principle.

---

# 25. Testing Strategy

Architecture should facilitate testing at different boundaries.

## Unit tests

Test application logic without unnecessary external infrastructure.

Prefer substitutes such as:

```text
FakeOCR
FakeRepository
FakeLLM
```

## Integration tests

Test real adapters against their dependencies where appropriate.

## Contract tests

Service interfaces should be tested against their documented contracts.

## Service integration tests

Important interactions between services should be tested through the same public interface used in production.

Do not bypass public service APIs merely to make integration tests easier.

---

# 26. Service Independence Test

For every service, periodically ask:

> Could this service theoretically be rewritten in another language while preserving its contract?

The answer does not have to imply that rewriting is desirable.

The question exists as a test for accidental implementation coupling.

If another service imports internal classes, depends on internal file layouts, or directly queries internal tables, the boundary is probably not sufficiently independent.

---

# 27. Architectural Review Checklist

Before accepting a change, consider:

1. Does it introduce unnecessary coupling?
2. Does it violate a service boundary?
3. Is this functionality in the correct service?
4. Does creating a new service have a concrete justification?
5. Is another service's internal implementation being exposed?
6. Is another service's database being accessed directly?
7. Is the network contract explicit?
8. Could the API evolve without modifying its consumers unnecessarily?
9. Does application logic depend directly on infrastructure?
10. Could the dependency be injected?
11. Is an external API leaking beyond its adapter?
12. Is implementation-selection logic scattered?
13. Would adding another implementation require modifying business logic?
14. Is a Registry being used as a Service Locator?
15. Can important application behavior be tested without unrelated infrastructure?
16. Are network failures and timeouts handled explicitly?
17. Has new infrastructure been introduced without solving a concrete problem?
18. Has architectural complexity increased more than the problem justifies?

---

# 28. Simplicity Rule

Strong decoupling does not mean maximum abstraction.

Microservices do not mean maximum distribution.

Do not introduce:

* interfaces;
* factories;
* registries;
* adapters;
* services;
* queues;
* caches;
* orchestration infrastructure;

merely because these patterns exist.

Every abstraction must solve a concrete design problem.

Every network boundary must solve a concrete architectural or operational problem.

Prefer:

> the simplest architecture that preserves the required boundaries and allows the system to evolve safely.

---

# 29. Default Architecture

Unless a concrete requirement justifies another approach, prefer:

```text
                   Client
                     │
                    HTTP
                     │
                     ▼
                 API Service
                     │
          ┌──────────┼───────────┐
          │          │           │
         HTTP       HTTP        HTTP
          │          │           │
          ▼          ▼           ▼
      Service A   OCR Service  LLM Service
```

Each service:

```text
Service
│
├── API / transport
├── application
├── domain
├── ports
├── adapters
└── composition root
```

Communication between independently deployed services occurs through documented network contracts.

HTTP/REST is the default synchronous communication mechanism.

Additional distributed infrastructure is introduced only when concrete requirements justify it.

---

# 30. Architectural Decisions

Important architectural decisions should be documented under:

```text
docs/architecture/decisions/
```

using Architecture Decision Records.

An ADR should document:

* context;
* decision;
* alternatives considered;
* trade-offs;
* consequences.

Examples:

```text
ADR-001-use-microservices-for-model-inference.md
ADR-002-http-as-default-service-communication.md
ADR-003-ocr-service-boundary.md
```

An explicit documented trade-off is preferable to silently violating an architectural principle.

---

# Core Architectural Rule

When uncertain, optimize for:

```text
clear boundaries
+
low coupling
+
high cohesion
+
explicit contracts
+
replaceable implementations
+
service independence
+
operational simplicity
```

Strong decoupling is a goal.

Distributed complexity is a cost.

The architecture should obtain the former while introducing the latter only when justified.
